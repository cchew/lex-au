from pathlib import Path

import pytest
from docx import Document
from docx.oxml.ns import qn
import os
from lexau.figures import materialise_figures, FigureResult

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
    res = materialise_figures("demo-act", "demo_act", _blobs("tests/fixtures/figures/one_png.docx"), tmp_path)
    fr = res[0][0]
    assert fr.kind == "raster"
    assert fr.src == "corpus/images/demo_act-fig-1.png"  # flat
    assert (tmp_path / "demo_act-fig-1.png").exists()
    assert fr.width and fr.height

@pytest.mark.parametrize("fx", ["one_emf.docx", "one_wmf.docx"])
def test_vector_converted_when_soffice_present(tmp_path, fx):
    if not __import__("shutil").which("soffice"):
        pytest.skip("no soffice")
    res = materialise_figures("v-act", "v_act", _blobs(f"tests/fixtures/figures/{fx}"), tmp_path)
    fr = res[0][0]
    assert fr.kind == "converted"
    assert (tmp_path / "v_act-fig-1.png").exists()

def test_vector_placeholder_without_soffice(tmp_path, monkeypatch):
    monkeypatch.setattr("lexau.figures.shutil.which", lambda _: None)
    res = materialise_figures("v-act", "v_act", _blobs("tests/fixtures/figures/one_emf.docx"), tmp_path)
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

def test_two_images_one_paragraph(tmp_path):
    res = materialise_figures("y", "y", [[(".png", _PNG_1x1), (".png", _PNG_1x1)]], tmp_path)
    assert [r.src for r in res[0]] == ["corpus/images/y-fig-1.png", "corpus/images/y-fig-1b.png"]
