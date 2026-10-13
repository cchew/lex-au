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
import time
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download

SYNC_STAMP = ".hf-sync-stamp.json"
MAX_ATTEMPTS = 5
MAX_WORKERS = 4  # default 8 trips HF 429s on an 11k-file snapshot
BACKOFF_SECONDS = 30


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


def _missing_files(repo: str, local_dir: str) -> list[str]:
    remote = HfApi().list_repo_files(repo_id=repo, repo_type="dataset")
    root = Path(local_dir)
    return [f for f in remote if not (root / f).is_file()]


def restore(repo: str, local_dir: str, sleep=time.sleep) -> str:
    """Download the snapshot, retrying (downloads resume) and then verifying
    every remote file is present locally. A rate-limited partial restore
    must fail here, not surface later as a bogus verify-gate failure."""
    last_error: str = "unknown"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            path = snapshot_download(
                repo_id=repo,
                repo_type="dataset",
                local_dir=local_dir,
                max_workers=MAX_WORKERS,
            )
            missing = _missing_files(repo, local_dir)
            if not missing:
                _write_sync_stamp(repo, local_dir)
                return path
            last_error = f"{len(missing)} files missing, e.g. {missing[:3]}"
        except Exception as exc:  # noqa: BLE001 - retry any transport failure
            last_error = str(exc)
        print(f"Restore attempt {attempt}/{MAX_ATTEMPTS} incomplete: {last_error}", file=sys.stderr)
        if attempt < MAX_ATTEMPTS:
            sleep(BACKOFF_SECONDS * attempt)
    raise RuntimeError(f"Corpus restore failed after {MAX_ATTEMPTS} attempts: {last_error}")


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
