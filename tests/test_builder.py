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
    return b.build()

def test_root_element_is_akoma_ntoso(meta):
    xml, _ = build_xml(meta, [])
    assert xml.tag == f"{{{AKN_NS}}}akomaNtoso"

def test_frbr_work_uri_in_meta(meta):
    xml, _ = build_xml(meta, [])
    ns = {"akn": AKN_NS}
    this_elem = xml.find(".//akn:FRBRWork/akn:FRBRthis", ns)
    assert this_elem is not None
    assert "/akn/au/act/1988/119" in this_elem.get("value", "")

def test_single_section_produces_section_element(meta):
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        ParsedParagraph(ElementType.BODY, text="This Act is the Privacy Act 1988."),
    ]
    xml, _ = build_xml(meta, paragraphs)
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
    xml, _ = build_xml(meta, paragraphs)
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
    xml, _ = build_xml(meta, paragraphs)
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
    xml, _ = build_xml(meta, paragraphs)
    raw = etree.tostring(xml, encoding="unicode", xml_declaration=False)
    assert "akomaNtoso" in raw
    assert 'eId="part-I"' in raw
    assert 'eId="part-I__sec-1"' in raw


def test_subsection_eid(meta):
    xml, _ = build_xml(meta, [
        ParsedParagraph(ElementType.SECTION, number="16", heading="Notification"),
        ParsedParagraph(ElementType.SUBSECTION, number="1", text="The entity must notify..."),
    ])
    ns = {"akn": AKN_NS}
    subsec = xml.find(".//akn:subsection", ns)
    assert subsec is not None
    assert subsec.get("eId") == "sec-16__subsec-1"


def test_full_hierarchy_eid(meta):
    xml, _ = build_xml(meta, [
        ParsedParagraph(ElementType.SECTION, number="6", heading="Definitions"),
        ParsedParagraph(ElementType.SUBSECTION, number="1", text=""),
        ParsedParagraph(ElementType.PARAGRAPH, number="a", text="means..."),
        ParsedParagraph(ElementType.SUBPARAGRAPH, number="i", text="first thing"),
    ])
    ns = {"akn": AKN_NS}
    subpara = xml.find(".//akn:subparagraph", ns)
    assert subpara is not None
    assert subpara.get("eId") == "sec-6__subsec-1__para-a__subpara-i"


def test_paragraph_l_as_subparagraph_inside_paragraph(meta):
    # (l) when the stack has an open PARAGRAPH -> reclassified to SUBPARAGRAPH
    xml, _ = build_xml(meta, [
        ParsedParagraph(ElementType.SECTION, number="5", heading="Obligations"),
        ParsedParagraph(ElementType.SUBSECTION, number="1", text=""),
        ParsedParagraph(ElementType.PARAGRAPH, number="a", text=""),
        ParsedParagraph(ElementType.PARAGRAPH, number="l", text="the ambiguous item"),
    ])
    ns = {"akn": AKN_NS}
    subpara = xml.find(".//akn:subparagraph", ns)
    assert subpara is not None
    assert subpara.get("eId") == "sec-5__subsec-1__para-a__subpara-l"


def test_paragraph_l_as_sibling_paragraph(meta):
    # (l) after (a) at the same depth: (a) is closed off stack before (l) arrives
    xml, _ = build_xml(meta, [
        ParsedParagraph(ElementType.SECTION, number="5", heading="Obligations"),
        ParsedParagraph(ElementType.SUBSECTION, number="1", text=""),
        ParsedParagraph(ElementType.PARAGRAPH, number="a", text="the first condition:"),
        ParsedParagraph(ElementType.PARAGRAPH, number="l", text="the roman-ambiguous item"),
    ])
    ns = {"akn": AKN_NS}
    paragraphs = xml.findall(".//akn:paragraph", ns)
    assert len(paragraphs) == 2
    assert paragraphs[1].get("eId") == "sec-5__subsec-1__para-l"


def test_frbr_work_date_is_iso(meta):
    xml, _ = build_xml(meta, [])
    ns = {"akn": AKN_NS}
    work_date = xml.find(".//akn:FRBRWork/akn:FRBRdate", ns)
    assert work_date is not None
    assert work_date.get("date") == "1988-01-01"


def test_frbr_expression_date_is_iso(meta):
    xml, _ = build_xml(meta, [])
    ns = {"akn": AKN_NS}
    expr_date = xml.find(".//akn:FRBRExpression/akn:FRBRdate", ns)
    assert expr_date is not None
    assert expr_date.get("date") == "2024-01-01"
