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
- every downloaded file is checked against that revision's tree (LFS
  sha256 or git blob sha1); mismatches are deleted and re-fetched, and a
  final full check runs before the stamp is written.

Bulk path (2026-10-27): a shallow git fetch of the pinned sha plus a
batched `git lfs pull` brings the whole dataset down in ~4 min without
per-file resolver requests. Its output is verified like everything else;
whatever fails verification (or everything, if git is unavailable) goes to
the per-file loop below. --no-git skips it.

Rate limits: every per-file download costs HF "resolvers" requests
(5,000 per 5 minutes with a token, less anonymously), so the ~11.4k-file
corpus cannot finish inside one window. The per-file loop works in
passes: each pass fetches only files not yet verified (progress is
monotone), stops early on a 429, waits for the window to reset (RateLimit
/ Retry-After header, else 300 s) and resumes, until a wall-clock budget
(default 60 min, --budget-minutes or LEXAU_RESTORE_BUDGET_MINUTES) is spent.
Only then does it exit non-zero.

On success writes .hf-sync-stamp.json with the pinned sha. `lexau export-hf`
refuses to publish unless that sha is still the remote head.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from huggingface_hub import HfApi, hf_hub_download
from huggingface_hub.utils import filter_repo_objects

try:  # huggingface_hub >= 1.x
    from huggingface_hub.utils import parse_ratelimit_headers
except ImportError:  # pragma: no cover - older hub: fall back to Retry-After / window
    def parse_ratelimit_headers(_headers):
        return None

from lexau import hfsync

SYNC_STAMP = ".hf-sync-stamp.json"
MAX_WORKERS = 4
DEFAULT_BUDGET_MINUTES = 60.0
RATE_LIMIT_WINDOW_SECONDS = 300  # HF's fixed window when no header says otherwise
ERROR_BACKOFF_SECONDS = 30  # non-rate-limit transport failures


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


def rate_limit_wait(exc: BaseException) -> float | None:
    """Seconds to wait if exc (or anything it wraps) is an HF 429, else None.
    hf_hub_download raises LocalEntryNotFoundError *from* the HfHubHTTPError,
    so walk the cause chain for a response."""
    seen = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        response = getattr(cur, "response", None)
        if response is not None and getattr(response, "status_code", None) == 429:
            headers = getattr(response, "headers", None) or {}
            info = parse_ratelimit_headers(headers)
            if info is not None:
                return float(info.reset_in_seconds) + 1
            for key in headers:
                if key.lower() == "retry-after":
                    try:
                        return float(headers[key]) + 1
                    except (TypeError, ValueError):
                        break
            return float(RATE_LIMIT_WINDOW_SECONDS)
        text = str(cur)
        if response is None and ("429" in text or "rate limit" in text.lower()):
            return float(RATE_LIMIT_WINDOW_SECONDS)
        cur = cur.__cause__ or cur.__context__
    return None


def git_bulk_fetch(repo: str, sha: str, target: Path,
                   include: list[str] | None = None) -> None:
    """Fetch the whole repo at `sha` into the empty `target` with one shallow
    git fetch plus a batched `git lfs pull`, then drop .git.

    Measured 2026-10-27 at ce532dde: 221 s, no 429s (git pack + LFS batch
    API, not one resolver request per file) vs 2,754 s for the per-file
    loop. Nothing it writes is trusted: restore() verifies every file
    against the tree afterwards and re-fetches mismatches per file. Raises
    on any git failure; .git is removed either way."""
    endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
    env = dict(os.environ, GIT_LFS_SKIP_SMUDGE="1", GIT_TERMINAL_PROMPT="0")
    token = os.environ.get("HF_TOKEN")
    if token:
        # Passed through the environment so it is never written to .git/config.
        env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="http.extraHeader",
                   GIT_CONFIG_VALUE_0=f"Authorization: Bearer {token}")

    def git(*args: str) -> str:
        return subprocess.run(["git", *args], cwd=target, env=env, check=True,
                              capture_output=True, text=True).stdout.strip()

    target.mkdir(parents=True, exist_ok=True)
    try:
        git("init", "-q", ".")
        git("remote", "add", "origin", f"{endpoint}/datasets/{repo}")
        git("fetch", "-q", "--depth", "1", "origin", sha)
        git("checkout", "-q", "FETCH_HEAD")
        head = git("rev-parse", "HEAD")
        if head != sha:
            raise RuntimeError(f"git checked out {head}, not the pinned {sha}")
        lfs = ["lfs", "pull"]
        if include:
            lfs += ["--include", ",".join(include)]
        git(*lfs)
    finally:
        shutil.rmtree(target / ".git", ignore_errors=True)


