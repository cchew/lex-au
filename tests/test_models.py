from lexau.models import ActMetadata, ParseReport
from datetime import date
from cobalt import FrbrUri as CobaltFrbrUri
import json
import pytest
from pathlib import Path

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


def test_frbr_work_uri_cobalt_roundtrip(privacy_meta):
    parsed = CobaltFrbrUri.parse(privacy_meta.frbr_work_uri)
    assert parsed.country == "au"
    assert parsed.doctype == "act"
    assert parsed.date == str(privacy_meta.year)
    assert parsed.number == str(privacy_meta.number)


def test_frbr_expression_uri_cobalt_roundtrip(privacy_meta):
    parsed = CobaltFrbrUri.parse(privacy_meta.frbr_expression_uri)
    assert parsed.expression_uri() == privacy_meta.frbr_expression_uri
    assert parsed.language == "eng"
    assert parsed.expression_date == f"@{privacy_meta.effective_date.isoformat()}"


def _load_corpus_acts() -> list[ActMetadata]:
    index_path = Path(__file__).parent.parent / "corpus" / "index.json"
    if not index_path.exists():
        return []
    index = json.loads(index_path.read_text())
    return [
        ActMetadata(
            name=e["name"],
            title_id=e["title_id"],
            comp_id=e["comp_id"],
            comp_num=e["comp_num"],
            year=e["year"],
            number=e["number"],
            effective_date=date.fromisoformat(e["effective_date"]),
        )
        for e in index["acts"].values()
    ]


@pytest.fixture(params=_load_corpus_acts(), ids=lambda m: m.safe_name)
def corpus_act(request: pytest.FixtureRequest) -> ActMetadata:
    return request.param


def test_corpus_frbr_uris_parse_correctly(corpus_act: ActMetadata) -> None:
    work = CobaltFrbrUri.parse(corpus_act.frbr_work_uri)
    assert work.country == "au"
    assert work.doctype == "act"
    assert work.date == str(corpus_act.year)
    assert work.number == str(corpus_act.number)

    expr = CobaltFrbrUri.parse(corpus_act.frbr_expression_uri)
    assert expr.expression_uri() == corpus_act.frbr_expression_uri
    assert expr.language == "eng"
    assert expr.expression_date == f"@{corpus_act.effective_date.isoformat()}"


def test_parse_report_has_required_fields():
    r = ParseReport(
        act_name="Privacy Act 1988",
        volumes_fetched=1,
        preface_paras=5,
        schedules_found=1,
        schedule_names=["Schedule 1"],
        subsections_parsed=42,
        paragraphs_parsed=18,
        subparagraphs_parsed=6,
        style_fallbacks=2,
        refs_resolved=31,
        refs_unresolved=3,
    )
    assert r.act_name == "Privacy Act 1988"
    assert r.schedules_found == 1
    assert r.refs_unresolved == 3
