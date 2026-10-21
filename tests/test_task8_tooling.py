import json
import shutil
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import diff_corpora as dc  # noqa: E402
import rebuild_offline as ro  # noqa: E402
import review_local_terms as rl  # noqa: E402

NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
FIXTURES = Path(__file__).parent / "fixtures" / "docx"


def _entry(**kw):
    e = {"name": "Foo Act 2000", "title_id": "C1", "comp_id": "C2", "comp_num": "7",
         "year": 2000, "number": 5, "effective_date": "2026-01-02", "xml_path": "xml/foo-act-2000.xml",
         "aliases": ["Old Foo Act"]}
    e.update(kw)
    return e


def test_meta_from_entry() -> None:
    m = ro.meta_from_entry(_entry(comp_num=7))
    assert (m.safe_name, m.comp_num, m.year, m.number) == ("foo-act-2000", "7", 2000, 5)
    assert m.effective_date.isoformat() == "2026-01-02"
    assert m.aliases == ["Old Foo Act"] and m.doc_type == "act" and m.locality is None


def test_find_volumes_sorted_numerically_and_prefers_c_files(tmp_path: Path) -> None:
    for n in ("vol10", "vol2", "vol1"):
        (tmp_path / f"foo-act-2000-c7-{n}.docx").touch()
    (tmp_path / "foo-act-2000-vol0.docx").touch()
    (tmp_path / "foo-act-2000-c6-vol0.docx").touch()
    names = [p.name for p in ro.find_volumes(tmp_path, "foo-act-2000", "7")]
    assert names == ["foo-act-2000-c7-vol1.docx", "foo-act-2000-c7-vol2.docx", "foo-act-2000-c7-vol10.docx"]


def test_find_volumes_legacy_fallback_and_missing(tmp_path: Path) -> None:
    (tmp_path / "foo-act-2000-vol1.docx").touch()
    (tmp_path / "foo-act-2000-vol0.docx").touch()
    (tmp_path / "foo-act-2000-extra-vol0.docx").touch()
    assert [p.name for p in ro.find_volumes(tmp_path, "foo-act-2000", "7")] == [
        "foo-act-2000-vol0.docx", "foo-act-2000-vol1.docx"]
    assert ro.find_volumes(tmp_path, "bar", "1") == []


def test_select_keys_reproducible_and_filters(tmp_path: Path) -> None:
    acts = {f"a{i:02d}": _entry(name=f"A{i}") for i in range(30)}
    vols = {k: [Path("x")] * (2 if i % 3 == 0 else 1) for i, k in enumerate(sorted(acts))}
    s1 = ro.select_keys(acts, vols, False, 5, 42, None)
    assert s1 == ro.select_keys(acts, vols, False, 5, 42, None) and len(s1) == 5
    assert s1 != ro.select_keys(acts, vols, False, 5, 43, None)
    multi = ro.select_keys(acts, vols, True, None, 0, None)
    assert len(multi) == 10
    f = tmp_path / "keys.txt"
    f.write_text("a01\nA2\n")
    assert ro.select_keys(acts, vols, False, None, 0, f) == ["a01", "a02"]
    acts["reg"] = _entry(doc_type="regulation")
    assert "reg" not in ro.select_keys(acts, {**vols, "reg": []}, False, None, 0, None)


def test_flag_is_required(tmp_path: Path) -> None:
    r = CliRunner().invoke(ro.main, ["--baseline-corpus", str(tmp_path), "--out", str(tmp_path / "o")])
    assert r.exit_code != 0 and "local-definitions" in r.output


def test_smoke_offline_rebuild_from_cached_docx(tmp_path: Path) -> None:
    src = FIXTURES / "loan-act-(no.-2)-1976-vol0.docx"
    if not src.exists():
        pytest.skip("fixture docx absent")
    base = tmp_path / "base"
    (base / "docx").mkdir(parents=True)
    shutil.copy(src, base / "docx" / src.name)
    entry = _entry(name="Loan Act (No. 2) 1976", year=1976, number=2, comp_num="1",
                   xml_path="xml/loan-act-(no.-2)-1976.xml", aliases=[])
    (base / "index.json").write_text(json.dumps({"acts": {"loan-act-(no.-2)-1976": entry}}))
    before = sorted(p.name for p in base.rglob("*"))
    out = tmp_path / "out"
    r = CliRunner().invoke(ro.main, ["--baseline-corpus", str(base), "--out", str(out), "--local-definitions"])
    assert r.exit_code == 0, r.output
    assert "built=1 skipped-missing-docx=0 errors=0" in r.output
    assert (out / "xml" / "loan-act-(no.-2)-1976.xml").exists()
    assert sorted(p.name for p in base.rglob("*")) == before


def _xml(body: str) -> str:
    return f'<akomaNtoso xmlns="{NS}"><act><body>{body}</body></act></akomaNtoso>'


def _write(d: Path, stem: str, body: str) -> None:
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{stem}.xml").write_text(_xml(body))


SEC = '<section eId="sec_1"><num>1</num><heading>Meanings</heading><content><p>{}</p></content></section>'


