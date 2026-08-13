"""Regenerate acts.txt from corpus/index.json's current Act names.

acts.txt is the one corpus-related file tracked in git (everything under
corpus/ itself is gitignored). It drifts whenever Acts are added to the
corpus without a matching acts.txt update -- this script recomputes it
from the corpus's own build manifest so it can't drift.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def regenerate(corpus_dir: Path, output: Path) -> int:
    index_path = corpus_dir / "index.json"
    index = json.loads(index_path.read_text())
    names = sorted(entry["name"] for entry in index.get("acts", {}).values())
    output.write_text("\n".join(names) + "\n" if names else "")
    return len(names)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-dir", type=Path, default=Path("corpus"))
    parser.add_argument("--output", type=Path, default=Path("acts.txt"))
    args = parser.parse_args()

    count = regenerate(args.corpus_dir, args.output)
    print(f"Wrote {count} Act name(s) -> {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
