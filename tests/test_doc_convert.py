import subprocess
from pathlib import Path

from lexau.doc_convert import convert_doc_to_docx


def test_returns_none_when_soffice_missing(tmp_path, monkeypatch):
    def fake_run(cmd, **kwargs):
        raise FileNotFoundError("soffice not found")
    monkeypatch.setattr(subprocess, "run", fake_run)

    doc_path = tmp_path / "test-act.doc"
    doc_path.write_bytes(b"\xd0\xcf\x11\xe0fake ole2 content")
    result = convert_doc_to_docx(doc_path, tmp_path / "out")

    assert result is None


def test_returns_converted_path_on_success(tmp_path, monkeypatch):
    out_dir = tmp_path / "out"

    def fake_run(cmd, **kwargs):
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "test-act.docx").write_bytes(b"PK\x03\x04fake docx")
        return subprocess.CompletedProcess(cmd, returncode=0)
    monkeypatch.setattr(subprocess, "run", fake_run)

    doc_path = tmp_path / "test-act.doc"
    doc_path.write_bytes(b"\xd0\xcf\x11\xe0fake ole2 content")
    result = convert_doc_to_docx(doc_path, out_dir)

    assert result == out_dir / "test-act.docx"
    assert result.read_bytes() == b"PK\x03\x04fake docx"


def test_returns_none_when_no_output_produced(tmp_path, monkeypatch):
    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode=0)  # no file written
    monkeypatch.setattr(subprocess, "run", fake_run)

    doc_path = tmp_path / "test-act.doc"
    doc_path.write_bytes(b"\xd0\xcf\x11\xe0")
    result = convert_doc_to_docx(doc_path, tmp_path / "out")

    assert result is None


def test_uses_unique_profile_per_call(tmp_path, monkeypatch):
    seen_profiles = []

    def fake_run(cmd, **kwargs):
        profile_arg = next(a for a in cmd if a.startswith("-env:UserInstallation="))
        seen_profiles.append(profile_arg)
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 1))
    monkeypatch.setattr(subprocess, "run", fake_run)

    doc_path = tmp_path / "test-act.doc"
    doc_path.write_bytes(b"\xd0\xcf\x11\xe0")
    convert_doc_to_docx(doc_path, tmp_path / "out1")
    convert_doc_to_docx(doc_path, tmp_path / "out2")

    assert len(seen_profiles) == 2
    assert seen_profiles[0] != seen_profiles[1]