def test_diff_counts_and_exit_codes(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    same = SEC.format("plain")
    _write(a, "same", same)
    _write(b, "same", same)
    _write(a, "chg", SEC.format("x"))
    _write(b, "chg", SEC.format(
        'In this section, <term refersTo="#term-y--sec_1">y</term> means <def>z</def> <ref refersTo="#term-y--sec_1"/>'))
    res = dc.diff_dirs(a, b)
    s = res["summary"]
    assert (s["identical"], s["differing"], s["total_new_terms"], s["total_new_local_refs"]) == (1, 1, 1, 2)
    assert s["section_count_mismatches"] == []
    rep = tmp_path / "r.json"
    assert dc.main([str(a), str(b), "--report", str(rep)]) == 0
    assert dc.main([str(a), str(b), "--report", str(rep), "--require-identical"]) == 1
    _write(b, "chg", SEC.format("x") + SEC.format("extra"))
    assert dc.main([str(a), str(b), "--report", str(rep)]) == 1
    assert json.loads(rep.read_text())["summary"]["section_count_mismatches"] == ["chg"]


def test_review_extraction_strata_and_reproducible_sample(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    _write(a, "act", SEC.format('<term refersTo="#term-old">old</term> means <def>x</def>'))
    body = SEC.format('<term refersTo="#term-old">old</term> means <def>x</def>')
    body += (
        '<section eId="sec_2"><num>2</num><heading>Local</heading><content>'
        '<p>In this section, <term refersTo="#term-a--sec_2">a</term> means <def>x</def></p>'
        '<p><term refersTo="#term-b--sec_2">b</term> means <def>y</def></p>'
        '<p>In this Act, <term refersTo="#term-c">c</term> means <def>z</def></p>'
        '</content></section>'
    )
    _write(b, "act", body)
    terms = rl.new_terms(a, b)
    assert sorted(t["term"] for t in terms) == ["a", "b", "c"]
    phrased, unphrased = rl.split_strata(terms)
    assert sorted(t["term"] for t in phrased) == ["a", "c"]
    assert [t["term"] for t in unphrased] == ["b"]
    assert unphrased[0]["heading"] == "2 Local" and unphrased[0]["scope"] == "local:sec_2"
    assert rl.sample(phrased, 1, 3) == rl.sample(phrased, 1, 3)
    out = tmp_path / "r.md"
    assert rl.main([str(a), str(b), "--n", "5", "--seed", "9", "--out", str(out)]) == 0
    md = out.read_text()
    assert "Seed: 9" in md and "(b1)" in md and "Stratum 2" in md


def _akn(gen: str, extra: str = "") -> bytes:
    return (
        f'<akomaNtoso xmlns="{NS}"><act><meta><identification><FRBRWork><FRBRdate date="2000-01-01" name="Generation"/></FRBRWork>'
        f'<FRBRManifestation><FRBRthis value="x"/><FRBRdate date="{gen}" name="Generation"/></FRBRManifestation>'
        f'</identification></meta><body>{extra}</body></act></akomaNtoso>'
    ).encode()


def _two_dirs(tmp_path: Path, base: bytes, new: bytes) -> tuple[Path, Path]:
    b, n = tmp_path / "b", tmp_path / "n"
    b.mkdir()
    n.mkdir()
    (b / "a.xml").write_bytes(base)
    (n / "a.xml").write_bytes(new)
    return b, n


def test_generation_date_only_difference_is_identical(tmp_path: Path) -> None:
    b, n = _two_dirs(tmp_path, _akn("2026-10-01"), _akn("2026-10-22"))
    s = dc.diff_dirs(b, n)["summary"]
    assert (s["identical"], s["differing"], s["date_only_differing"]) == (1, 0, 1)


def test_other_difference_still_differs(tmp_path: Path) -> None:
    b, n = _two_dirs(tmp_path, _akn("2026-10-01", "<p>a</p>"), _akn("2026-10-22", "<p>b</p>"))
    s = dc.diff_dirs(b, n)["summary"]
    assert (s["identical"], s["differing"], s["date_only_differing"]) == (0, 1, 0)


def test_work_generation_date_change_is_not_normalised(tmp_path: Path) -> None:
    b, n = _two_dirs(tmp_path, _akn("2026-10-01"), _akn("2026-10-01").replace(b'2000-01-01', b'2001-01-01'))
    assert dc.diff_dirs(b, n)["summary"]["differing"] == 1


def test_no_normalise_flag_differs_on_date(tmp_path: Path) -> None:
    b, n = _two_dirs(tmp_path, _akn("2026-10-01"), _akn("2026-10-22"))
    s = dc.diff_dirs(b, n, normalise_generation_date=False)["summary"]
    assert (s["identical"], s["differing"], s["date_only_differing"]) == (0, 1, 0)


def test_cli_flag_and_report_line(tmp_path: Path, capsys) -> None:
    b, n = _two_dirs(tmp_path, _akn("2026-10-01"), _akn("2026-10-22"))
    rep = tmp_path / "r.json"
    assert dc.main([str(b), str(n), "--report", str(rep), "--require-identical"]) == 0
    assert "date_only=1" in capsys.readouterr().out
    assert dc.main([str(b), str(n), "--report", str(rep), "--require-identical", "--no-normalise-generation-date"]) == 1
