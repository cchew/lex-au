"""Compare a local corpus directory against a pinned Hugging Face revision.

Used by scripts/restore_corpus_from_hf.py (verify every restored file came
from the pinned revision) and `lexau export-hf` (refuse to upload anything
beyond what this run actually changed).

Background: on 2026-10-25 a scheduled run restored over stale files that a
git checkout had left in corpus/. snapshot_download hit HF 429s, logged
"Defaulting to existing file" and kept them; an existence-only check passed;
upload_large_folder then pushed every stale file back to the dataset. The
fix is to compare content, not existence.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from huggingface_hub.utils import filter_repo_objects

# Local-only paths never present on (or uploaded to) the dataset:
# huggingface_hub's own download/upload metadata and the sync stamp.
LOCAL_ONLY_PATTERNS = [".cache/**", ".hf-sync-stamp.json"]

_CHUNK = 1 << 20


@dataclass(frozen=True)
class RemoteFile:
    path: str
    size: int
    blob_id: str
    lfs_sha256: str | None = None


def remote_files(api, repo: str, revision: str, repo_type: str = "dataset") -> dict[str, RemoteFile]:
    """Every file in the repo at `revision`, keyed by path. The plain tree
    listing already carries each file's git blob id and, for LFS files, the
    LFS sha256, so expand=True (much smaller pages) is not needed."""
    out: dict[str, RemoteFile] = {}
    for entry in api.list_repo_tree(
        repo_id=repo, repo_type=repo_type, revision=revision, recursive=True
    ):
        blob_id = getattr(entry, "blob_id", None)
        if blob_id is None:  # RepoFolder
            continue
        lfs = getattr(entry, "lfs", None)
        out[entry.path] = RemoteFile(
            path=entry.path,
            size=entry.size,
            blob_id=blob_id,
            lfs_sha256=getattr(lfs, "sha256", None) if lfs else None,
        )
    return out


def git_blob_sha1(path: Path) -> str:
    h = hashlib.sha1()
    h.update(f"blob {path.stat().st_size}\0".encode())
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def matches(path: Path, remote: RemoteFile) -> bool:
    """True if the local file's content equals the remote file's."""
    if path.stat().st_size != remote.size:
        return False
    if remote.lfs_sha256:
        return sha256_file(path) == remote.lfs_sha256
    return git_blob_sha1(path) == remote.blob_id


def local_files(root: Path, ignore_patterns: list[str] | None = None) -> list[str]:
    """Posix relative paths of files under root, minus local-only metadata
    and any ignore_patterns."""
    paths = [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]
    ignore = LOCAL_ONLY_PATTERNS + list(ignore_patterns or [])
    return sorted(filter_repo_objects(paths, ignore_patterns=ignore))


def verify_against_remote(root: Path, remote: dict[str, RemoteFile]) -> list[tuple[str, str]]:
    """Problems that make `root` not an exact copy of `remote`, as
    (path, reason) with reason "missing" / "content differs" / "not on remote".
    Empty list means every remote file is present with identical content
    and nothing else is."""
    problems: list[tuple[str, str]] = []
    for path, rf in sorted(remote.items()):
        local = root / path
        if not local.is_file():
            problems.append((path, "missing"))
        elif not matches(local, rf):
            problems.append((path, "content differs"))
    for path in local_files(root):
        if path not in remote:
            problems.append((path, "not on remote"))
    return problems


def changed_files(
    root: Path, remote: dict[str, RemoteFile], ignore_patterns: list[str]
) -> list[str]:
    """Local paths (after ignore_patterns) that are new or differ from remote,
    i.e. what upload_large_folder would upload."""
    out = []
    for path in local_files(root, ignore_patterns):
        rf = remote.get(path)
        if rf is None or not matches(root / path, rf):
            out.append(path)
    return out
