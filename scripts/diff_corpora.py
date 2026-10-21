"""Compare two corpus xml dirs: byte identity, section counts, term and local-term counts."""
from __future__ import annotations

import argparse
import json
import re
import sys
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
    }


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
        }
    compared = {k: v for k, v in acts.items() if "missing" not in v}
    summary = {
        "acts_compared": len(compared),
        "acts_missing": sorted(k for k, v in acts.items() if "missing" in v),
        "identical": sum(v["identical"] for v in compared.values()),
        "date_only_differing": sum(v["date_only"] for v in compared.values()),
        "differing": sum(not v["identical"] for v in compared.values()),
        "section_count_mismatches": sorted(k for k, v in compared.items() if v["section_diff"]),
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
        f"missing={len(s['acts_missing'])} section_mismatches={len(s['section_count_mismatches'])} "
        f"new_terms={s['total_new_terms']} new_local_refs={s['total_new_local_refs']}"
    )
    for k in s["section_count_mismatches"][:20]:
        print(f"  section mismatch: {k} {result['acts'][k]['sections']}")
    fail = bool(s["section_count_mismatches"]) or (args.require_identical and s["differing"] > 0)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
