import json
import subprocess
import sys
from pathlib import Path


def test_diff_finds_acts_missing_from_corpus(tmp_path: Path):
    live_acts = tmp_path / "live.txt"
    live_acts.write_text("Privacy Act 1988\nNew Act 2026\nGST Act 1999\n")

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "index.json").write_text(json.dumps({
        "acts": {
            "privacy-act-1988": {"name": "Privacy Act 1988"},
            "gst-act-1999": {"name": "GST Act 1999"},
        }
    }))

    output = tmp_path / "new-acts.txt"
    result = subprocess.run(
        [sys.executable, "scripts/diff_new_acts.py",
         "--live-acts", str(live_acts), "--corpus-dir", str(corpus_dir),
         "--output", str(output)],
        capture_output=True, text=True,
    )

    assert result.returncode == 0
    assert output.read_text().splitlines() == ["New Act 2026"]
    assert "Found 1 new Act(s)" in result.stdout


def test_diff_handles_missing_index_json(tmp_path: Path):
    live_acts = tmp_path / "live.txt"
    live_acts.write_text("Privacy Act 1988\n")
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    output = tmp_path / "new-acts.txt"

    result = subprocess.run(
        [sys.executable, "scripts/diff_new_acts.py",
         "--live-acts", str(live_acts), "--corpus-dir", str(corpus_dir),
         "--output", str(output)],
        capture_output=True, text=True,
    )

    assert result.returncode == 0
    assert output.read_text().splitlines() == ["Privacy Act 1988"]


def test_diff_writes_empty_file_when_nothing_new(tmp_path: Path):
    live_acts = tmp_path / "live.txt"
    live_acts.write_text("Privacy Act 1988\n")
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "index.json").write_text(json.dumps({
        "acts": {"privacy-act-1988": {"name": "Privacy Act 1988"}}
    }))
    output = tmp_path / "new-acts.txt"

    result = subprocess.run(
        [sys.executable, "scripts/diff_new_acts.py",
         "--live-acts", str(live_acts), "--corpus-dir", str(corpus_dir),
         "--output", str(output)],
        capture_output=True, text=True,
    )

    assert result.returncode == 0
    assert output.read_text() == ""
    assert "Found 0 new Act(s)" in result.stdout


def test_diff_respects_limit(tmp_path: Path):
    live_acts = tmp_path / "live.txt"
    live_acts.write_text("C Act 2026\nA Act 2026\nB Act 2026\n")
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    output = tmp_path / "new-acts.txt"

    result = subprocess.run(
        [sys.executable, "scripts/diff_new_acts.py",
         "--live-acts", str(live_acts), "--corpus-dir", str(corpus_dir),
         "--output", str(output), "--limit", "2"],
        capture_output=True, text=True,
    )

    assert result.returncode == 0
    assert output.read_text().splitlines() == ["A Act 2026", "B Act 2026"]
    assert "Found 2 new Act(s)" in result.stdout
