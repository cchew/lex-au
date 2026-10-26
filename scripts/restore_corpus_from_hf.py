"""Restore the published corpus from the Hugging Face dataset into an empty
local directory, pinned to one revision and verified file by file.

Run at the start of every scheduled workflow -- corpus/ is gitignored and
untracked, so a fresh checkout has nothing to diff or update against until
this runs.

Why it is this strict (2026-10-25 incident): stale files left in corpus/ by
a git checkout survived a rate-limited snapshot_download ("Couldn't access
the Hub ... Defaulting to existing file"), an existence-only check passed,
and export-hf pushed them back over 2,260 XML + 909 reports. So:

- the target must be empty (nothing pre-existing can survive the restore);
- the remote head sha is resolved once and every file comes from it;
- after download every file is checked against that revision's tree (LFS
  sha256 or git blob sha1); mismatches are deleted and re-fetched with
  backoff, and the script exits non-zero if any remain.

On success writes .hf-sync-stamp.json with the pinned sha. `lexau export-hf`
refuses to publish unless that sha is still the remote head.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download
from huggingface_hub.utils import filter_repo_objects

from lexau import hfsync

SYNC_STAMP = ".hf-sync-stamp.json"
MAX_ATTEMPTS = 5
MAX_WORKERS = 4  # default 8 trips HF 429s on an 11k-file snapshot
BACKOFF_SECONDS = 30


def _write_sync_stamp(repo: str, local_dir: Path, sha: str, file_count: int,
                      allow_patterns: list[str] | None) -> None:
    stamp = {
        "repo": repo,
        "repo_type": "dataset",
        "restored_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "remote_sha": sha,
        "file_count": file_count,
    }
    if allow_patterns:
        # A partial restore must never drive a publish (its "missing" files
        # would look like deletions); export-hf refuses stamps carrying this.
        stamp["allow_patterns"] = allow_patterns
    (local_dir / SYNC_STAMP).write_text(json.dumps(stamp, indent=2) + "\n")


def _is_empty(path: Path) -> bool:
    return not path.exists() or not any(path.iterdir())


def restore(repo: str, local_dir: str, sleep=time.sleep, api=None,
            allow_patterns: list[str] | None = None) -> str:
    target = Path(local_dir)
    if not _is_empty(target):
        raise RuntimeError(
            f"{target} is not empty. Restore only into an empty directory so no "
            "pre-existing file can survive a rate-limited download."
        )
    api = api or HfApi()

    sha: str | None = None
    remote: dict[str, hfsync.RemoteFile] | None = None
    last_error = "unknown"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            if sha is None:
                sha = api.repo_info(repo_id=repo, repo_type="dataset").sha
                if not sha:
                    raise RuntimeError(f"could not resolve head sha for {repo}")
            if remote is None:
                remote = hfsync.remote_files(api, repo, sha)
                if allow_patterns:
                    keep = set(filter_repo_objects(list(remote), allow_patterns=allow_patterns))
                    remote = {p: rf for p, rf in remote.items() if p in keep}
            kwargs = dict(
                repo_id=repo,
                repo_type="dataset",
                revision=sha,
                local_dir=str(target),
                max_workers=MAX_WORKERS,
            )
            if allow_patterns:
                kwargs["allow_patterns"] = allow_patterns
            snapshot_download(**kwargs)
            problems = hfsync.verify_against_remote(target, remote)
            if not problems:
                _write_sync_stamp(repo, target, sha, len(remote), allow_patterns)
                return str(target)
            # Delete every bad file so the next attempt re-fetches it instead
            # of "defaulting to existing file" again.
            for path, _reason in problems:
                (target / path).unlink(missing_ok=True)
            sample = [f"{p}: {r}" for p, r in problems[:3]]
            last_error = f"{len(problems)} files missing or mismatched, e.g. {sample}"
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
    parser.add_argument(
        "--allow-patterns", nargs="+", default=None,
        help="Restore only matching paths (testing). The stamp is marked partial "
             "and export-hf will refuse to publish from it.",
    )
    args = parser.parse_args()

    path = restore(args.repo, args.local_dir, allow_patterns=args.allow_patterns)
    print(f"Restored corpus from {args.repo} -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
