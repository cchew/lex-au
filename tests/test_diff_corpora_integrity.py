import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import diff_corpora as dc  # noqa: E402

NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"


def _act(*sections: tuple[str, str, str]) -> bytes:
    """sections: (eId, heading, paragraph text)"""
    body = "".join(
        f'<section eId="{eid}"><num>1</num><heading>{h}</heading><content><p>{t}</p></content></section>'
        for eid, h, t in sections
    )
    return f'<akomaNtoso xmlns="{NS}"><act><body>{body}</body></act></akomaNtoso>'.encode()


def _write(d: Path, name: str, data: bytes) -> None:
    d.mkdir(exist_ok=True)
    (d / f"{name}.xml").write_bytes(data)


def test_lost_paragraph_text_is_flagged(tmp_path: Path) -> None:
    b, n = tmp_path / "b", tmp_path / "n"
    _write(b, "a", _act(("sec-1", "Short title", "This Act may be cited as the Example Act."),
                        ("sec-2", "Commencement", "This Act commences on Royal Assent, which is a long sentence.")))
    _write(n, "a", _act(("sec-1", "Short title", "This Act may be cited as the Example Act.")))
    res = dc.diff_dirs(b, n)
    assert res["summary"]["text_lost_acts"] == ["a"]
    assert "commences on Royal Assent" in res["acts"]["a"]["text_lost_examples"][0]
    assert dc.main([str(b), str(n), "--report", str(tmp_path / "r.json")]) == 1


def test_moved_text_and_dropped_number_labels_are_not_loss(tmp_path: Path) -> None:
    b, n = tmp_path / "b", tmp_path / "n"
    _write(b, "a", _act(("sec-1", "", "3. The object of section 5 is to ensure that the provision is valid."),
                        ("sec-2", "", "1.(1) This Act may be cited as the Example Act 1994.")))
    _write(n, "a", _act(("sec-3", "Object of section 5", "The object of section 5 is to ensure that the provision is valid."),
                        ("sec-1", "Short title", "This Act may be cited as the Example Act 1994.")))
    res = dc.diff_dirs(b, n)
    assert res["summary"]["text_lost_acts"] == []


def test_duplicate_and_empty_eids_in_the_new_corpus_are_flagged(tmp_path: Path) -> None:
    b, n = tmp_path / "b", tmp_path / "n"
    _write(b, "a", _act(("sec-1", "H", "Text one is here.")))
    _write(n, "a", _act(("sec-1", "H", "Text one is here."), ("sec-1", "H2", "Text two is here.")))
    _write(b, "e", _act(("sec-1", "H", "Text one is here.")))
    _write(n, "e", _act(("", "H", "Text one is here.")))
    s = dc.diff_dirs(b, n)["summary"]
    assert s["duplicate_eid_acts"] == ["a"]
    assert s["empty_eid_acts"] == ["e"]


def test_section_increase_passes_only_when_allowed(tmp_path: Path) -> None:
    b, n = tmp_path / "b", tmp_path / "n"
    _write(b, "a", _act(("sec-1", "H", "Text one is here.")))
    _write(n, "a", _act(("sec-1", "H", "Text one is here."), ("sec-2", "H2", "Text two is here.")))
    assert dc.main([str(b), str(n), "--report", str(tmp_path / "r.json")]) == 1
    assert dc.main([str(b), str(n), "--report", str(tmp_path / "r.json"), "--allow-section-increase"]) == 0


def test_section_drop_always_fails(tmp_path: Path) -> None:
    b, n = tmp_path / "b", tmp_path / "n"
    _write(b, "a", _act(("sec-1", "H", "Text one is here."), ("sec-2", "H2", "Text two is here.")))
    _write(n, "a", _act(("sec-1", "H", "Text one is here."), ("sec-2", "H2", "Text two is here.")).replace(b"sec-2", b"sub-2").replace(b"<section", b"<subsection").replace(b"</section", b"</subsection"))
    res = dc.diff_dirs(b, n)
    assert res["summary"]["section_drops"] == ["a"]
    assert dc.main([str(b), str(n), "--report", str(tmp_path / "r.json"), "--allow-section-increase"]) == 1
