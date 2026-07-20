#!/usr/bin/env python3
"""Phase 1 prerequisite: build the .doc-format failure population and pick
the 30-Act stratified sample for scripts/spike_doc_conversion.py.

Reads corpus/reports/ingest-remaining-20260713.log (the 2026-07-13/14
4,230-Act expansion run), the ground-truth source for the 1,796
`.doc`-format failures per
docs/superpowers/specs/2026-07-20-legacy-doc-format-parsing-design.md.

Usage:
    python scripts/select_doc_conversion_sample.py [--corpus-dir corpus]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from lexau.crawler import _parse_year_from_name

_LOW_VALUE_RE = re.compile(
    r"Amendment|Statute Law Revision|Repeal|Consequential|Transitional|Miscellaneous",
    re.IGNORECASE,
)


def _parse_doc_failures(log_path: Path) -> list[str]:
    lines = log_path.read_text().splitlines()
    names = []
    for i, line in enumerate(lines):
        if line == "  SKIP -- DOCX download failed":
            m = re.match(r"^\[fetch \] (.+)$", lines[i - 1])
            if m:
                names.append(m.group(1))
    return names


def _era(name: str) -> str:
    try:
        year = _parse_year_from_name(name)
    except ValueError:
        return "unknown"
    if year < 1970:
        return "pre-1970"
    if year < 2000:
        return "1970s-90s"
    return "2000s+"


def _stratified_pick(names: list[str], n: int) -> list[str]:
    """Deterministic even-stride sample over the sorted population, so
    re-running this script reproduces the same sample."""
    ordered = sorted(names)
    if len(ordered) <= n:
        return ordered
    stride = len(ordered) / n
    return [ordered[int(i * stride)] for i in range(n)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-dir", default="corpus", type=Path)
    args = ap.parse_args()

    log_path = args.corpus_dir / "reports" / "ingest-remaining-20260713.log"
    names = _parse_doc_failures(log_path)
    print(f"Found {len(names)} '.doc'-format failures (expect 1,796)")

    low_value = [n for n in names if _LOW_VALUE_RE.search(n)]
    substantive = [n for n in names if not _LOW_VALUE_RE.search(n)]
    print(f"  low-value:   {len(low_value)} (expect 1,586)")
    print(f"  substantive: {len(substantive)} (expect 210)")

    by_era: dict[str, list[str]] = {"pre-1970": [], "1970s-90s": [], "2000s+": [], "unknown": []}
    for n in substantive:
        by_era[_era(n)].append(n)

    sample = []
    for era in ("pre-1970", "1970s-90s", "2000s+"):
        for n in _stratified_pick(by_era[era], 5):
            sample.append({"act_name": n, "category": "substantive", "era": era})

    for n in _stratified_pick(low_value, 15):
        sample.append({"act_name": n, "category": "low-value", "era": None})

    print(f"\nSample: {len(sample)} Acts (expect 30)")
    for row in sample:
        print(f"  [{row['category']:<11}] {row['era'] or '-':<10} {row['act_name']}")

    out_path = args.corpus_dir / "reports" / "doc-conversion-sample.json"
    out_path.write_text(json.dumps({
        "total_doc_failures": len(names),
        "low_value_count": len(low_value),
        "substantive_count": len(substantive),
        "substantive_titles": sorted(substantive),
        "sample": sample,
    }, indent=2, ensure_ascii=False))
    print(f"\nWritten to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
