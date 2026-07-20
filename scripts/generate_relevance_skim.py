#!/usr/bin/env python3
"""Generate the human-fillable relevance-skim template for the 210
substantive .doc-failure titles (Task 1's output). Per the spec: "no
low-value keyword" is a coarse proxy, not a value judgement -- some titles
in this bucket are still plausibly low-value one-offs (e.g. AIDC Sale Act
1997) and need a human relevance call before Phase 2 batches them.

Usage:
    python scripts/generate_relevance_skim.py [--corpus-dir corpus]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-dir", default="corpus", type=Path)
    args = ap.parse_args()

    sample_path = args.corpus_dir / "reports" / "doc-conversion-sample.json"
    titles = json.loads(sample_path.read_text())["substantive_titles"]

    lines = [
        "# Doc-conversion relevance skim",
        "",
        "210 substantive (no low-value-keyword) `.doc`-only Acts. Mark each",
        "`keep` (real current law worth Phase 2 ingestion) or `drop`",
        "(plausibly low-value despite missing the keyword match -- e.g. a",
        "one-off historical Act). Blank `call` = not yet reviewed.",
        "",
        "| # | Act | call | note |",
        "|---|-----|------|------|",
    ]
    for i, title in enumerate(titles, 1):
        lines.append(f"| {i} | {title} | | |")

    out_path = args.corpus_dir / "reports" / "doc-conversion-relevance-skim.md"
    out_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {len(titles)}-row template to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
