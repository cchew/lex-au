"""Restore the published corpus from the Hugging Face dataset into a
local directory.

Run at the start of every scheduled workflow -- corpus/ is entirely
gitignored, so a fresh checkout has nothing to diff or update against
until this runs.
"""
from __future__ import annotations

import argparse
import sys

from huggingface_hub import snapshot_download


def restore(repo: str, local_dir: str) -> str:
    return snapshot_download(repo_id=repo, repo_type="dataset", local_dir=local_dir)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="cchew/lex-au", help="HF dataset repo")
    parser.add_argument("--local-dir", default="corpus")
    args = parser.parse_args()

    path = restore(args.repo, args.local_dir)
    print(f"Restored corpus from {args.repo} -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
