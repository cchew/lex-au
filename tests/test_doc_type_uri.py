from datetime import date

from lexau.models import ActMetadata, doc_type_for


def _meta(**kw) -> ActMetadata:
    base = dict(name="X", title_id="C1", comp_id="c", comp_num="1", year=1994, number=57,
                effective_date=date(2026, 1, 1))
    base.update(kw)
    return ActMetadata(**base)


def test_doc_type_for():
    assert doc_type_for("F1996B00580", "Superannuation Industry (Supervision) Regulations 1994") == "regulation"
    assert doc_type_for("F2015L00000", "Foreign Acquisitions and Takeovers Regulation 2015") == "regulation"
    assert doc_type_for("F2020L00001", "Aged Care Rules 2020") == "instrument"
    assert doc_type_for("C2004A03712", "Privacy Act 1988") == "act"
    assert doc_type_for("C2004A00001", "Something Regulations Act 2000") == "act"


def test_regulation_work_uri_uses_title_id():
    m = _meta(name="Superannuation Industry (Supervision) Regulations 1994",
              title_id="F1996B00580", doc_type="regulation")
    assert m.frbr_work_uri == "/akn/au/regulation/1994/F1996B00580"
    assert m.frbr_expression_uri.startswith("/akn/au/regulation/1994/F1996B00580/eng@")


def test_act_work_uri_unchanged():
    m = _meta(year=1988, number=119)
    assert m.frbr_work_uri == "/akn/au/act/1988/119"


def test_locality_instrument_uri_unchanged():
    m = _meta(doc_type="instrument", locality="vic", title_id="F2020L00001")
    assert m.frbr_work_uri.endswith("/1994/57")
