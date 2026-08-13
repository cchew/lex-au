"""Diff the live in-force Act list against the local corpus's index.json,
writing Act names present live but not yet in the corpus.

Deliberately diffs against corpus/index.json (the corpus's own build
manifest) rather than acts.txt -- acts.txt is a separately-maintained
file that has already been found to drift from the real corpus.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def compute_new_acts(live_acts_path: Path, corpus_dir: Path) -> list[str]:
    live_names = {
        line.strip() for line in live_acts_path.read_text().splitlines() if line.strip()
    }
    index_path = corpus_dir / "index.json"
    corpus_names: set[str] = set()
    if index_path.exists():
        index = json.loads(index_path.read_text())
        corpus_names = {entry["name"] for entry in index.get("acts", {}).values()}
    return sorted(live_names - corpus_names)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-acts", type=Path, required=True,
                         help="Path to lexau list-acts output, one Act name per line")
    parser.add_argument("--corpus-dir", type=Path, default=Path("corpus"))
    parser.add_argument("--output", type=Path, required=True,
                         help="Where to write new candidate Act names, one per line")
    args = parser.parse_args()

    new_acts = compute_new_acts(args.live_acts, args.corpus_dir)
    args.output.write_text("\n".join(new_acts) + "\n" if new_acts else "")
    print(f"Found {len(new_acts)} new Act(s) not yet in the corpus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
