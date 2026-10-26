import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "restore_corpus_from_hf",
        Path(__file__).parent.parent / "scripts" / "restore_corpus_from_hf.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SHA = "c0ffee" * 6 + "abcd"


def _blob_id(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _entry(path: str, data: bytes, lfs: bool = False):
    if lfs:
        # Real LFS entries: blob_id is the sha1 of the *pointer* file, so only
        # the sha256 can confirm the content.
        pointer = b"version https://git-lfs.github.com/spec/v1\noid sha256:%s\n" % (
            hashlib.sha256(data).hexdigest().encode()
        )
        return SimpleNamespace(path=path, size=len(data), blob_id=_blob_id(pointer),
                               lfs=SimpleNamespace(sha256=hashlib.sha256(data).hexdigest()))
    return SimpleNamespace(path=path, size=len(data), blob_id=_blob_id(data), lfs=None)


REMOTE = {
    "index.json": b'{"acts": {}}',
    "xml/a.xml": b"<akn>fresh</akn>",
    "images/a-fig-1.png": b"\x89PNG fresh",
}


class FakeApi:
    def __init__(self, remote=REMOTE, sha=SHA, lfs=("images/a-fig-1.png",)):
        self.remote = remote
        self.sha = sha
        self.lfs = set(lfs)
        self.tree_calls = []

    def repo_info(self, **_):
        return SimpleNamespace(sha=self.sha)

    def list_repo_tree(self, **kwargs):
        self.tree_calls.append(kwargs)
        return [_entry(p, d, p in self.lfs) for p, d in self.remote.items()]


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class RateLimited(Exception):
    def __init__(self, headers):
        super().__init__("429 Too Many Requests")
        self.response = SimpleNamespace(status_code=429, headers=headers)


def _downloader(remote=REMOTE, calls=None, content=None, fail=None):
    """hf_hub_download stand-in. content(path, n) overrides the bytes written
    on the n-th request for path; fail(path, n) may return an exception."""
    counts = {}

    def download(*, repo_id, filename, repo_type, revision, local_dir):
        n = counts[filename] = counts.get(filename, 0) + 1
        if calls is not None:
            calls.append(dict(repo_id=repo_id, filename=filename, repo_type=repo_type,
                              revision=revision, local_dir=local_dir))
        if fail is not None:
            exc = fail(filename, n)
            if exc is not None:
                raise exc
        target = Path(local_dir) / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        data = content(filename, n) if content else None
        target.write_bytes(remote[filename] if data is None else data)
        meta = Path(local_dir) / ".cache" / "huggingface" / "download" / f"{filename}.metadata"
        meta.parent.mkdir(parents=True, exist_ok=True)
        meta.write_text(revision)
        return str(target)

    return download


def _restore(module, local, clock=None, **kwargs):
    clock = clock or FakeClock()
    kwargs.setdefault("api", FakeApi())
    kwargs.setdefault("workers", 1)
    kwargs.setdefault("bulk", None)
    return module.restore("cchew/lex-au", str(local), sleep=clock.sleep, clock=clock, **kwargs)


def test_restore_pins_revision_and_writes_stamp(tmp_path):
    module = _load_module()
    api = FakeApi()
    calls = []
    local = tmp_path / "corpus"

    _restore(module, local, api=api, download=_downloader(calls=calls))

    assert sorted(c["filename"] for c in calls) == sorted(REMOTE)
    assert {c["revision"] for c in calls} == {SHA}
    assert {c["local_dir"] for c in calls} == {str(local)}
    assert api.tree_calls[0]["revision"] == SHA
    stamp = json.loads((local / ".hf-sync-stamp.json").read_text())
    assert stamp["repo"] == "cchew/lex-au"
    assert stamp["remote_sha"] == SHA
    assert stamp["file_count"] == len(REMOTE)


def test_restore_ignores_hf_cache_metadata(tmp_path):
    """hf_hub_download writes .cache/huggingface/ under local_dir; it is not
    on the remote and must not fail the final "not on remote" check."""
    module = _load_module()
    local = tmp_path / "corpus"
    _restore(module, local, download=_downloader())
    assert (local / ".cache" / "huggingface").is_dir()
    assert (local / ".hf-sync-stamp.json").exists()


def test_restore_refuses_non_empty_target(tmp_path):
    module = _load_module()
    local = tmp_path / "corpus"
    (local / "xml").mkdir(parents=True)
    (local / "xml" / "a.xml").write_text("stale")
    calls = []

    with pytest.raises(RuntimeError, match="not empty"):
        _restore(module, local, download=_downloader(calls=calls))
    assert calls == []


def test_restore_allows_existing_empty_dir(tmp_path):
    module = _load_module()
    local = tmp_path / "corpus"
    local.mkdir()
    _restore(module, local, download=_downloader())
    assert (local / "xml" / "a.xml").read_bytes() == REMOTE["xml/a.xml"]


def test_restore_fails_closed_when_stale_xml_persists(tmp_path):
    """The 2026-10-25 failure mode: the download "succeeds" but leaves the
    wrong bytes. Content verification must catch it; no stamp after the
    budget is spent."""
    module = _load_module()
    local = tmp_path / "corpus"
    stale = lambda p, n: b"STALE " + REMOTE[p] if p == "xml/a.xml" else None  # noqa: E731

    with pytest.raises(RuntimeError, match="budget spent"):
        _restore(module, local, download=_downloader(content=stale), budget_seconds=600)
    assert not (local / ".hf-sync-stamp.json").exists()
    assert not (local / "xml" / "a.xml").exists()  # bad copy deleted


def test_restore_rejects_same_size_stale_lfs_content(tmp_path):
    """Only the LFS sha256 can tell these apart: same size, and the tree's
    blob_id is the pointer's sha1, not the content's."""
    module = _load_module()
    local = tmp_path / "corpus"
    real = REMOTE["images/a-fig-1.png"]
    stale = lambda p, n: b"\x89PNG stale" if p == "images/a-fig-1.png" else None  # noqa: E731
    assert len(b"\x89PNG stale") == len(real)

    with pytest.raises(RuntimeError, match="budget spent"):
        _restore(module, local, download=_downloader(content=stale), budget_seconds=600)
    assert not (local / ".hf-sync-stamp.json").exists()


def test_restore_rejects_same_size_stale_git_blob(tmp_path):
    module = _load_module()
    local = tmp_path / "corpus"
    real = REMOTE["xml/a.xml"]
    stale = lambda p, n: b"<akn>stale</akn>" if p == "xml/a.xml" else None  # noqa: E731
    assert len(b"<akn>stale</akn>") == len(real)

    with pytest.raises(RuntimeError, match="budget spent"):
        _restore(module, local, download=_downloader(content=stale), budget_seconds=600)
    assert not (local / ".hf-sync-stamp.json").exists()


def test_restore_deletes_mismatch_and_refetches_only_it(tmp_path):
    module = _load_module()
    local = tmp_path / "corpus"
    calls = []
    corrupt = lambda p, n: b"truncated" if (p, n) == ("images/a-fig-1.png", 1) else None  # noqa: E731

    _restore(module, local, download=_downloader(calls=calls, content=corrupt))

    names = [c["filename"] for c in calls]
    assert names.count("images/a-fig-1.png") == 2
    assert names.count("xml/a.xml") == 1  # verified files are never re-requested
    assert (local / "images/a-fig-1.png").read_bytes() == REMOTE["images/a-fig-1.png"]
    assert (local / ".hf-sync-stamp.json").exists()


def test_restore_deletes_bad_file_before_refetch(tmp_path):
    """A real hf_hub_download "defaults to existing file" if one is on disk,
    so a mismatch must be deleted before the next pass asks again."""
    module = _load_module()
    local = tmp_path / "corpus"
    seen_on_disk = []
    inner = _downloader(content=lambda p, n: b"bad" if (p, n) == ("xml/a.xml", 1) else None)

    def download(**kw):
        if kw["filename"] == "xml/a.xml":
            seen_on_disk.append((Path(kw["local_dir"]) / kw["filename"]).exists())
        return inner(**kw)

    _restore(module, local, download=download)
    assert seen_on_disk == [False, False]


def test_restore_honours_ratelimit_header_and_resumes(tmp_path):
    module = _load_module()
    local = tmp_path / "corpus"
    calls = []
    clock = FakeClock()
    headers = {"RateLimit": '"resolvers";r=0;t=120', "RateLimit-Policy": '"fixed window";"resolvers";q=5000;w=300'}
    fail = lambda p, n: RateLimited(headers) if (p, n) == ("index.json", 1) else None  # noqa: E731

    _restore(module, local, clock=clock, download=_downloader(calls=calls, fail=fail))

    assert clock.sleeps == [121.0]
    names = [c["filename"] for c in calls]
    # sorted order: images/, index.json, xml/ -- the 429 on index.json stops
    # the pass before xml/a.xml is requested; the next pass skips images/.
    assert names == ["images/a-fig-1.png", "index.json", "index.json", "xml/a.xml"]
    assert (local / ".hf-sync-stamp.json").exists()


def test_restore_honours_retry_after_wrapped_in_cause(tmp_path):
    """hf_hub_download raises LocalEntryNotFoundError from the HTTP error."""
    module = _load_module()
    clock = FakeClock()

    def fail(p, n):
        if (p, n) == ("xml/a.xml", 1):
            try:
                raise RateLimited({"Retry-After": "42"})
            except RateLimited as inner:
                outer = RuntimeError("An error happened while trying to locate the file")
                outer.__cause__ = inner
                return outer
        return None

    _restore(module, tmp_path / "corpus", clock=clock, download=_downloader(fail=fail))
    assert clock.sleeps == [43.0]


def test_restore_waits_full_window_when_no_header(tmp_path):
    module = _load_module()
    clock = FakeClock()
    fail = lambda p, n: RateLimited({}) if (p, n) == ("xml/a.xml", 1) else None  # noqa: E731
    _restore(module, tmp_path / "corpus", clock=clock, download=_downloader(fail=fail))
    assert clock.sleeps == [module.RATE_LIMIT_WINDOW_SECONDS]


def test_restore_rides_out_many_windows_within_budget(tmp_path):
    """11.4k files cannot fit one 5,000-resolver window: several 429 waits
    in a row are normal and must not fail the restore."""
    module = _load_module()
    clock = FakeClock()
    fail = lambda p, n: RateLimited({}) if p == "xml/a.xml" and n <= 6 else None  # noqa: E731
    _restore(module, tmp_path / "corpus", clock=clock, download=_downloader(fail=fail))
    assert clock.sleeps == [300.0] * 6
    assert (tmp_path / "corpus" / ".hf-sync-stamp.json").exists()


def test_restore_fails_when_budget_spent_on_rate_limits(tmp_path):
    module = _load_module()
    clock = FakeClock()
    fail = lambda p, n: RateLimited({}) if p == "xml/a.xml" else None  # noqa: E731
    with pytest.raises(RuntimeError, match="10-minute budget spent"):
        _restore(module, tmp_path / "corpus", clock=clock,
                 download=_downloader(fail=fail), budget_seconds=600)
    assert sum(clock.sleeps) <= 600
    assert not (tmp_path / "corpus" / ".hf-sync-stamp.json").exists()


def test_restore_retries_transport_errors(tmp_path):
    module = _load_module()
    clock = FakeClock()
    fail = lambda p, n: ConnectionError("reset") if n < 3 else None  # noqa: E731
    _restore(module, tmp_path / "corpus", clock=clock, download=_downloader(fail=fail))
    assert clock.sleeps == [module.ERROR_BACKOFF_SECONDS] * 2


def test_restore_fails_without_remote_sha(tmp_path):
    module = _load_module()
    with pytest.raises(RuntimeError, match="head sha"):
        _restore(module, tmp_path / "corpus", api=FakeApi(sha=None), download=_downloader())


def test_restore_allow_patterns_limits_download_and_verification(tmp_path):
    module = _load_module()
    calls = []
    local = tmp_path / "corpus"
    _restore(module, local, download=_downloader(calls=calls), allow_patterns=["xml/*"])
    assert [c["filename"] for c in calls] == ["xml/a.xml"]
    stamp = json.loads((local / ".hf-sync-stamp.json").read_text())
    assert stamp["file_count"] == 1
    assert stamp["allow_patterns"] == ["xml/*"]


def test_rate_limit_wait_ignores_other_errors():
    module = _load_module()
    assert module.rate_limit_wait(ConnectionError("reset")) is None
    err = Exception("boom")
    err.response = SimpleNamespace(status_code=500, headers={})
    assert module.rate_limit_wait(err) is None


def _bulk_writer(files):
    """git_bulk_fetch stand-in: writes `files` (path -> bytes) into target."""
    def bulk(repo, sha, target, include=None):
        assert sha == SHA
        for path, data in files.items():
            dest = Path(target) / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
    return bulk


def test_bulk_fetch_output_is_verified_and_only_bad_files_refetched(tmp_path):
    """A git checkout whose lfs pull failed leaves pointer files; an extra
    file not on the remote must not survive either."""
    module = _load_module()
    local = tmp_path / "corpus"
    calls = []
    seen_on_disk = []
    inner = _downloader(calls=calls)

    def download(**kw):
        seen_on_disk.append((Path(kw["local_dir"]) / kw["filename"]).exists())
        return inner(**kw)

    bulk = _bulk_writer({
        "index.json": REMOTE["index.json"],
        "xml/a.xml": REMOTE["xml/a.xml"],
        "images/a-fig-1.png": b"version https://git-lfs.github.com/spec/v1\n",  # pointer
        "xml/extra.xml": b"<akn>not on remote</akn>",
    })
    _restore(module, local, bulk=bulk, download=download)

    assert [c["filename"] for c in calls] == ["images/a-fig-1.png"]
    assert seen_on_disk == [False]  # pointer deleted before the per-file fetch
    assert not (local / "xml/extra.xml").exists()
    assert (local / "images/a-fig-1.png").read_bytes() == REMOTE["images/a-fig-1.png"]
    assert (local / ".hf-sync-stamp.json").exists()


def test_bulk_fetch_failure_falls_back_to_per_file(tmp_path):
    module = _load_module()
    calls = []

    def broken(repo, sha, target, include=None):
        raise RuntimeError("git: command not found")

    _restore(module, tmp_path / "corpus", bulk=broken, download=_downloader(calls=calls))
    assert sorted(c["filename"] for c in calls) == sorted(REMOTE)


def test_bulk_fetch_complete_needs_no_per_file_requests(tmp_path):
    module = _load_module()
    calls = []
    _restore(module, tmp_path / "corpus", bulk=_bulk_writer(REMOTE), download=_downloader(calls=calls))
    assert calls == []
    assert (tmp_path / "corpus" / ".hf-sync-stamp.json").exists()


def test_git_bulk_fetch_pins_sha_and_removes_git_dir(monkeypatch, tmp_path):
    module = _load_module()
    commands = []

    def fake_run(cmd, cwd, env, **_):
        commands.append(cmd[1:])
        (Path(cwd) / ".git").mkdir(exist_ok=True)
        out = SHA if cmd[1] == "rev-parse" else ""
        assert "Bearer" not in " ".join(cmd)  # token only via env
        return SimpleNamespace(stdout=out)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setenv("HF_TOKEN", "hf_secret")
    module.git_bulk_fetch("cchew/lex-au", SHA, tmp_path / "corpus", include=["xml/*"])

    assert ["fetch", "-q", "--depth", "1", "origin", SHA] in commands
    assert ["lfs", "pull", "--include", "xml/*"] in commands
    assert not (tmp_path / "corpus" / ".git").exists()


def test_git_bulk_fetch_rejects_wrong_head(monkeypatch, tmp_path):
    module = _load_module()

    def fake_run(cmd, cwd, env, **_):
        (Path(cwd) / ".git").mkdir(exist_ok=True)
        return SimpleNamespace(stdout="f" * 40 if cmd[1] == "rev-parse" else "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="not the pinned"):
        module.git_bulk_fetch("cchew/lex-au", SHA, tmp_path / "corpus")
    assert not (tmp_path / "corpus" / ".git").exists()
