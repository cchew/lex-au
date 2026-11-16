"""Compare two corpus xml dirs: byte identity, section counts, term counts, text loss, eId integrity, figure drops.

Release check: exits 1 on lost paragraph text, duplicate or empty eIds, a section or figure drop, or (unless
--allow-section-increase) any section-count change."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from lxml import etree

AKN = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
LOCAL_REF_RE = re.compile(r'refersTo="#term-[^"]*--[^"]*"')


# builder.py stamps today's date on the FRBRManifestation Generation date, so a
# rebuild on another day never matches the baseline byte-for-byte. Only that
# one date attribute is rewritten; every other byte is compared as-is.
_MANIFESTATION_RE = re.compile(r"<(?:\w+:)?FRBRManifestation\b.*?</(?:\w+:)?FRBRManifestation>", re.DOTALL)
_GEN_DATE_TAG_RE = re.compile(r"<(?:\w+:)?FRBRdate\b[^>]*\bname=\"Generation\"[^>]*>")
_DATE_ATTR_RE = re.compile(r'\bdate="[^"]*"')
GENERATION_DATE_TOKEN = "GENERATION-DATE"


def normalise_generation_date_bytes(xml_bytes: bytes) -> bytes:
    def fix_block(m: re.Match[str]) -> str:
        return _GEN_DATE_TAG_RE.sub(
            lambda t: _DATE_ATTR_RE.sub(f'date="{GENERATION_DATE_TOKEN}"', t.group(0), count=1), m.group(0)
        )

    return _MANIFESTATION_RE.sub(fix_block, xml_bytes.decode("utf-8")).encode("utf-8")


def act_counts(xml_bytes: bytes) -> dict[str, int]:
    root = etree.fromstring(xml_bytes)
    return {
        "sections": len(root.findall(f".//{{{AKN}}}section")),
        "terms": len(root.findall(f".//{{{AKN}}}term")),
        "local_refs": len(LOCAL_REF_RE.findall(xml_bytes.decode("utf-8"))),
        # builder.py emits every figure as <figure><img src=...>; both counts must never drop.
        "figures": len(root.findall(f".//{{{AKN}}}figure")),
        "images": len(root.findall(f".//{{{AKN}}}img")),
    }


_LABEL_RE = re.compile(r"^(?:\d+[A-Z]*\.?\s*)?(?:\(\d+[A-Z]?\)\s+)?")
_WS_RE = re.compile(r"\s+")
_MIN_PROBE = 12


def _norm(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def _paragraph_texts(root: etree._Element) -> list[str]:
    return [_norm("".join(p.itertext())) for p in root.iter(f"{{{AKN}}}p")]


def lost_text(base_bytes: bytes, new_bytes: bytes) -> list[str]:
    """Paragraphs present in the baseline whose text no longer appears anywhere in the new
    Act. A leading section/subsection label ("3. ", "1.(1) ") is ignored, because a label
    that moves into <num> or a heading is not loss; text that moves elsewhere is not loss either."""
    base = Counter(_paragraph_texts(etree.fromstring(base_bytes)))
    new_root = etree.fromstring(new_bytes)
    new = Counter(_paragraph_texts(new_root))
    full_new = _norm("".join(new_root.itertext()))
    lost: list[str] = []
    for text in (base - new).elements():
        probe = _LABEL_RE.sub("", text, count=1)[:80]
        if len(probe) >= _MIN_PROBE and probe not in full_new:
            lost.append(text)
    return lost


def eid_problems(xml_bytes: bytes) -> tuple[int, int]:
    """(duplicate eId count, empty eId count)."""
    seen: Counter[str] = Counter()
    empty = 0
    for el in etree.fromstring(xml_bytes).iter():
        eid = el.get("eId") if isinstance(el.tag, str) else None
        if eid is None:
            continue
        if eid == "":
            empty += 1
        seen[eid] += 1
    return sum(c - 1 for c in seen.values() if c > 1), empty


def diff_dirs(
    base: Path,
    new: Path,
    names: list[str] | None = None,
    normalise_generation_date: bool = True,
) -> dict:
    """names: file stems to compare; default is every xml present in `new`."""
    stems = names if names is not None else sorted(p.stem for p in new.glob("*.xml"))
    acts: dict[str, dict] = {}
    for stem in stems:
        b, n = base / f"{stem}.xml", new / f"{stem}.xml"
        if not b.exists() or not n.exists():
            acts[stem] = {"missing": [x.parent.name for x in (b, n) if not x.exists()]}
            continue
        bb, nb = b.read_bytes(), n.read_bytes()
        bc, nc = act_counts(bb), act_counts(nb)
        same = bb == nb
        date_only = False
        if not same and normalise_generation_date:
            date_only = same = normalise_generation_date_bytes(bb) == normalise_generation_date_bytes(nb)
        acts[stem] = {
            "identical": same,
            "date_only": date_only,
            "sections": [bc["sections"], nc["sections"]],
            "section_diff": nc["sections"] - bc["sections"],
            "terms": [bc["terms"], nc["terms"]],
            "new_terms": nc["terms"] - bc["terms"],
            "local_refs": [bc["local_refs"], nc["local_refs"]],
            "new_local_refs": nc["local_refs"] - bc["local_refs"],
            "figures": [bc["figures"], nc["figures"]],
            "images": [bc["images"], nc["images"]],
            "figure_drop": nc["figures"] < bc["figures"] or nc["images"] < bc["images"],
            "section_drop": nc["sections"] < bc["sections"],
        }
        dups, empties = eid_problems(nb)
        acts[stem]["duplicate_eids"], acts[stem]["empty_eids"] = dups, empties
        lost = [] if same else lost_text(bb, nb)
        acts[stem]["text_lost"] = len(lost)
        acts[stem]["text_lost_examples"] = [t[:120] for t in lost[:3]]
    compared = {k: v for k, v in acts.items() if "missing" not in v}
    summary = {
        "acts_compared": len(compared),
        "acts_missing": sorted(k for k, v in acts.items() if "missing" in v),
        "identical": sum(v["identical"] for v in compared.values()),
        "date_only_differing": sum(v["date_only"] for v in compared.values()),
        "differing": sum(not v["identical"] for v in compared.values()),
        "section_count_mismatches": sorted(k for k, v in compared.items() if v["section_diff"]),
        "section_drops": sorted(k for k, v in compared.items() if v["section_drop"]),
        "text_lost_acts": sorted(k for k, v in compared.items() if v["text_lost"]),
        "duplicate_eid_acts": sorted(k for k, v in compared.items() if v["duplicate_eids"]),
        "empty_eid_acts": sorted(k for k, v in compared.items() if v["empty_eids"]),
        "figure_count_drops": sorted(k for k, v in compared.items() if v["figure_drop"]),
        "total_new_terms": sum(v["new_terms"] for v in compared.values()),
        "total_new_local_refs": sum(v["new_local_refs"] for v in compared.values()),
    }
    return {"summary": summary, "acts": acts}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("baseline_xml_dir", type=Path)
    ap.add_argument("new_xml_dir", type=Path)
    ap.add_argument("--acts-file", type=Path, help="file stems, one per line (default: all in new dir)")
    ap.add_argument("--report", type=Path, default=Path("diff_corpora.json"))
    ap.add_argument(
        "--no-normalise-generation-date",
        action="store_true",
        help="compare raw bytes instead of masking the manifestation Generation date",
    )
    ap.add_argument("--require-identical", action="store_true")
    ap.add_argument(
        "--allow-section-increase",
        action="store_true",
        help="an Act gaining sections is reported but does not fail; a drop always fails",
    )
    args = ap.parse_args(argv)

    names = None
    if args.acts_file:
        names = [ln.strip() for ln in args.acts_file.read_text().splitlines() if ln.strip()]
    result = diff_dirs(
        args.baseline_xml_dir, args.new_xml_dir, names,
        normalise_generation_date=not args.no_normalise_generation_date,
    )
    args.report.write_text(json.dumps(result, indent=2))
    s = result["summary"]
    print(
        f"compared={s['acts_compared']} identical={s['identical']} (date_only={s['date_only_differing']}) differing={s['differing']} "
        f"missing={len(s['acts_missing'])} figure_drops={len(s['figure_count_drops'])} section_mismatches={len(s['section_count_mismatches'])} "
        f"new_terms={s['total_new_terms']} new_local_refs={s['total_new_local_refs']}"
    )
    for k in s["figure_count_drops"][:20]:
        print(f"  figure/image count dropped: {k} figures={result['acts'][k]['figures']} images={result['acts'][k]['images']}")
    for k in s["section_count_mismatches"][:20]:
        print(f"  section mismatch: {k} {result['acts'][k]['sections']}")
    for k in s["text_lost_acts"][:20]:
        print(f"  text lost: {k} {result['acts'][k]['text_lost']} paragraph(s), e.g. {result['acts'][k]['text_lost_examples'][0]!r}")
    for k in s["duplicate_eid_acts"][:20] + s["empty_eid_acts"][:20]:
        print(f"  eId problem: {k} duplicates={result['acts'][k]['duplicate_eids']} empty={result['acts'][k]['empty_eids']}")
    section_fail = s["section_drops"] if args.allow_section_increase else s["section_count_mismatches"]
    fail = (
        bool(section_fail)
        or bool(s["figure_count_drops"])
        or bool(s["text_lost_acts"])
        or bool(s["duplicate_eid_acts"])
        or bool(s["empty_eid_acts"])
        or (args.require_identical and s["differing"] > 0)
    )
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
