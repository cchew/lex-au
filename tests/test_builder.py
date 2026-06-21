import pytest
from lxml import etree
from datetime import date
from lexau.models import ActMetadata
from lexau.parser import ParsedParagraph, ElementType
from lexau.builder import AknBuilder

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"

@pytest.fixture
def meta(privacy_meta):
    return privacy_meta

def build_xml(meta, paragraphs):
    b = AknBuilder(meta)
    for p in paragraphs:
        b.add(p)
    xml, _validation = b.build()
    return xml

def test_root_element_is_akoma_ntoso(meta):
    xml = build_xml(meta, [])
    assert xml.tag == f"{{{AKN_NS}}}akomaNtoso"

def test_frbr_work_uri_in_meta(meta):
    xml = build_xml(meta, [])
    ns = {"akn": AKN_NS}
    this_elem = xml.find(".//akn:FRBRWork/akn:FRBRthis", ns)
    assert this_elem is not None
    assert "/akn/au/act/1988/119" in this_elem.get("value", "")

def test_single_section_produces_section_element(meta):
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        ParsedParagraph(ElementType.BODY, text="This Act is the Privacy Act 1988."),
    ]
    xml = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    section = xml.find(".//akn:section", ns)
    assert section is not None
    assert section.get("eId") == "sec-1"
    num = section.find("akn:num", ns)
    assert num is not None and num.text == "1"
    heading = section.find("akn:heading", ns)
    assert heading is not None and heading.text == "Short title"

def test_body_text_in_content_p(meta):
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        ParsedParagraph(ElementType.BODY, text="This Act is the Privacy Act 1988."),
    ]
    xml = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    p = xml.find(".//akn:section/akn:content/akn:p", ns)
    assert p is not None
    assert p.text == "This Act is the Privacy Act 1988."

def test_part_contains_sections(meta):
    paragraphs = [
        ParsedParagraph(ElementType.PART, number="I", heading="Preliminary"),
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        ParsedParagraph(ElementType.BODY, text="This Act is the Privacy Act 1988."),
        ParsedParagraph(ElementType.SECTION, number="2", heading="Commencement"),
    ]
    xml = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    part = xml.find(".//akn:part", ns)
    assert part is not None
    assert part.get("eId") == "part-I"
    sections = part.findall("akn:section", ns)
    assert len(sections) == 2
    assert sections[0].get("eId") == "part-I__sec-1"

def test_valid_xml_serialises(meta):
    paragraphs = [
        ParsedParagraph(ElementType.PART, number="I", heading="Preliminary"),
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        ParsedParagraph(ElementType.BODY, text="This Act is the Privacy Act 1988."),
    ]
    xml = build_xml(meta, paragraphs)
    raw = etree.tostring(xml, encoding="unicode", xml_declaration=False)
    assert "akomaNtoso" in raw
    assert 'eId="part-I"' in raw
    assert 'eId="part-I__sec-1"' in raw
