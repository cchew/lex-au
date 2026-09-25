"""Materialise DOCX figure image blobs into files under ``corpus/images/``.

One responsibility: turn the ``(ext, bytes)`` blobs pulled off FIGURE
paragraphs by :mod:`lexau.docx_reader` into real files on disk and report
what happened per image.

- Raster blobs (``.png``/``.jpg``/``.jpeg``/``.gif``/``.bmp``) are written
  verbatim (``.jpeg`` renamed to ``.jpg``); dimensions are read from the
  file header with stdlib byte parsing (no Pillow).
- Vector blobs (``.emf``/``.wmf``) are rasterised to PNG with LibreOffice
  ``soffice`` when it is on ``PATH``. Conversion is batched in chunks so one
  slow/hung file does not sink a figure-heavy Act. Without ``soffice`` (or on
  any conversion failure) the image becomes a ``placeholder``: the ``<img
  src>`` path is still reported, but no file is written.

Output is flat: ``out_dir/<safe_name>-fig-<n>.png`` (not ``<slug>/...``) so
the explorer's basename-keyed figure resolver can find it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

RASTER_EXTS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp"})
VECTOR_EXTS: frozenset[str] = frozenset({".emf", ".wmf"})

# Module-level so tests can monkeypatch them.
_SOFFICE_CHUNK = 8
_SOFFICE_TIMEOUT_S = 90


@dataclass
class FigureResult:
    src: str
    kind: Literal["raster", "converted", "placeholder"]
    width: int | None
    height: int | None


def _png_size(blob: bytes) -> tuple[int | None, int | None]:
    if len(blob) < 24 or blob[:8] != b"\x89PNG\r\n\x1a\n" or blob[12:16] != b"IHDR":
        return (None, None)
    w = int.from_bytes(blob[16:20], "big")
    h = int.from_bytes(blob[20:24], "big")
    return (w or None, h or None)


def _jpeg_size(blob: bytes) -> tuple[int | None, int | None]:
    if blob[:2] != b"\xff\xd8":
        return (None, None)
    i, n = 2, len(blob)
    while i + 9 < n:
        if blob[i] != 0xFF:
            i += 1
            continue
        marker = blob[i + 1]
        if marker == 0xD8 or marker == 0xD9 or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seg_len = int.from_bytes(blob[i + 2:i + 4], "big")
        if marker in (0xC0, 0xC1, 0xC2, 0xC3):
            h = int.from_bytes(blob[i + 5:i + 7], "big")
            w = int.from_bytes(blob[i + 7:i + 9], "big")
            return (w or None, h or None)
        if seg_len < 2:
            break
        i += 2 + seg_len
    return (None, None)


def _gif_size(blob: bytes) -> tuple[int | None, int | None]:
    if len(blob) < 10 or blob[:6] not in (b"GIF87a", b"GIF89a"):
        return (None, None)
    w = int.from_bytes(blob[6:8], "little")
    h = int.from_bytes(blob[8:10], "little")
    return (w or None, h or None)


def _dims(blob: bytes, ext: str) -> tuple[int | None, int | None]:
    if ext == ".png":
        return _png_size(blob)
    if ext in (".jpg", ".jpeg"):
        return _jpeg_size(blob)
    if ext == ".gif":
        return _gif_size(blob)
    return (None, None)


def _suffix(image_index: int) -> str:
    """0 -> '', 1 -> 'b', 2 -> 'c', ..."""
    return "" if image_index == 0 else chr(ord("a") + image_index)


@dataclass
class _Pending:
    result: FigureResult
    in_path: Path
    out_path: Path


def _convert_chunk(
    soffice_bin: str, tmp_dir: Path, chunk: list[_Pending], out_dir: Path
) -> None:
    """Run one batched soffice conversion. A batch's returncode/timeout
    status describes the WHOLE invocation, not each individual file -- one
    slow/pathological blob can make soffice exit non-zero, hang past
    ``_SOFFICE_TIMEOUT_S``, or (rarely) raise ``OSError`` even after several
    of the chunk's other files converted cleanly and are already sitting in
    ``tmp_dir``. So regardless of how the subprocess call ends (clean exit,
    non-zero exit, timeout, or OSError), finalise every ``tmp_dir/<stem>.png``
    that actually exists on disk; only files that never got produced are left
    as placeholders."""
    lo_profile = tmp_dir / "lo"
    cmd = [
        soffice_bin,
        "--headless",
        f"-env:UserInstallation=file://{lo_profile}",
        "--convert-to",
        "png",
        "--outdir",
        str(tmp_dir),
        *[str(p.in_path) for p in chunk],
    ]
    try:
        subprocess.run(
            cmd,
            capture_output=True,
            timeout=_SOFFICE_TIMEOUT_S,
            env={**os.environ, "SAL_USE_VCLPLUGIN": "svp"},
        )
    except (subprocess.TimeoutExpired, OSError):
        pass
    out_dir.mkdir(parents=True, exist_ok=True)
    for pending in chunk:
        produced = tmp_dir / (pending.in_path.stem + ".png")
        if not produced.exists():
            continue
        data = produced.read_bytes()
        w, h = _png_size(data)
        if w is None and h is None:
            # Malformed/truncated PNG -- most likely on the timeout/OSError
            # paths above, where soffice was killed/crashed mid-write and
            # left a partial file on disk. Do not ship it as "converted";
            # fall back to the placeholder default instead.
            continue
        pending.out_path.write_bytes(data)
        pending.result.kind = "converted"
        pending.result.width = w
        pending.result.height = h


def materialise_figures(
    slug: str,
    safe_name: str,
    figures: list[list[tuple[str, bytes]]],
    out_dir: Path,
) -> list[list[FigureResult]]:
    """Write figure blobs to ``out_dir`` and return results mirroring the input
    nesting (one inner list per FIGURE paragraph, one FigureResult per image).

    ``figures`` is the concatenated blob list for a whole Act in document
    order; paragraph position ``n`` (1-based) names the file
    ``<safe_name>-fig-<n>[<letter>].<ext>``.
    """
    out_dir = Path(out_dir)
    results: list[list[FigureResult]] = []
    pending: list[_Pending] = []

    soffice_bin = shutil.which("soffice")
    tmp_dir = Path(tempfile.mkdtemp(prefix="lexau-fig-"))
    uid = 0
    try:
        for n, para in enumerate(figures, start=1):
            row: list[FigureResult] = []
            for image_index, (ext, blob) in enumerate(para):
                ext = ext.lower()
                stem = f"{safe_name}-fig-{n}{_suffix(image_index)}"

                if ext in RASTER_EXTS:
                    disk_ext = ".jpg" if ext in (".jpg", ".jpeg") else ext
                    out_dir.mkdir(parents=True, exist_ok=True)
                    (out_dir / f"{stem}{disk_ext}").write_bytes(blob)
                    w, h = _dims(blob, ext)
                    row.append(
                        FigureResult(
                            f"corpus/images/{stem}{disk_ext}", "raster", w, h
                        )
                    )
                    continue

                # Vector or unknown: reported src is always .png; placeholder
                # until soffice proves otherwise.
                fr = FigureResult(f"corpus/images/{stem}.png", "placeholder", None, None)
                row.append(fr)
                if ext in VECTOR_EXTS and soffice_bin:
                    uid += 1
                    in_path = tmp_dir / f"{uid}{ext}"
                    in_path.write_bytes(blob)
                    pending.append(_Pending(fr, in_path, out_dir / f"{stem}.png"))
            results.append(row)

        if pending and soffice_bin:
            for start in range(0, len(pending), _SOFFICE_CHUNK):
                _convert_chunk(
                    soffice_bin, tmp_dir, pending[start:start + _SOFFICE_CHUNK], out_dir
                )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return results
