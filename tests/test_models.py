from lexau.models import ActMetadata
from datetime import date

def test_frbr_work_uri():
    meta = ActMetadata(
        name="Privacy Act 1988",
        title_id="C2004A03712",
        comp_id="C2024C00280",
        comp_num="52",
        year=1988,
        number=119,
        effective_date=date(2024, 1, 1),
    )
    assert meta.frbr_work_uri == "/akn/au/act/1988/119"

def test_frbr_expression_uri():
    meta = ActMetadata(
        name="Privacy Act 1988",
        title_id="C2004A03712",
        comp_id="C2024C00280",
        comp_num="52",
        year=1988,
        number=119,
        effective_date=date(2024, 1, 1),
    )
    assert meta.frbr_expression_uri == "/akn/au/act/1988/119/eng@2024-01-01"

def test_safe_name():
    meta = ActMetadata(
        name="Fair Work Act 2009",
        title_id="C2009A00028",
        comp_id="C2024C00100",
        comp_num="10",
        year=2009,
        number=28,
        effective_date=date(2024, 6, 1),
    )
    assert meta.safe_name == "fair-work-act-2009"
