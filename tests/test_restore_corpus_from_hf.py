import importlib.util
from pathlib import Path


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "restore_corpus_from_hf",
        Path(__file__).parent.parent / "scripts" / "restore_corpus_from_hf.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _patch(module, monkeypatch, tmp_path, remote_files, download):
    monkeypatch.setattr(module, "snapshot_download", download)
    monkeypatch.setattr(module, "_write_sync_stamp", lambda repo, d: None)

    class FakeApi:
        def list_repo_files(self, **_):
            return remote_files

    monkeypatch.setattr(module, "HfApi", FakeApi)


def test_restore_calls_snapshot_download_with_expected_args(monkeypatch, tmp_path):
    module = _load_module()
    calls = {}
    local_dir = str(tmp_path / "corpus")

    def fake_snapshot_download(**kwargs):
        calls.update(kwargs)
        return kwargs["local_dir"]

    _patch(module, monkeypatch, tmp_path, [], fake_snapshot_download)
    result = module.restore("cchew/lex-au", local_dir, sleep=lambda _: None)

    assert calls == {
        "repo_id": "cchew/lex-au",
        "repo_type": "dataset",
        "local_dir": local_dir,
        "max_workers": module.MAX_WORKERS,
    }
    assert result == local_dir


def test_restore_retries_until_files_present(monkeypatch, tmp_path):
    module = _load_module()
    local_dir = tmp_path / "corpus"
    attempts = []

    def flaky(**kwargs):
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("429")
        local_dir.mkdir(exist_ok=True)
        (local_dir / "a.json").write_text("{}")
        return str(local_dir)

    _patch(module, monkeypatch, tmp_path, ["a.json"], flaky)
    module.restore("cchew/lex-au", str(local_dir), sleep=lambda _: None)
    assert len(attempts) == 3


def test_restore_fails_when_files_stay_missing(monkeypatch, tmp_path):
    import pytest

    module = _load_module()
    _patch(module, monkeypatch, tmp_path, ["gone.json"], lambda **k: k["local_dir"])
    with pytest.raises(RuntimeError, match="1 files missing"):
        module.restore("cchew/lex-au", str(tmp_path / "corpus"), sleep=lambda _: None)
