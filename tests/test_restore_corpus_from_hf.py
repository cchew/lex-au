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


def test_restore_calls_snapshot_download_with_expected_args(monkeypatch, tmp_path):
    module = _load_module()
    calls = {}

    def fake_snapshot_download(*, repo_id, repo_type, local_dir):
        calls["repo_id"] = repo_id
        calls["repo_type"] = repo_type
        calls["local_dir"] = local_dir
        return local_dir

    monkeypatch.setattr(module, "snapshot_download", fake_snapshot_download)

    local_dir = str(tmp_path / "corpus")
    result = module.restore("cchew/lex-au", local_dir)

    assert calls == {
        "repo_id": "cchew/lex-au",
        "repo_type": "dataset",
        "local_dir": local_dir,
    }
    assert result == local_dir
