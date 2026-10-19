"""Build the golden contract fixtures (contract-fixtures/) from a restored corpus.

Copies a hand-picked set of small real Acts, one or more per structural shape class, and
writes index.json (corpus-shaped) and contract.json (shape facts + SHA-256 per fixture).

Refuses to rewrite the manifest when the shape vocabulary (tag names, hcontainer names)
differs from the recorded one unless STRUCTURE_VERSION was bumped past the recorded
version. That is the guard against changing AKN shape without telling consumers.

Usage:
    python scripts/build_contract_fixtures.py --corpus-dir corpus
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from lexau.corpus import STRUCTURE_VERSION  # noqa: E402

AKN = "{http://docs.oasis-open.org/legaldocml/ns/akn/3.0}"
PACKAGE = Path(__file__).resolve().parent.parent / "contract-fixtures" / "src" / "lexau_contract_fixtures"
DATA = PACKAGE / "data"

# Real, small Acts picked by shape. Add a slug here, never hand-edit the XML.
SELECTION = [
    "carer-recognition-act-2010",
    "net-zero-economy-authority-(transitional-provisions)-act-2024",
    "tax-laws-amendment-(gifts)-act-2015",
    "governor-general-amendment-(salary)-act-2014",
    "excise-tariff-amendment-(product-stewardship-for-oil)-act-2023",
    "digital-id-(transitional-and-consequential-provisions)-act-2024",
    "overseas-missions-(privileges-and-immunities)-act-1995",
    "excess-exploration-credit-tax-act-2015",
    "customs-charges-and-levies-legislation-amendment-(sheep-and-lamb)-act-2020",
    "migration-legislation-amendment-act-(no.-6)-1995",
    "new-business-tax-system-(franking-deficit-tax)-act-2002",
    "public-and-educational-lending-rights-(better-income-for-authors)-consequential-amendments-and-transitional-provisions-act-2026",
]

# Each shape class is a predicate over the measured facts. Every class must be held by at
# least one fixture (tests/test_contract_fixtures.py enforces it).
SHAPE_CLASSES = {
    "flat_clause": lambda f: f["flat_clauses"] > 0,
    "nested_clause": lambda f: f["nested_clauses"] > 0,
    "quoted_amendment": lambda f: f["quoted_structures"] > 0 and f["amended_acts"] > 0,
    "quoted_definition": lambda f: f["quoted_definitions"] > 0,
    "schedule_no_clause": lambda f: f["attachments_without_clause"] > 0,
    "attachment_table": lambda f: f["attachment_tables"] > 0,
    "oversized_clause": lambda f: f["clause_max_words"] >= 1500,
    "duplicate_eid": lambda f: f["duplicate_eids"] > 0,
    "authorial_note": lambda f: f["authorial_notes"] > 0,
    "cross_act_refs": lambda f: f["cross_act_refs"] >= 5,
    "definitions": lambda f: f["definitions"] >= 5,
}


def _words(el: etree._Element) -> int:
    return sum(len(t.split()) for t in el.itertext())


def _name(el: etree._Element) -> str:
    return el.tag.removeprefix(AKN) if isinstance(el.tag, str) else ""


def measure(xml_path: Path) -> dict:
    root = etree.parse(str(xml_path)).getroot()
    tags: dict[str, int] = {}
    hcontainers: dict[str, int] = {}
    eids: dict[str, int] = {}
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        tags[_name(el)] = tags.get(_name(el), 0) + 1
        if _name(el) == "hcontainer":
            n = el.get("name", "")
            hcontainers[n] = hcontainers.get(n, 0) + 1
        if el.get("eId"):
            eids[el.get("eId")] = eids.get(el.get("eId"), 0) + 1

    attachments = list(root.iter(f"{AKN}attachment"))
    flat = nested = max_words = 0
    for att in attachments:
        for h in att.iter(f"{AKN}hcontainer"):
            if h.get("name") != "clause":
                continue
            max_words = max(max_words, _words(h))
            ancestors = {a.get("name") for a in h.iterancestors(f"{AKN}hcontainer")}
            if ancestors & {"part", "division"}:
                nested += 1
            else:
                flat += 1
    cross_act = [
        r for r in root.iter(f"{AKN}ref") if "/au/act/" in (r.get("href") or "")
    ]
    return {
        "flat_clauses": flat,
        "nested_clauses": nested,
        "clause_max_words": max_words,
        "quoted_structures": tags.get("quotedStructure", 0),
        "amended_acts": hcontainers.get("amendedAct", 0),
        "quoted_definitions": sum(
            1 for q in root.iter(f"{AKN}quotedStructure") if next(q.iter(f"{AKN}def"), None) is not None
        ),
        "attachments": len(attachments),
        "attachments_without_clause": sum(
            1
            for a in attachments
            if not any(h.get("name") == "clause" for h in a.iter(f"{AKN}hcontainer"))
        ),
        "attachment_tables": sum(len(list(a.iter(f"{AKN}table"))) for a in attachments),
        "attachment_words": sum(_words(a) for a in attachments),
        "duplicate_eids": sum(c - 1 for c in eids.values() if c > 1),
        "authorial_notes": tags.get("authorialNote", 0),
        "cross_act_refs": len(cross_act),
        "definitions": tags.get("def", 0),
        "tags": sorted(tags),
        "hcontainer_names": sorted(hcontainers),
    }


def classify(facts: dict) -> list[str]:
    return [name for name, pred in SHAPE_CLASSES.items() if pred(facts)]


def build_manifest(fixtures_dir: Path, slugs: list[str]) -> dict:
    fixtures = {}
    for slug in slugs:
        path = fixtures_dir / "xml" / f"{slug}.xml"
        facts = measure(path)
        fixtures[slug] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "classes": classify(facts),
            "facts": facts,
        }
    vocab = lambda key: sorted({v for f in fixtures.values() for v in f["facts"][key]})  # noqa: E731
    return {
        "structure_version": STRUCTURE_VERSION,
        "shape_classes": sorted(SHAPE_CLASSES),
        "tag_vocabulary": vocab("tags"),
        "hcontainer_vocabulary": vocab("hcontainer_names"),
        "fixtures": fixtures,
    }


def check_version_bump(new: dict, old: dict | None) -> None:
    """Shape vocabulary may only change when STRUCTURE_VERSION moved past the recorded one."""
    if old is None or new["structure_version"] > old["structure_version"]:
        return
    for key in ("tag_vocabulary", "hcontainer_vocabulary"):
        added = sorted(set(new[key]) - set(old[key]))
        if added:
            raise SystemExit(
                f"{key} gained {added} but STRUCTURE_VERSION is still {new['structure_version']}. "
                "Bump STRUCTURE_VERSION in src/lexau/corpus.py (and the fixture package major version) "
                "before regenerating, so consumers fail closed."
            )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-dir", type=Path, required=True)
    args = ap.parse_args()

    index = json.loads((args.corpus_dir / "index.json").read_text())["acts"]
    by_name_slug = {slug: e for slug, e in index.items()}
    missing = [s for s in SELECTION if s not in by_name_slug]
    if missing:
        raise SystemExit(f"Not in corpus index: {missing}")

    manifest_path = DATA / "contract.json"
    old = json.loads(manifest_path.read_text()) if manifest_path.exists() else None

    (DATA / "xml").mkdir(parents=True, exist_ok=True)
    for stale in (DATA / "xml").glob("*.xml"):
        stale.unlink()
    for slug in SELECTION:
        shutil.copyfile(args.corpus_dir / by_name_slug[slug]["xml_path"], DATA / "xml" / f"{slug}.xml")

    manifest = build_manifest(DATA, SELECTION)
    check_version_bump(manifest, old)
    uncovered = [c for c in SHAPE_CLASSES if not any(c in f["classes"] for f in manifest["fixtures"].values())]
    if uncovered:
        raise SystemExit(f"No fixture holds shape class(es): {uncovered}")

    (DATA / "index.json").write_text(
        json.dumps(
            {
                "acts": {s: by_name_slug[s] for s in SELECTION},
                "updated_at": None,
                "structure_version": STRUCTURE_VERSION,
            },
            indent=2,
        )
        + "\n"
    )
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Wrote {len(SELECTION)} fixtures; classes: {manifest['shape_classes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
