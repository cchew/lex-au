"""LibreOffice-headless .doc -> .docx conversion.

Wraps `soffice --headless --convert-to docx`, the only tool confirmed to
preserve paragraph-style and run-level (bold/italic) formatting into a real
OOXML document the existing parser pipeline can consume -- antiword/catdoc
were rejected because raw-text extraction discards exactly that signal. See
docs/superpowers/specs/2026-07-20-legacy-doc-format-parsing-design.md,
"Tooling choice".
"""
from __future__ import annotations

import subprocess
import tempfile
import uuid
from pathlib import Path


def convert_doc_to_docx(doc_path: Path, out_dir: Path, timeout: int = 120) -> Path | None:
    """Convert one .doc file to .docx via LibreOffice headless.

    Uses a fresh -env:UserInstallation profile directory per call so
    concurrent invocations never contend over a shared LibreOffice
    user-profile lock file (the spec's "known operational gotcha").

    Returns the converted .docx path, or None if soffice is missing, exits
    non-zero, times out, or produces no output file.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    profile_dir = Path(tempfile.gettempdir()) / f"lo_profile_{uuid.uuid4().hex}"
    cmd = [
        "soffice",
        "--headless",
        "--norestore",
        f"-env:UserInstallation=file://{profile_dir}",
        "--convert-to", "docx",
        "--outdir", str(out_dir),
        str(doc_path),
    ]
    try:
        subprocess.run(cmd, timeout=timeout, capture_output=True, check=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None

    converted = out_dir / f"{doc_path.stem}.docx"
    return converted if converted.exists() else None
