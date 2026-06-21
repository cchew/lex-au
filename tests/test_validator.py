import pytest
from datetime import date
from lxml import etree
from lexau.models import ActMetadata
from lexau.parser import ParsedParagraph, ElementType
from lexau.builder import AknBuilder
from lexau.validator import validate_akn, ValidationResult

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"


def _build(meta: ActMetadata, paragraphs: list[ParsedParagraph]) -> etree._Element:
    b = AknBuilder(meta)
    for p in paragraphs:
        b.add(p)
    xml = b.build()
    return xml


@pytest.fixture
def meta(privacy_meta: ActMetadata) -> ActMetadata:
    return privacy_meta


def test_validate_akn_passes_on_valid_output(meta: ActMetadata) -> None:
    xml = _build(meta, [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        ParsedParagraph(ElementType.BODY, text="This Act is the Privacy Act 1988."),
    ])
    result = validate_akn(xml, meta)
    assert result.passed
    assert result.errors == []


def test_validate_akn_fails_on_wrong_frbr_uri(meta: ActMetadata) -> None:
    xml = _build(meta, [])
    wrong_meta = ActMetadata(
        name="Wrong Act 2000",
        title_id="C2000A00001",
        comp_id="C2000C00001",
        comp_num="1",
        year=2000,
        number=1,
        effective_date=date(2000, 1, 1),
    )
    result = validate_akn(xml, wrong_meta)
    assert not result.passed
    assert any("FRBR URI mismatch" in e for e in result.errors)


def test_validate_akn_fails_on_unparseable_xml(meta: ActMetadata) -> None:
    broken = etree.fromstring(b"<notAkn/>")
    result = validate_akn(broken, meta)
    assert not result.passed
    assert result.errors


def test_validation_result_is_dataclass() -> None:
    r = ValidationResult(passed=True, errors=[])
    assert r.passed
    assert r.errors == []
