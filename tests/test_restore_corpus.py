import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

_MODULE_PATH = Path(__file__).parent.parent / "scripts" / "restore_corpus_from_hf.py"
_spec = importlib.util.spec_from_file_location("restore_corpus_from_hf", _MODULE_PATH)
rc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rc)


def test_restore_writes_fresh_sync_stamp(tmp_path):
    local = tmp_path / "corpus"

    def fake_snapshot(*, repo_id, repo_type, local_dir):
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        return str(local_dir)

    with patch.object(rc, "snapshot_download", side_effect=fake_snapshot) as snap, \
         patch.object(rc, "HfApi") as api_cls:
        api_cls.return_value.repo_info.return_value = MagicMock(sha="deadbeef" * 5)
        rc.restore("cchew/lex-au", str(local))

    snap.assert_called_once()
    stamp = json.loads((local / ".hf-sync-stamp.json").read_text())
    assert stamp["repo"] == "cchew/lex-au"
    assert stamp["repo_type"] == "dataset"
    assert stamp["remote_sha"] == "deadbeef" * 5
    restored_at = datetime.fromisoformat(stamp["restored_at"].replace("Z", "+00:00"))
    assert (datetime.now(timezone.utc) - restored_at).total_seconds() < 60


def test_restore_stamp_written_even_if_repo_info_fails(tmp_path):
    local = tmp_path / "corpus"

    def fake_snapshot(*, repo_id, repo_type, local_dir):
        Path(local_dir).mkdir(parents=True, exist_ok=True)
        return str(local_dir)

    with patch.object(rc, "snapshot_download", side_effect=fake_snapshot), \
         patch.object(rc, "HfApi") as api_cls:
        api_cls.return_value.repo_info.side_effect = RuntimeError("offline")
        rc.restore("cchew/lex-au", str(local))

    stamp = json.loads((local / ".hf-sync-stamp.json").read_text())
    assert stamp["repo"] == "cchew/lex-au"
    assert stamp["remote_sha"] is None
