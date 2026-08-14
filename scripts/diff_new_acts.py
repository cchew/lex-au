"""Diff the live in-force Act list against the local corpus's index.json,
writing Act names present live but not yet in the corpus.

Deliberately diffs against corpus/index.json (the corpus's own build
manifest) rather than acts.txt -- acts.txt is a separately-maintained
file that has already been found to drift from the real corpus.

Two deliberate exclusion mechanisms keep permanently-dropped Acts (already
folded into whatever principal Act they amend, by AU drafting convention)
from resurfacing as growth candidates: a regex applied dynamically to every
run's live list (amending/repeal/consequential-style titles), and a static
file of individually-reviewed substantive-sounding titles with no shared
pattern.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

LOW_VALUE_TITLE_PATTERN = re.compile(
    r"Amendment|Statute Law Revision|Repeal|Consequential|Transitional|Miscellaneous",
    re.IGNORECASE,
)


def compute_new_acts(
    live_acts_path: Path,
    corpus_dir: Path,
    limit: int | None = None,
    exclude_titles_path: Path | None = None,
) -> list[str]:
    live_names = {
        line.strip() for line in live_acts_path.read_text().splitlines() if line.strip()
    }
    index_path = corpus_dir / "index.json"
    corpus_names: set[str] = set()
    if index_path.exists():
        index = json.loads(index_path.read_text())
        corpus_names = {entry["name"] for entry in index.get("acts", {}).values()}

    exclude_titles: set[str] = set()
    if exclude_titles_path is not None and exclude_titles_path.exists():
        exclude_titles = {
            line.strip()
            for line in exclude_titles_path.read_text().splitlines()
            if line.strip()
        }

    new_acts = live_names - corpus_names
    new_acts = {name for name in new_acts if not LOW_VALUE_TITLE_PATTERN.search(name)}
    new_acts = new_acts - exclude_titles
    new_acts = sorted(new_acts)
    if limit is not None:
        new_acts = new_acts[:limit]
    return new_acts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-acts", type=Path, required=True,
                         help="Path to lexau list-acts output, one Act name per line")
    parser.add_argument("--corpus-dir", type=Path, default=Path("corpus"))
    parser.add_argument("--output", type=Path, required=True,
                         help="Where to write new candidate Act names, one per line")
    parser.add_argument("--limit", type=int, default=None,
                         help="Cap the number of candidate Act names returned (no cap "
                              "unless set; growth-check.yml's pre-build candidate diff "
                              "passes --limit 20)")
    parser.add_argument("--exclude-titles", type=Path,
                         default=Path("docs/corpus-exclusions-drop-titles.txt"),
                         help="Path to a file of individually-reviewed Act titles to "
                              "exclude, one per line (Category 2 of the corpus "
                              "exclusions policy). Missing file is treated as no "
                              "additional exclusions.")
    args = parser.parse_args()

    new_acts = compute_new_acts(
        args.live_acts, args.corpus_dir, limit=args.limit,
        exclude_titles_path=args.exclude_titles,
    )
    args.output.write_text("\n".join(new_acts) + "\n" if new_acts else "")
    print(f"Found {len(new_acts)} new Act(s) not yet in the corpus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
