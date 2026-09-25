import subprocess
from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn
import os
from lexau.figures import materialise_figures, FigureResult

_FIX = Path(__file__).parent / "fixtures" / "figures"

_PNG_1x1 = bytes.fromhex(
  "89504e470d0a1a0a0000000d494844520000000100000001080600000"
  "01f15c4890000000a49444154789c6300010000050001"
  "0d0a2db40000000049454e44ae426082")

def _blobs(docx_path):
    doc = Document(docx_path); out = []
    for p in doc.paragraphs:
        blips = p._element.findall(f".//{qn('a:blip')}")
        if not blips: continue
        imgs = []
        for b in blips:
            rid = b.get(qn("r:embed"))
            part = p.part.related_parts[rid]
            imgs.append((Path(str(part.partname)).suffix.lower(), part.blob))
        out.append(imgs)
    return out

def test_raster_png_written_with_dims(tmp_path):
    res = materialise_figures("demo-act", "demo_act", _blobs(_FIX / "one_png.docx"), tmp_path)
    fr = res[0][0]
    assert fr.kind == "raster"
    assert fr.src == "corpus/images/demo_act-fig-1.png"  # flat
    assert (tmp_path / "demo_act-fig-1.png").exists()
    assert fr.width and fr.height

@pytest.mark.parametrize("fx", ["one_emf.docx", "one_wmf.docx"])
def test_vector_converted_when_soffice_present(tmp_path, fx):
    if not __import__("shutil").which("soffice"):
        pytest.skip("no soffice")
    res = materialise_figures("v-act", "v_act", _blobs(_FIX / fx), tmp_path)
    fr = res[0][0]
    assert fr.kind == "converted"
    assert (tmp_path / "v_act-fig-1.png").exists()

def test_vector_placeholder_without_soffice(tmp_path, monkeypatch):
    monkeypatch.setattr("lexau.figures.shutil.which", lambda _: None)
    res = materialise_figures("v-act", "v_act", _blobs(_FIX / "one_emf.docx"), tmp_path)
    fr = res[0][0]
    assert fr.kind == "placeholder"
    assert fr.src == "corpus/images/v_act-fig-1.png"  # flat
    assert not (tmp_path / "v_act-fig-1.png").exists()

def test_soffice_invoked_with_abs_path_and_full_env(tmp_path, monkeypatch):
    seen = {}
    def fake_run(cmd, *a, **k):
        seen["cmd"], seen["env"] = cmd, k.get("env", {})
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        for s in cmd[cmd.index("--outdir") + 2:]:
            (outdir / (Path(s).stem + ".png")).write_bytes(_PNG_1x1)
        class R: returncode = 0
        return R()
    monkeypatch.setattr("lexau.figures.shutil.which", lambda _: "/usr/local/bin/soffice")
    monkeypatch.setattr("lexau.figures.subprocess.run", fake_run)
    materialise_figures("v", "v", [[(".emf", b"x")]], tmp_path)
    assert os.path.isabs(seen["cmd"][0]) and seen["cmd"][0].endswith("soffice")
    assert "PATH" in seen["env"]

def test_chunked_partial_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("lexau.figures._SOFFICE_CHUNK", 2)
    calls = {"n": 0}
    def fake_run(cmd, *a, **k):
        calls["n"] += 1
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        rc = 0 if calls["n"] == 1 else 1
        if rc == 0:
            for s in cmd[cmd.index("--outdir") + 2:]:
                (outdir / (Path(s).stem + ".png")).write_bytes(_PNG_1x1)
        class R: pass
        R.returncode = rc
        return R()
    monkeypatch.setattr("lexau.figures.shutil.which", lambda _: "/usr/local/bin/soffice")
    monkeypatch.setattr("lexau.figures.subprocess.run", fake_run)
    res = materialise_figures("v", "v", [[(".emf", b"a")], [(".emf", b"b")], [(".emf", b"c")]], tmp_path)
    kinds = [r[0].kind for r in res]
    assert kinds == ["converted", "converted", "placeholder"]

