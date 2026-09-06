"""Restore the published corpus from the Hugging Face dataset into a
local directory.

Run at the start of every scheduled workflow -- corpus/ is entirely
gitignored, so a fresh checkout has nothing to diff or update against
until this runs.

Also writes a sync stamp (.hf-sync-stamp.json) into the local dir. That
stamp is what `lexau export-hf` checks before it reconciles remote
deletions: a stale or absent stamp means the local corpus may be missing
Acts the pipeline has since added straight to HF, so export-hf must not
treat them as "deleted locally" and remove them from the dataset.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download

SYNC_STAMP = ".hf-sync-stamp.json"


def _write_sync_stamp(repo: str, local_dir: str) -> None:
    try:
        remote_sha = HfApi().repo_info(repo_id=repo, repo_type="dataset").sha
    except Exception as exc:  # noqa: BLE001 - sha is diagnostic only, never block a restore on it
        print(f"Warning: could not read remote sha for stamp ({exc})", file=sys.stderr)
        remote_sha = None
    stamp = {
        "repo": repo,
        "repo_type": "dataset",
        "restored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "remote_sha": remote_sha,
    }
    target = Path(local_dir)
    target.mkdir(parents=True, exist_ok=True)
    (target / SYNC_STAMP).write_text(json.dumps(stamp, indent=2) + "\n")


def restore(repo: str, local_dir: str) -> str:
    path = snapshot_download(repo_id=repo, repo_type="dataset", local_dir=local_dir)
    _write_sync_stamp(repo, local_dir)
    return path


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