def _fetch_pass(repo, sha, target, paths, remote, download, workers):
    """Download `paths`, stopping early on the first 429. Returns
    (verified, failed, rate_waits, errors)."""
    stop = threading.Event()
    lock = threading.Lock()
    verified: list[str] = []
    failed: list[str] = []
    waits: list[float] = []
    errors: list[str] = []

    def one(path: str) -> None:
        if stop.is_set():
            return
        try:
            download(repo_id=repo, filename=path, repo_type="dataset",
                     revision=sha, local_dir=str(target))
        except Exception as exc:  # noqa: BLE001 - classified below
            wait = rate_limit_wait(exc)
            with lock:
                if wait is not None:
                    waits.append(wait)
                    stop.set()  # the rest of this pass would only burn the next window
                else:
                    errors.append(f"{path}: {exc}")
            (target / path).unlink(missing_ok=True)
            return
        local = target / path
        ok = local.is_file() and hfsync.matches(local, remote[path])
        if not ok:
            # Delete so the next pass re-fetches it instead of "defaulting
            # to existing file".
            local.unlink(missing_ok=True)
        with lock:
            (verified if ok else failed).append(path)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(one, paths))
    return verified, failed, waits, errors


def restore(repo: str, local_dir: str, sleep=time.sleep, api=None,
            allow_patterns: list[str] | None = None,
            budget_seconds: float = DEFAULT_BUDGET_MINUTES * 60,
            clock=time.monotonic, workers: int = MAX_WORKERS,
            download=None, bulk=git_bulk_fetch) -> str:
    target = Path(local_dir)
    if not _is_empty(target):
        raise RuntimeError(
            f"{target} is not empty. Restore only into an empty directory so no "
            "pre-existing file can survive a rate-limited download."
        )
    api = api or HfApi()
    download = download or hf_hub_download
    deadline = clock() + budget_seconds

    def wait_or_fail(seconds: float, why: str) -> None:
        left = deadline - clock()
        if left <= 0 or seconds > left:
            raise RuntimeError(
                f"Corpus restore failed: {budget_seconds / 60:.0f}-minute budget spent ({why})"
            )
        print(f"  waiting {seconds:.0f}s ({left / 60:.1f} min of budget left)", file=sys.stderr)
        sleep(seconds)

    sha: str | None = None
    remote: dict[str, hfsync.RemoteFile] | None = None
    while remote is None:
        try:
            if sha is None:
                sha = api.repo_info(repo_id=repo, repo_type="dataset").sha
                if not sha:
                    raise RuntimeError(f"could not resolve head sha for {repo}")
            remote = hfsync.remote_files(api, repo, sha)
        except Exception as exc:  # noqa: BLE001
            if "could not resolve head sha" in str(exc):
                raise
            wait = rate_limit_wait(exc)
            print(f"Listing {repo} failed: {exc}", file=sys.stderr)
            wait_or_fail(wait if wait is not None else ERROR_BACKOFF_SECONDS, str(exc))
    if allow_patterns:
        keep = set(filter_repo_objects(list(remote), allow_patterns=allow_patterns))
        remote = {p: rf for p, rf in remote.items() if p in keep}

    print(f"Restoring {len(remote)} files from {repo}@{sha}", file=sys.stderr)
    done: set[str] = set()
    if bulk is not None:
        started = clock()
        try:
            bulk(repo, sha, target, include=allow_patterns)
        except Exception as exc:  # noqa: BLE001 - the per-file loop covers whatever is missing
            detail = getattr(exc, "stderr", "") or ""
            print(f"git bulk fetch failed, falling back to per-file: {exc} {detail[-500:]}",
                  file=sys.stderr)
        problems = hfsync.verify_against_remote(target, remote)
        bad = {p for p, _reason in problems}
        for path in bad:
            # Pointer files from a failed lfs pull, files outside
            # allow_patterns, anything else: gone before the per-file loop.
            (target / path).unlink(missing_ok=True)
        done = {p for p in remote if p not in bad}
        print(
            f"git bulk fetch: {len(done)}/{len(remote)} verified, {len(bad)} to fetch per file "
            f"({clock() - started:.0f}s)",
            file=sys.stderr,
        )
    pass_no = 0
    while True:
        todo = [p for p in sorted(remote) if p not in done]
        if not todo:
            problems = hfsync.verify_against_remote(target, remote)
            if not problems:
                _write_sync_stamp(repo, target, sha, len(remote), allow_patterns)
                print(f"Verified all {len(remote)} files in {pass_no} pass(es)", file=sys.stderr)
                return str(target)
            # Something changed under us; re-fetch exactly those.
            for path, _reason in problems:
                if path in remote:
                    (target / path).unlink(missing_ok=True)
                    done.discard(path)
                else:
                    raise RuntimeError(f"Corpus restore failed: {path} is not on the remote")
            continue
        pass_no += 1
        verified, failed, waits, errors = _fetch_pass(
            repo, sha, target, todo, remote, download, workers
        )
        done.update(verified)
        print(
            f"Pass {pass_no}: {len(verified)} verified this pass, {len(done)}/{len(remote)} "
            f"total, {len(remote) - len(done)} remaining; {len(failed)} mismatched, "
            f"{len(waits)} rate-limited, {len(errors)} other errors",
            file=sys.stderr,
        )
        if errors:
            print(f"  e.g. {errors[:3]}", file=sys.stderr)
        if len(done) == len(remote):
            continue
        if waits:
            wait_or_fail(max(waits), f"{len(remote) - len(done)} files still missing, rate-limited")
        elif not verified:
            # No progress and no rate limit: back off before trying again.
            sample = (errors or [f"{p}: content differs" for p in failed])[:3]
            wait_or_fail(ERROR_BACKOFF_SECONDS, f"{len(remote) - len(done)} files missing or mismatched, e.g. {sample}")


def _budget_minutes_default() -> float:
    raw = os.environ.get("LEXAU_RESTORE_BUDGET_MINUTES")
    return float(raw) if raw else DEFAULT_BUDGET_MINUTES


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="cchew/lex-au", help="HF dataset repo")
    parser.add_argument("--local-dir", default="corpus")
    parser.add_argument(
        "--allow-patterns", nargs="+", default=None,
        help="Restore only matching paths (testing). The stamp is marked partial "
             "and export-hf will refuse to publish from it.",
    )
    parser.add_argument(
        "--no-git", action="store_true",
        help="Skip the git bulk fetch and download every file individually.",
    )
    parser.add_argument(
        "--budget-minutes", type=float, default=_budget_minutes_default(),
        help="Total wall-clock budget including rate-limit waits "
             "(env LEXAU_RESTORE_BUDGET_MINUTES; default %(default)s).",
    )
    args = parser.parse_args()

    started = time.monotonic()
    path = restore(args.repo, args.local_dir, allow_patterns=args.allow_patterns,
                   budget_seconds=args.budget_minutes * 60,
                   bulk=None if args.no_git else git_bulk_fetch)
    print(f"Restored corpus from {args.repo} -> {path} in {time.monotonic() - started:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
