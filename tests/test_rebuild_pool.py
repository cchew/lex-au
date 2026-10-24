import json
import shutil
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import diff_corpora as dc  # noqa: E402
import rebuild_offline as ro  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "docx"
NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"

SAMPLE = {
    "a.c.t.-supreme-court-(transfer)-act-1992": ("A.C.T. Supreme Court (Transfer) Act 1992", 1992),
    "albury-wodonga-development-(financial-assistance)-amendment-act-1982": (
        "Albury-Wodonga Development (Financial Assistance) Amendment Act 1982", 1982),
    "loan-(war-service-land-settlement)-act-1970": ("Loan (War Service Land Settlement) Act 1970", 1970),
    "loan-act-(no.-2)-1976": ("Loan Act (No. 2) 1976", 1976),
    "northern-territory-(commonwealth-lands)-act-1980": ("Northern Territory (Commonwealth Lands) Act 1980", 1980),
}


def _baseline(tmp_path: Path) -> Path:
    base = tmp_path / "base"
    (base / "docx").mkdir(parents=True)
    acts = {}
    for i, (key, (name, year)) in enumerate(SAMPLE.items()):
        src = FIXTURES / f"{key}-vol0.docx"
        if not src.exists():
            pytest.skip("fixture docx absent")
        shutil.copy(src, base / "docx" / src.name)
        acts[key] = {"name": name, "title_id": f"C{i}", "comp_id": f"CC{i}", "comp_num": "1", "year": year,
                     "number": i + 1, "effective_date": "2026-01-02", "xml_path": f"xml/{key}.xml", "aliases": []}
    (base / "index.json").write_text(json.dumps({"acts": acts, "updated_at": "x"}))
    return base


def _task(key: str, out: Path) -> dict:
    return {"key": key, "entry": {}, "paths": [], "out_dir": str(out), "index_path": "", "local_definitions": True}


def test_order_largest_first() -> None:
    assert ro.order_largest_first(["b", "a", "c", "d"], {"a": 5, "b": 50, "c": 5, "d": 500}) == ["d", "b", "a", "c"]


def test_total_docx_size_sums_volumes(tmp_path: Path) -> None:
    (tmp_path / "x1").write_bytes(b"12345")
    (tmp_path / "x2").write_bytes(b"123")
    assert ro.total_docx_size([tmp_path / "x1", tmp_path / "x2"]) == 8


def test_is_well_formed(tmp_path: Path) -> None:
    (tmp_path / "ok.xml").write_text("<r/>")
    (tmp_path / "bad.xml").write_text("<r>trunc")
    assert ro.is_well_formed(tmp_path / "ok.xml")
    assert not ro.is_well_formed(tmp_path / "bad.xml")
    assert not ro.is_well_formed(tmp_path / "absent.xml")


def test_build_one_isolates_failure(tmp_path: Path) -> None:
    res = ro.build_one(_task("boom", tmp_path))
    assert res["status"] == "failed" and res["key"] == "boom" and "error" in res


def test_build_one_writes_atomically_and_leaves_no_tmp(tmp_path: Path, monkeypatch) -> None:
    from lxml import etree
    monkeypatch.setattr(ro, "_convert_act", lambda *a, **k: (etree.Element("r"), type("R", (), {"terms_found": 3})()))
    monkeypatch.setattr(ro, "asdict", lambda r: {"terms_found": 3})
    monkeypatch.setattr(ro, "_load_corpus_index", lambda p: {})
    (tmp_path / "xml").mkdir()
    (tmp_path / "reports").mkdir()
    entry = {"name": "Foo Act 2000", "title_id": "C1", "comp_id": "C2", "comp_num": "7", "year": 2000,
             "number": 5, "effective_date": "2026-01-02"}
    res = ro.build_one({"key": "foo-act-2000", "entry": entry, "paths": ["a.docx"], "out_dir": str(tmp_path),
                        "index_path": "i.json", "local_definitions": True})
    assert res["status"] == "built", res
    assert (tmp_path / "xml" / "foo-act-2000.xml").read_bytes().startswith(b"<?xml")
    assert not list(tmp_path.rglob("*.tmp"))


def test_resume_skips_wellformed_rebuilds_truncated_and_reports(tmp_path: Path, monkeypatch) -> None:
    base = _baseline(tmp_path)
    out = tmp_path / "out"
    keys = sorted(SAMPLE)
    (out / "xml").mkdir(parents=True)
    good, bad = keys[0], keys[1]
    (out / "xml" / f"{good}.xml").write_text("<sentinel/>")
    (out / "xml" / f"{bad}.xml").write_text("<r>trunc")
    r = CliRunner().invoke(ro.main, ["--baseline-corpus", str(base), "--out", str(out),
                                     "--local-definitions", "--resume", "--workers", "1"])
    assert r.exit_code == 0, r.output
    assert "built=4 skipped-resume=1" in r.output and "errors=0" in r.output
    assert (out / "xml" / f"{good}.xml").read_text() == "<sentinel/>"
    assert ro.is_well_formed(out / "xml" / f"{bad}.xml")
    assert not list(out.rglob("*.tmp"))
    progress = [json.loads(ln) for ln in (out / "rebuild-progress.jsonl").read_text().splitlines()]
    assert len(progress) == 4 and all(p["status"] == "built" and "worker" in p for p in progress)


