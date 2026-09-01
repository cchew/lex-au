"""Tests for scripts/audit_conversion_fidelity.py helpers."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from docx import Document

_SPEC = importlib.util.spec_from_file_location(
    "audit_conversion_fidelity",
    Path(__file__).resolve().parents[1] / "scripts" / "audit_conversion_fidelity.py",
)
audit = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(audit)


def _volume(path: Path, body_line: str) -> None:
    """A minimal Federal Register style volume: Contents block, body, endnotes."""
    doc = Document()
    for line in [
        "Contents",
        "Chapter 1—Preliminary 5",  # TOC entry (trailing page number)
        "1 Short title 5",  # TOC entry
        "The Parliament enacts:",  # first real body paragraph
        body_line,
        "Endnotes",
        "Endnote 1—About the endnotes",
    ]:
        doc.add_paragraph(line)
    doc.save(str(path))


def test_docx_body_paras_keeps_body_from_every_volume(tmp_path):
    # Regression pin: each volume carries its own Contents block and its own
    # endnote apparatus. Slicing the concatenation once finds only volume 1's
    # "Endnotes" heading and discards every later volume. `_docx_body_paras`
    # must slice per volume so a multi-volume Act is compared in full.
    v1 = tmp_path / "act-2001-c1-vol1.docx"
    v2 = tmp_path / "act-2001-c1-vol2.docx"
    _volume(v1, "Body text unique to volume one.")
    _volume(v2, "Body text unique to volume two.")

    body = audit._docx_body_paras([v1, v2])

    assert "Body text unique to volume one." in body
    assert "Body text unique to volume two." in body
    # front/back matter is trimmed on both volumes
    assert not any("Endnote 1" in p for p in body)
    assert "Contents" not in body


def test_docx_paths_prefers_compilation_and_guards_prefix_collision(tmp_path):
    docx_dir = tmp_path / "docx"
    docx_dir.mkdir()
    for name in [
        "fair-work-act-2009-c73-vol1.docx",
        "fair-work-act-2009-c73-vol2.docx",
        "fair-work-act-2009-vol1.docx",  # stale legacy download
        "fair-work-(registered-organisations)-act-2009-vol0.docx",  # different Act
    ]:
        (docx_dir / name).write_bytes(b"")

    paths, mode = audit._docx_paths(tmp_path, "fair-work-act-2009", {"comp_num": "73"})

    assert mode == "comp-vol"
    assert [p.name for p in paths] == [
        "fair-work-act-2009-c73-vol1.docx",
        "fair-work-act-2009-c73-vol2.docx",
    ]


def test_docx_paths_orders_volumes_numerically(tmp_path):
    docx_dir = tmp_path / "docx"
    docx_dir.mkdir()
    for n in (1, 2, 10, 11):
        (docx_dir / f"x-act-1997-c266-vol{n}.docx").write_bytes(b"")

    paths, _ = audit._docx_paths(tmp_path, "x-act-1997", {"comp_num": "266"})

    assert [p.name for p in paths] == [
        "x-act-1997-c266-vol1.docx",
        "x-act-1997-c266-vol2.docx",
        "x-act-1997-c266-vol10.docx",
        "x-act-1997-c266-vol11.docx",
    ]
