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
    lfs_info = SimpleNamespace(sha256=hashlib.sha256(data).hexdigest()) if lfs else None
    return SimpleNamespace(path=path, size=len(data), blob_id=_blob_id(b"pointer" + data) if lfs else _blob_id(data), lfs=lfs_info)


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


def _faithful_download(remote=REMOTE, calls=None):
    def download(**kwargs):
        if calls is not None:
            calls.append(kwargs)
        root = Path(kwargs["local_dir"])
        for path, data in remote.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        return kwargs["local_dir"]

    return download


def test_restore_pins_revision_and_writes_stamp(monkeypatch, tmp_path):
    module = _load_module()
    api = FakeApi()
    calls = []
    monkeypatch.setattr(module, "snapshot_download", _faithful_download(calls=calls))
    local = tmp_path / "corpus"

    module.restore("cchew/lex-au", str(local), sleep=lambda _: None, api=api)

    assert calls == [{
        "repo_id": "cchew/lex-au",
        "repo_type": "dataset",
        "revision": SHA,
        "local_dir": str(local),
        "max_workers": module.MAX_WORKERS,
    }]
    assert api.tree_calls[0]["revision"] == SHA
    stamp = json.loads((local / ".hf-sync-stamp.json").read_text())
    assert stamp["repo"] == "cchew/lex-au"
    assert stamp["remote_sha"] == SHA
    assert stamp["file_count"] == len(REMOTE)


def test_restore_refuses_non_empty_target(monkeypatch, tmp_path):
    module = _load_module()
    local = tmp_path / "corpus"
    (local / "xml").mkdir(parents=True)
    (local / "xml" / "a.xml").write_text("stale")
    called = []
    monkeypatch.setattr(module, "snapshot_download", lambda **k: called.append(k))

    with pytest.raises(RuntimeError, match="not empty"):
        module.restore("cchew/lex-au", str(local), sleep=lambda _: None, api=FakeApi())
    assert called == []


def test_restore_allows_existing_empty_dir(monkeypatch, tmp_path):
    module = _load_module()
    local = tmp_path / "corpus"
    local.mkdir()
    monkeypatch.setattr(module, "snapshot_download", _faithful_download())
    module.restore("cchew/lex-au", str(local), sleep=lambda _: None, api=FakeApi())
    assert (local / "xml" / "a.xml").read_bytes() == REMOTE["xml/a.xml"]


def test_restore_fails_when_429_fallback_keeps_stale_files(monkeypatch, tmp_path):
    """The 2026-10-25 failure: stale files already in local_dir, the Hub is
    rate-limited, snapshot_download "defaults to existing file" and returns
    success. Content verification must catch it and fail, with no stamp."""
    module = _load_module()
    local = tmp_path / "corpus"

    def stale_fallback(**kwargs):
        root = Path(kwargs["local_dir"])
        for path, data in REMOTE.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            # Pretend these were pre-seeded and the 429 fallback kept them.
            target.write_bytes(b"STALE " + data if path.startswith("xml/") else data)
        return kwargs["local_dir"]

    monkeypatch.setattr(module, "snapshot_download", stale_fallback)

    with pytest.raises(RuntimeError, match="1 files missing or mismatched"):
        module.restore("cchew/lex-au", str(local), sleep=lambda _: None, api=FakeApi())
    assert not (local / ".hf-sync-stamp.json").exists()


def test_restore_refetches_mismatched_files_then_succeeds(monkeypatch, tmp_path):
    module = _load_module()
    local = tmp_path / "corpus"
    attempts = []

    def download(**kwargs):
        attempts.append(1)
        root = Path(kwargs["local_dir"])
        for path, data in REMOTE.items():
            target = root / path
            if target.exists():  # real snapshot_download keeps existing files
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            corrupt = len(attempts) == 1 and path == "images/a-fig-1.png"
            target.write_bytes(b"truncated" if corrupt else data)
        return kwargs["local_dir"]

    monkeypatch.setattr(module, "snapshot_download", download)
    sleeps = []
    module.restore("cchew/lex-au", str(local), sleep=sleeps.append, api=FakeApi())

    assert len(attempts) == 2
    assert sleeps == [module.BACKOFF_SECONDS]
    assert (local / "images/a-fig-1.png").read_bytes() == REMOTE["images/a-fig-1.png"]
    assert (local / ".hf-sync-stamp.json").exists()


def test_restore_retries_transport_errors(monkeypatch, tmp_path):
    module = _load_module()
    attempts = []
    good = _faithful_download()

    def flaky(**kwargs):
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("429")
        return good(**kwargs)

    monkeypatch.setattr(module, "snapshot_download", flaky)
    module.restore("cchew/lex-au", str(tmp_path / "corpus"), sleep=lambda _: None, api=FakeApi())
    assert len(attempts) == 3


def test_restore_fails_when_files_stay_missing(monkeypatch, tmp_path):
    module = _load_module()
    monkeypatch.setattr(module, "snapshot_download", lambda **k: k["local_dir"])
    with pytest.raises(RuntimeError, match="3 files missing or mismatched"):
        module.restore("cchew/lex-au", str(tmp_path / "corpus"), sleep=lambda _: None, api=FakeApi())


def test_restore_fails_without_remote_sha(monkeypatch, tmp_path):
    module = _load_module()
    monkeypatch.setattr(module, "snapshot_download", _faithful_download())
    with pytest.raises(RuntimeError, match="head sha"):
        module.restore("cchew/lex-au", str(tmp_path / "corpus"), sleep=lambda _: None, api=FakeApi(sha=None))


def test_restore_allow_patterns_limits_download_and_verification(monkeypatch, tmp_path):
    module = _load_module()
    calls = []
    subset = {"xml/a.xml": REMOTE["xml/a.xml"]}
    monkeypatch.setattr(module, "snapshot_download", _faithful_download(remote=subset, calls=calls))
    local = tmp_path / "corpus"
    module.restore(
        "cchew/lex-au", str(local), sleep=lambda _: None, api=FakeApi(), allow_patterns=["xml/*"]
    )
    assert calls[0]["allow_patterns"] == ["xml/*"]
    assert json.loads((local / ".hf-sync-stamp.json").read_text())["file_count"] == 1
