import json
import subprocess
import sys
from pathlib import Path


def test_regenerate_writes_sorted_names_from_index(tmp_path: Path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "index.json").write_text(json.dumps({
        "acts": {
            "privacy-act-1988": {"name": "Privacy Act 1988"},
            "gst-act-1999": {"name": "A New Tax System (Goods and Services Tax) Act 1999"},
        }
    }))
    output = tmp_path / "acts.txt"

    result = subprocess.run(
        [sys.executable, "scripts/regenerate_acts_txt.py",
         "--corpus-dir", str(corpus_dir), "--output", str(output)],
        capture_output=True, text=True,
    )

    assert result.returncode == 0
    lines = output.read_text().splitlines()
    assert lines == [
        "A New Tax System (Goods and Services Tax) Act 1999",
        "Privacy Act 1988",
    ]
    assert "Wrote 2 Act name(s)" in result.stdout


def test_regenerate_handles_empty_corpus(tmp_path: Path):
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "index.json").write_text(json.dumps({"acts": {}}))
    output = tmp_path / "acts.txt"

    result = subprocess.run(
        [sys.executable, "scripts/regenerate_acts_txt.py",
         "--corpus-dir", str(corpus_dir), "--output", str(output)],
        capture_output=True, text=True,
    )

    assert result.returncode == 0
    assert output.read_text() == ""
    assert "Wrote 0 Act name(s)" in result.stdout