def test_pool_survives_failure_and_exits_nonzero(tmp_path: Path, monkeypatch) -> None:
    base = _baseline(tmp_path)
    victim = "loan-act-(no.-2)-1976"
    # corrupt one DOCX so only that Act fails
    (base / "docx" / f"{victim}-vol0.docx").write_bytes(b"not a docx")
    out = tmp_path / "out"
    r = CliRunner().invoke(ro.main, ["--baseline-corpus", str(base), "--out", str(out),
                                     "--local-definitions", "--workers", "2"])
    assert r.exit_code == 1, r.output
    assert "built=4" in r.output and "errors=1" in r.output
    assert victim in r.output
    assert not (out / "xml" / f"{victim}.xml").exists()
    assert len(list((out / "xml").glob("*.xml"))) == 4


def test_workers_1_and_2_produce_identical_xml_and_index(tmp_path: Path) -> None:
    base = _baseline(tmp_path)
    outs = {}
    for n in (1, 2):
        out = tmp_path / f"out{n}"
        args = ["--baseline-corpus", str(base), "--out", str(out), "--local-definitions", "--workers", str(n)]
        r = CliRunner().invoke(ro.main, args)
        assert r.exit_code == 0, r.output
        outs[n] = out
    names = sorted(p.name for p in (outs[1] / "xml").glob("*.xml"))
    assert len(names) == 5 and names == sorted(p.name for p in (outs[2] / "xml").glob("*.xml"))
    for name in names:
        a, b = (outs[n] / "xml" / name for n in (1, 2))
        assert dc.normalise_generation_date_bytes(a.read_bytes()) == dc.normalise_generation_date_bytes(b.read_bytes())
    for name in sorted(p.name for p in (outs[1] / "reports").glob("*.json")):
        assert (outs[1] / "reports" / name).read_text() == (outs[2] / "reports" / name).read_text()
    idx = json.loads((outs[2] / "index.json").read_text())
    base_idx = json.loads((base / "index.json").read_text())
    assert idx["structure_version"] == 2 and idx["acts"] == base_idx["acts"]


def test_workers_1_path_unchanged_output(tmp_path: Path) -> None:
    base = _baseline(tmp_path)
    out = tmp_path / "out"
    r = CliRunner().invoke(ro.main, ["--baseline-corpus", str(base), "--out", str(out), "--local-definitions"])
    assert r.exit_code == 0 and "built=5 skipped-missing-docx=0 errors=0" in r.output
    assert not (out / "rebuild-progress.jsonl").exists()


def test_queue_is_submitted_largest_first(tmp_path: Path, monkeypatch) -> None:
    seen: list[str] = []

    class FakeEx:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def submit(self, fn, t):
            from concurrent.futures import Future
            seen.append(t["key"])
            f = Future()
            f.set_result({"key": t["key"], "pid": 1, "status": "built", "seconds": 0.1})
            return f

    monkeypatch.setattr(ro, "ProcessPoolExecutor", FakeEx)
    base = _baseline(tmp_path)
    out = tmp_path / "out"
    r = CliRunner().invoke(ro.main, ["--baseline-corpus", str(base), "--out", str(out),
                                     "--local-definitions", "--workers", "3"])
    assert r.exit_code == 0, r.output
    sizes = {k: (base / "docx" / f"{k}-vol0.docx").stat().st_size for k in SAMPLE}
    assert seen == sorted(SAMPLE, key=lambda k: (-sizes[k], k))


def _fig_xml(figs: int) -> bytes:
    body = "".join('<figure><img src="x.png" alt=""/></figure>' for _ in range(figs))
    return f'<akomaNtoso xmlns="{NS}"><act><body>{body}</body></act></akomaNtoso>'.encode()


def test_diff_flags_figure_count_drop(tmp_path: Path) -> None:
    b, n = tmp_path / "b", tmp_path / "n"
    for d, figs in ((b, 3), (n, 2)):
        d.mkdir()
        (d / "a.xml").write_bytes(_fig_xml(figs))
    for d in (b, n):
        (d / "same.xml").write_bytes(_fig_xml(1))
    res = dc.diff_dirs(b, n)
    assert res["summary"]["figure_count_drops"] == ["a"]
    assert res["acts"]["a"]["figures"] == [3, 2] and res["acts"]["a"]["images"] == [3, 2]
    assert not res["acts"]["same"]["figure_drop"]
    assert dc.main([str(b), str(n), "--report", str(tmp_path / "r.json")]) == 1