def test_chunk_nonzero_exit_finalises_partial_success(tmp_path, monkeypatch):
    # Real-world shape (task-18B diagnosis): one bad/pathological blob in an
    # otherwise-good batched soffice invocation can make the WHOLE call exit
    # non-zero even though soffice already wrote PNGs for the other files in
    # the chunk before choking. Those already-written files must not be
    # thrown away just because the batch's overall exit code is non-zero.
    monkeypatch.setattr("lexau.figures._SOFFICE_CHUNK", 8)

    def fake_run(cmd, *a, **k):
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        inputs = cmd[cmd.index("--outdir") + 2:]
        # Every input except the last converts fine; the last one is the
        # pathological blob that sinks the batch's exit code.
        for s in inputs[:-1]:
            (outdir / (Path(s).stem + ".png")).write_bytes(_PNG_1x1)

        class R:
            pass

        R.returncode = 1
        return R()

    monkeypatch.setattr("lexau.figures.shutil.which", lambda _: "/usr/local/bin/soffice")
    monkeypatch.setattr("lexau.figures.subprocess.run", fake_run)
    figures = [[(".emf", b"a")], [(".emf", b"b")], [(".emf", b"c")]]
    res = materialise_figures("v", "v", figures, tmp_path)
    kinds = [r[0].kind for r in res]
    assert kinds == ["converted", "converted", "placeholder"]
    assert (tmp_path / "v-fig-1.png").exists()
    assert (tmp_path / "v-fig-2.png").exists()
    assert not (tmp_path / "v-fig-3.png").exists()


def test_chunk_timeout_finalises_partial_success(tmp_path, monkeypatch):
    # Same collateral-loss shape, but via the TimeoutExpired path rather than
    # a non-zero exit -- soffice can hang on one blob after already writing
    # PNGs for the earlier files in the same batched invocation.
    monkeypatch.setattr("lexau.figures._SOFFICE_CHUNK", 8)

    def fake_run(cmd, *a, **k):
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        inputs = cmd[cmd.index("--outdir") + 2:]
        for s in inputs[:-1]:
            (outdir / (Path(s).stem + ".png")).write_bytes(_PNG_1x1)
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=90)

    monkeypatch.setattr("lexau.figures.shutil.which", lambda _: "/usr/local/bin/soffice")
    monkeypatch.setattr("lexau.figures.subprocess.run", fake_run)
    figures = [[(".wmf", b"a")], [(".wmf", b"b")]]
    res = materialise_figures("t", "t", figures, tmp_path)
    kinds = [r[0].kind for r in res]
    assert kinds == ["converted", "placeholder"]
    assert (tmp_path / "t-fig-1.png").exists()
    assert not (tmp_path / "t-fig-2.png").exists()


def test_chunk_oserror_finalises_partial_success(tmp_path, monkeypatch):
    # Same shape again via OSError (e.g. soffice crashes/is killed partway
    # through a batch after writing some output).
    monkeypatch.setattr("lexau.figures._SOFFICE_CHUNK", 8)

    def fake_run(cmd, *a, **k):
        outdir = Path(cmd[cmd.index("--outdir") + 1])
        inputs = cmd[cmd.index("--outdir") + 2:]
        for s in inputs[:-1]:
            (outdir / (Path(s).stem + ".png")).write_bytes(_PNG_1x1)
        raise OSError("soffice crashed")

    monkeypatch.setattr("lexau.figures.shutil.which", lambda _: "/usr/local/bin/soffice")
    monkeypatch.setattr("lexau.figures.subprocess.run", fake_run)
    figures = [[(".emf", b"a")], [(".emf", b"b")]]
    res = materialise_figures("o", "o", figures, tmp_path)
    kinds = [r[0].kind for r in res]
    assert kinds == ["converted", "placeholder"]
    assert (tmp_path / "o-fig-1.png").exists()
    assert not (tmp_path / "o-fig-2.png").exists()


def test_two_images_one_paragraph(tmp_path):
    res = materialise_figures("y", "y", [[(".png", _PNG_1x1), (".png", _PNG_1x1)]], tmp_path)
    assert [r.src for r in res[0]] == ["corpus/images/y-fig-1.png", "corpus/images/y-fig-1b.png"]
