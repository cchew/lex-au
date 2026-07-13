import pytest
from lxml import etree
from datetime import date
from datetime import date as _date
from pathlib import Path
from unittest.mock import patch, MagicMock
from lexau.models import ActMetadata
from lexau.parser import ParsedParagraph, ElementType
from lexau.builder import AknBuilder, inject_lifecycle
from lexau.endnote_parser import AmendmentEvent, EndnoteResult

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


def test_preface_toc_emitted(meta):
    paragraphs = [
        ParsedParagraph(ElementType.BODY, text="Privacy Act 1988", raw_style="TOC Heading"),
        ParsedParagraph(ElementType.BODY, text="Part I—Preliminary\t1", raw_style="TOC 1"),
        ParsedParagraph(ElementType.BODY, text="1  Short title\t1", raw_style="TOC 2"),
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        ParsedParagraph(ElementType.BODY, text="This Act is the Privacy Act 1988."),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    preface = xml.find(".//akn:preface", ns)
    assert preface is not None
    toc = preface.find("akn:toc", ns)
    assert toc is not None
    toc_items = toc.findall("akn:tocItem", ns)
    assert len(toc_items) == 2  # both TOC 1 and TOC 2 lines become tocItem elements


def test_preface_non_toc_para_emitted_as_p(meta):
    paragraphs = [
        ParsedParagraph(ElementType.BODY, text="About this compilation", raw_style="Normal"),
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    preface = xml.find(".//akn:preface", ns)
    assert preface is not None
    p = preface.find("akn:p", ns)
    assert p is not None and p.text == "About this compilation"


def test_schedule_emitted_as_attachment(meta):
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        ParsedParagraph(ElementType.BODY, text="This Act is the Privacy Act 1988."),
        ParsedParagraph(ElementType.BODY, text="Schedule\xa01—Australian Privacy Principles", raw_style="ActHead 1"),
        ParsedParagraph(ElementType.BODY, text="APP 1  Open and transparent management"),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    attachments = xml.find(".//akn:attachments", ns)
    assert attachments is not None
    hcontainer = attachments.find(".//akn:hcontainer", ns)
    assert hcontainer is not None
    assert hcontainer.get("name") == "schedule"
    assert hcontainer.get("eId") == "schedule-1"


def test_multiple_schedules(meta):
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        ParsedParagraph(ElementType.BODY, text="Schedule\xa01—First Schedule", raw_style="ActHead 1"),
        ParsedParagraph(ElementType.BODY, text="Content of first schedule."),
        ParsedParagraph(ElementType.BODY, text="Schedule\xa02—Second Schedule", raw_style="ActHead 1"),
        ParsedParagraph(ElementType.BODY, text="Content of second schedule."),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    hcontainers = xml.findall(".//akn:hcontainer[@name='schedule']", ns)
    assert len(hcontainers) == 2
    assert hcontainers[0].get("eId") == "schedule-1"
    assert hcontainers[1].get("eId") == "schedule-2"


def test_body_outside_schedule_not_in_attachments(meta):
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        ParsedParagraph(ElementType.BODY, text="Section body text."),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    assert xml.find(".//akn:attachments", ns) is None


def test_schedule_app_clause_hierarchy(meta):
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        ParsedParagraph(ElementType.BODY, text="This Act is the Privacy Act 1988."),
        ParsedParagraph(ElementType.BODY, text="Schedule\xa01—Australian Privacy Principles", raw_style="ActHead 1"),
        ParsedParagraph(ElementType.BODY, text="APP 1 — Open and transparent management"),
        ParsedParagraph(ElementType.BODY, text="1.1 The object of this APP is to ensure..."),
        ParsedParagraph(ElementType.PARAGRAPH, number="a", text="have an up-to-date APP privacy policy"),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    clause = xml.find(".//akn:hcontainer[@name='clause']", ns)
    assert clause is not None
    assert clause.get("eId") == "schedule-1__clause-1"
    num = clause.find("akn:num", ns)
    assert num is not None and num.text == "1"
    subclause = xml.find(".//akn:hcontainer[@name='subclause']", ns)
    assert subclause is not None
    assert "subclause" in subclause.get("eId", "")
    para = xml.find(".//akn:hcontainer[@name='subclause']//akn:paragraph", ns)
    assert para is not None
    assert "para-a" in para.get("eId", "")


def test_schedule_numeric_clause(meta):
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        ParsedParagraph(ElementType.BODY, text="Schedule\xa02—Definitions", raw_style="ActHead 1"),
        ParsedParagraph(ElementType.BODY, text="1  General definitions"),
        ParsedParagraph(ElementType.BODY, text="1.1 In this Schedule..."),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    clause = xml.find(".//akn:hcontainer[@name='clause']", ns)
    assert clause is not None
    assert clause.get("eId") == "schedule-1__clause-1"


def test_schedule_alphanumeric_clause(meta):
    # TG Regs use clause numbers like "1A", "2B" — _CLAUSE_RE must match \d+[A-Z]?
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        ParsedParagraph(ElementType.BODY, text="Schedule\xa01—Test", raw_style="ActHead 1"),
        ParsedParagraph(ElementType.BODY, text="1A  Alpha clause heading"),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    clause = xml.find(".//akn:hcontainer[@name='clause']", ns)
    assert clause is not None
    assert clause.get("eId") == "schedule-1__clause-1A"


def test_schedule_section_typed_clause(meta):
    # TG Regs: clause headings parsed as SECTION elements (not BODY text) with num+heading fields
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        ParsedParagraph(ElementType.BODY, text="Schedule\xa01—Essential principles", raw_style="ActHead 1"),
        ParsedParagraph(ElementType.SECTION, number="7", heading="Chemical properties"),
        ParsedParagraph(ElementType.BODY, text="A device must be designed to minimise risk."),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    clause = xml.find(".//akn:hcontainer[@name='clause']", ns)
    assert clause is not None
    assert clause.get("eId") == "schedule-1__clause-7"
    heading = clause.find("akn:heading", ns)
    assert heading is not None and heading.text == "Chemical properties"


def test_schedule_section_typed_dotted_subclause(meta):
    # TG Regs: dotted clause numbers (7.1) parsed as SECTION → subclause under current clause
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        ParsedParagraph(ElementType.BODY, text="Schedule\xa01—Essential principles", raw_style="ActHead 1"),
        ParsedParagraph(ElementType.SECTION, number="7", heading="Chemical properties"),
        ParsedParagraph(ElementType.SECTION, number="7.1", heading="Choice of materials"),
        ParsedParagraph(ElementType.BODY, text="Materials must be biocompatible."),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    subclause = xml.find(".//akn:hcontainer[@name='subclause']", ns)
    assert subclause is not None
    assert subclause.get("eId") == "schedule-1__clause-7__subclause-7-1"
    heading = subclause.find("akn:heading", ns)
    assert heading is not None and heading.text == "Choice of materials"


def test_schedule_subsection_typed_subclause(meta):
    # TG Regs: SUBSECTION paragraphs with num inside a schedule clause → numbered subclause
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        ParsedParagraph(ElementType.BODY, text="Schedule\xa01—Essential principles", raw_style="ActHead 1"),
        ParsedParagraph(ElementType.SECTION, number="2", heading="Design principles"),
        ParsedParagraph(ElementType.SUBSECTION, number="1", text="The manufacturer must adopt safe design solutions."),
        ParsedParagraph(ElementType.SUBSECTION, number="2", text="Without limiting subclause (1), solutions must..."),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    clause = xml.find(".//akn:hcontainer[@name='clause']", ns)
    assert clause is not None
    assert clause.get("eId") == "schedule-1__clause-2"
    subclauses = clause.findall("akn:hcontainer[@name='subclause']", ns)
    assert len(subclauses) == 2
    assert subclauses[0].get("eId") == "schedule-1__clause-2__subclause-1"
    assert subclauses[1].get("eId") == "schedule-1__clause-2__subclause-2"


def test_build_attachments_returns_tuple(meta):
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        ParsedParagraph(ElementType.BODY, text="Schedule\xa01—Test", raw_style="ActHead 1"),
        ParsedParagraph(ElementType.BODY, text="1  First Clause"),
        ParsedParagraph(ElementType.BODY, text="2  Second Clause"),
    ]
    # build() uses _build_attachments internally — just verify it works end-to-end
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    clauses = xml.findall(".//akn:hcontainer[@name='clause']", ns)
    assert len(clauses) == 2


def test_authorial_note_emitted(meta):
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="16", heading="Notification"),
        ParsedParagraph(ElementType.NOTE, text="Note: See also section 6."),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    note = xml.find(".//akn:authorialNote", ns)
    assert note is not None
    assert note.get("placement") == "end"
    assert note.get("marker") == "1"
    assert note.get("eId") == "note-1"
    p = note.find("akn:content/akn:p", ns)
    assert p is not None
    assert p.text == "Note: See also section 6."


def test_example_emitted(meta):
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="6", heading="Definitions"),
        ParsedParagraph(ElementType.EXAMPLE, text="Example: A person who transfers data..."),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    ex = xml.find(".//akn:hcontainer[@name='example']", ns)
    assert ex is not None
    p = ex.find("akn:content/akn:p", ns)
    assert p is not None
    assert p.text == "Example: A person who transfers data..."


def test_penalty_emitted(meta):
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="13G", heading="Offences"),
        ParsedParagraph(ElementType.PENALTY, text="Penalty: 60 penalty units."),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    pen = xml.find(".//akn:hcontainer[@name='penalty']", ns)
    assert pen is not None
    p = pen.find("akn:content/akn:p", ns)
    assert p is not None
    assert p.text == "Penalty: 60 penalty units."


def test_table_emitted_as_akn_table(meta):
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Fees"),
        ParsedParagraph(
            ElementType.TABLE,
            table_rows=[["Header 1", "Header 2"], ["Data 1", "Data 2"]],
        ),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    table = xml.find(".//akn:table", ns)
    assert table is not None
    rows = table.findall("akn:tr", ns)
    assert len(rows) == 2
    ths = rows[0].findall("akn:th", ns)
    assert len(ths) == 2
    assert ths[0].text == "Header 1"
    tds = rows[1].findall("akn:td", ns)
    assert len(tds) == 2
    assert tds[0].text == "Data 1"


def test_empty_table_rows_skipped(meta):
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Fees"),
        ParsedParagraph(ElementType.TABLE, table_rows=[]),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    table = xml.find(".//akn:table", ns)
    assert table is not None
    rows = table.findall("akn:tr", ns)
    assert len(rows) == 0


def test_level4_emitted_with_lowercase_eid(meta):
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="45", heading="Tests"),
        ParsedParagraph(ElementType.SUBSECTION, number="1", text=""),
        ParsedParagraph(ElementType.PARAGRAPH, number="a", text=""),
        ParsedParagraph(ElementType.SUBPARAGRAPH, number="i", text=""),
        ParsedParagraph(ElementType.LEVEL4, number="A", text="the entity must comply"),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    level4 = xml.find(".//akn:hcontainer[@name='level4']", ns)
    assert level4 is not None
    assert level4.get("eId") == "sec-45__subsec-1__para-a__subpara-i__level4-a"
    num = level4.find("akn:num", ns)
    assert num is not None and num.text == "A"
    p = level4.find("akn:content/akn:p", ns)
    assert p is not None and "comply" in p.text


def test_frbr_work_has_country(meta):
    xml, _ = build_xml(meta, [])
    ns = {"akn": AKN_NS}
    el = xml.find(".//akn:FRBRWork/akn:FRBRcountry", ns)
    assert el is not None
    assert el.get("value") == "au"


def test_frbr_work_has_subtype(meta):
    xml, _ = build_xml(meta, [])
    ns = {"akn": AKN_NS}
    el = xml.find(".//akn:FRBRWork/akn:FRBRsubtype", ns)
    assert el is not None
    assert el.get("value") == "act"


def test_frbr_work_has_number(meta):
    xml, _ = build_xml(meta, [])
    ns = {"akn": AKN_NS}
    el = xml.find(".//akn:FRBRWork/akn:FRBRnumber", ns)
    assert el is not None
    assert el.get("value") == "119"  # privacy_meta.number


def test_frbr_work_has_name(meta):
    xml, _ = build_xml(meta, [])
    ns = {"akn": AKN_NS}
    el = xml.find(".//akn:FRBRWork/akn:FRBRname", ns)
    assert el is not None
    assert el.get("value") == "privacy-act-1988"


def test_frbr_work_is_prescriptive(meta):
    xml, _ = build_xml(meta, [])
    ns = {"akn": AKN_NS}
    el = xml.find(".//akn:FRBRWork/akn:FRBRprescriptive", ns)
    assert el is not None
    assert el.get("value") == "true"


def test_frbr_work_is_authoritative(meta):
    xml, _ = build_xml(meta, [])
    ns = {"akn": AKN_NS}
    el = xml.find(".//akn:FRBRWork/akn:FRBRauthoritative", ns)
    assert el is not None
    assert el.get("value") == "true"


def _meta_with_keywords():
    return ActMetadata(
        name="Privacy Act 1988",
        title_id="C2004A03712",
        comp_id="C2024C00280",
        comp_num="52",
        year=1988,
        number=119,
        effective_date=_date(2024, 1, 1),
        subject_keywords=["Privacy", "Data Protection"],
    )


def test_classification_keywords_in_meta(meta):
    m = _meta_with_keywords()
    b = AknBuilder(m)
    xml, _ = b.build()
    ns = {"akn": AKN_NS}
    classification = xml.find(".//akn:meta/akn:classification", ns)
    assert classification is not None
    assert classification.get("source") == "#legislation-gov-au"
    keywords = classification.findall("akn:keyword", ns)
    assert len(keywords) == 2
    show_as_values = {kw.get("showAs") for kw in keywords}
    assert "Privacy" in show_as_values
    assert "Data Protection" in show_as_values
    value_attrs = {kw.get("value") for kw in keywords}
    assert "privacy" in value_attrs
    assert "data-protection" in value_attrs


def test_no_keywords_no_classification(meta):
    # meta fixture has subject_keywords=[] (default)
    xml, _ = build_xml(meta, [])
    ns = {"akn": AKN_NS}
    classification = xml.find(".//akn:meta/akn:classification", ns)
    assert classification is None


def test_classification_before_references(meta):
    m = _meta_with_keywords()
    b = AknBuilder(m)
    xml, _ = b.build()
    ns = {"akn": AKN_NS}
    meta_el = xml.find(".//akn:meta", ns)
    tags = [c.tag.split("}")[1] for c in meta_el]
    assert tags.index("classification") < tags.index("references"), (
        f"<classification> must precede <references> in <meta>; got order: {tags}"
    )


def _meta_with_long_title():
    m = ActMetadata(
        name="Privacy Act 1988",
        title_id="C2004A03712",
        comp_id="C2024C00280",
        comp_num="52",
        year=1988,
        number=119,
        effective_date=_date(2024, 1, 1),
        long_title="An Act to make provision to protect the privacy of individuals",
    )
    return m


def test_long_title_in_preface(meta):
    m = _meta_with_long_title()
    b = AknBuilder(m)
    xml, _ = b.build()
    ns = {"akn": AKN_NS}
    lt = xml.find(".//akn:preface/akn:longTitle/akn:p", ns)
    assert lt is not None
    assert "privacy of individuals" in lt.text


def test_no_long_title_no_long_title_element(meta):
    # meta fixture has long_title="" (default)
    xml, _ = build_xml(meta, [])
    ns = {"akn": AKN_NS}
    lt = xml.find(".//akn:longTitle", ns)
    assert lt is None


def test_enacting_formula_detected(meta):
    b = AknBuilder(meta)
    b.add(ParsedParagraph(ElementType.BODY, text="The Parliament of Australia enacts:"))
    b.add(ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"))
    xml, _ = b.build()
    ns = {"akn": AKN_NS}
    formula = xml.find(".//akn:preface/akn:formula", ns)
    assert formula is not None
    assert formula.get("name") == "enacting"
    assert "enacts" in "".join(formula.itertext())


def test_whereas_recital_detected(meta):
    b = AknBuilder(meta)
    b.add(ParsedParagraph(ElementType.BODY, text="WHEREAS the Parliament intends to protect privacy:"))
    b.add(ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"))
    xml, _ = b.build()
    ns = {"akn": AKN_NS}
    # <preamble> must be a sibling of <preface> under <act>, NOT inside <preface>
    assert xml.find(".//akn:preface/akn:preamble", ns) is None, "<preamble> must NOT be inside <preface>"
    recital = xml.find(".//akn:act/akn:preamble/akn:recitals/akn:recital", ns)
    assert recital is not None


def test_ordinary_preface_para_unaffected(meta):
    b = AknBuilder(meta)
    b.add(ParsedParagraph(ElementType.BODY, text="This is a normal preface paragraph."))
    b.add(ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"))
    xml, _ = b.build()
    ns = {"akn": AKN_NS}
    # Should be a bare <p> not a <formula> or <recital>
    formula = xml.find(".//akn:preface/akn:formula", ns)
    assert formula is None
    p = xml.find(".//akn:preface/akn:p", ns)
    assert p is not None
    assert p.text == "This is a normal preface paragraph."


def test_tlcterm_in_references_after_build_with_report(meta):
    b = AknBuilder(meta)
    # Simulate a Definitions section
    b.add(ParsedParagraph(ElementType.SECTION, number="6", heading="Definitions"))
    b.add(ParsedParagraph(ElementType.BODY, text='"personal information" means information about an individual.'))
    b.add(ParsedParagraph(ElementType.SECTION, number="7", heading="Objects"))
    corpus_index = {}
    xml, report = b.build_with_report(corpus_index)
    assert report.terms_found == 1
    ns = {"akn": AKN_NS}
    tlc = xml.find('.//akn:references/akn:TLCTerm[@eId="term-personal-information"]', ns)
    assert tlc is not None
    assert tlc.get("showAs") == "personal information"


def test_refs_injected_inside_def_element(meta):
    b = AknBuilder(meta)
    b.add(ParsedParagraph(ElementType.SECTION, number="6", heading="Definitions"))
    b.add(ParsedParagraph(ElementType.BODY,
        text='"notifiable data breach" means a data breach as described in section 26.'))
    corpus_index = {}
    xml, _ = b.build_with_report(corpus_index)
    ns = {"akn": AKN_NS}
    def_el = xml.find(f".//{{{AKN_NS}}}def")
    assert def_el is not None
    # inject_refs should process text within <def> — check for a <ref> inside it
    ref_in_def = def_el.find(f"{{{AKN_NS}}}ref")
    assert ref_in_def is not None
    assert "sec-26" in ref_in_def.get("href", "")


def test_authorial_notes_get_eids(meta):
    b = AknBuilder(meta)
    b.add(ParsedParagraph(ElementType.SECTION, number="1", heading="Objects"))
    b.add(ParsedParagraph(ElementType.NOTE, text="Note: See also section 6."))
    b.add(ParsedParagraph(ElementType.NOTE, text="Note: See also section 7."))
    xml, _ = b.build()
    ns = {"akn": AKN_NS}
    notes = xml.findall(".//akn:authorialNote", ns)
    assert len(notes) == 2
    eids = [n.get("eId") for n in notes]
    assert "note-1" in eids
    assert "note-2" in eids


def test_note_ref_injected_for_bracket_marker(meta):
    b = AknBuilder(meta)
    b.add(ParsedParagraph(ElementType.SECTION, number="1", heading="Objects"))
    b.add(ParsedParagraph(ElementType.BODY, text="This provision applies [note 1]."))
    b.add(ParsedParagraph(ElementType.NOTE, text="Note 1: See section 6."))
    corpus_index = {}
    xml, report = b.build_with_report(corpus_index)
    assert report.note_refs_injected == 1
    ns = {"akn": AKN_NS}
    note_ref = xml.find(".//akn:noteRef[@href='#note-1']", ns)
    assert note_ref is not None
    assert note_ref.get("marker") == "1"


# --- blockList tests ---

def test_blocklist_basic(meta):
    """Two consecutive LIST_ITEM paragraphs at level 0 produce one <blockList> with two <item> children."""
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="4", heading="Obligations"),
        ParsedParagraph(ElementType.LIST_ITEM, number="0", text="First item"),
        ParsedParagraph(ElementType.LIST_ITEM, number="0", text="Second item"),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    blocklists = xml.findall(".//akn:blockList", ns)
    assert len(blocklists) == 1
    items = blocklists[0].findall("akn:item", ns)
    assert len(items) == 2
    assert items[0].get("eId") == "sec-4__list-1__item-1"
    assert items[1].get("eId") == "sec-4__list-1__item-2"


def test_blocklist_level_change(meta):
    """Level 0 item followed by level 1 item produces two separate <blockList> elements."""
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="5", heading="Requirements"),
        ParsedParagraph(ElementType.LIST_ITEM, number="0", text="Top level item"),
        ParsedParagraph(ElementType.LIST_ITEM, number="1", text="Nested item"),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    blocklists = xml.findall(".//akn:blockList", ns)
    assert len(blocklists) == 2
    assert blocklists[0].get("eId") == "sec-5__list-1"
    assert blocklists[1].get("eId") == "sec-5__list-2"


def test_blocklist_flush_on_subsection(meta):
    """LIST_ITEM followed by SUBSECTION: <blockList> is closed, <subsection> is a sibling."""
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="6", heading="Powers"),
        ParsedParagraph(ElementType.LIST_ITEM, number="0", text="An item in the list"),
        ParsedParagraph(ElementType.SUBSECTION, number="1", text="A subsection follows"),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    section = xml.find(".//akn:section", ns)
    assert section is not None
    # blockList and subsection should both be direct children of the section
    blocklist = section.find("akn:blockList", ns)
    subsection = section.find("akn:subsection", ns)
    assert blocklist is not None
    assert subsection is not None


def test_blocklist_num_extraction(meta):
    """Text '(a) the person is a resident' produces <num>(a)</num><p>the person is a resident</p>."""
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="7", heading="Conditions"),
        ParsedParagraph(ElementType.LIST_ITEM, number="0", text="(a) the person is a resident"),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    item = xml.find(".//akn:blockList/akn:item", ns)
    assert item is not None
    num = item.find("akn:num", ns)
    assert num is not None and num.text == "(a)"
    p = item.find("akn:p", ns)
    assert p is not None and p.text == "the person is a resident"


# --- lifecycle / eventRef tests (Task 5) ---

def _make_events(*args) -> list[AmendmentEvent]:
    """Helper: build AmendmentEvent list from (provision, effect, act_number, act_year) tuples."""
    return [
        AmendmentEvent(provision=prov, effect=eff, act_number=num, act_year=yr)
        for prov, eff, num, yr in args
    ]


def test_lifecycle_emitted(meta):
    """build_with_report with mocked endnote events emits <lifecycle> inside <meta>."""
    events = _make_events(("s 6", "am", 99, 2010))
    fake_result = EndnoteResult(amendment_events=events)

    b = AknBuilder(meta)
    with patch("lexau.builder.parse_endnotes", return_value=fake_result), \
         patch("lexau.builder.DocxDocument", MagicMock()):
        xml, report = b.build_with_report({}, last_volume_path=Path("fake.docx"))

    ns = {"akn": AKN_NS}
    lifecycle = xml.find(".//akn:meta/akn:lifecycle", ns)
    assert lifecycle is not None
    assert report.amendment_events_parsed == 1


def test_lifecycle_creation_event(meta):
    """<eventRef type='generation' eId='evt-creation'> is always present when lifecycle is emitted."""
    events = _make_events(("s 6", "am", 42, 2005))
    fake_result = EndnoteResult(amendment_events=events)

    b = AknBuilder(meta)
    with patch("lexau.builder.parse_endnotes", return_value=fake_result), \
         patch("lexau.builder.DocxDocument", MagicMock()):
        xml, _ = b.build_with_report({}, last_volume_path=Path("fake.docx"))

    ns = {"akn": AKN_NS}
    creation = xml.find(
        ".//akn:lifecycle/akn:eventRef[@eId='evt-creation'][@type='generation']", ns
    )
    assert creation is not None
    assert creation.get("date") == "1988-01-01"  # meta.year = 1988


def test_lifecycle_amendment_events(meta):
    """Two unique amending Acts produce two <eventRef type='amendment'>."""
    events = _make_events(
        ("s 6", "am", 70, 2009),
        ("s 7", "am", 109, 2004),
    )
    fake_result = EndnoteResult(amendment_events=events)

    b = AknBuilder(meta)
    with patch("lexau.builder.parse_endnotes", return_value=fake_result), \
         patch("lexau.builder.DocxDocument", MagicMock()):
        xml, _ = b.build_with_report({}, last_volume_path=Path("fake.docx"))

    ns = {"akn": AKN_NS}
    amd_events = xml.findall(
        ".//akn:lifecycle/akn:eventRef[@type='amendment']", ns
    )
    assert len(amd_events) == 2
    sources = {e.get("source") for e in amd_events}
    assert "/akn/au/act/2009/70" in sources
    assert "/akn/au/act/2004/109" in sources


def test_lifecycle_dedup(meta):
    """Same act_number/act_year in multiple rows produces only one <eventRef type='amendment'>."""
    events = _make_events(
        ("s 6", "am", 70, 2009),
        ("s 8", "rep", 70, 2009),  # same Act — should be deduped
        ("s 9", "ad", 70, 2009),   # same Act again
    )
    fake_result = EndnoteResult(amendment_events=events)

    b = AknBuilder(meta)
    with patch("lexau.builder.parse_endnotes", return_value=fake_result), \
         patch("lexau.builder.DocxDocument", MagicMock()):
        xml, _ = b.build_with_report({}, last_volume_path=Path("fake.docx"))

    ns = {"akn": AKN_NS}
    amd_events = xml.findall(
        ".//akn:lifecycle/akn:eventRef[@type='amendment']", ns
    )
    assert len(amd_events) == 1
    assert amd_events[0].get("source") == "/akn/au/act/2009/70"


def test_lifecycle_skipped_no_path(meta):
    """last_volume_path=None → no <lifecycle> emitted."""
    b = AknBuilder(meta)
    xml, report = b.build_with_report({}, last_volume_path=None)

    ns = {"akn": AKN_NS}
    lifecycle = xml.find(".//akn:lifecycle", ns)
    assert lifecycle is None
    assert report.amendment_events_parsed == 0


# --- temporalData tests (Task 6) ---

def test_temporal_data_emitted(meta):
    """<temporalData> is present inside <meta> when lifecycle is present."""
    events = _make_events(("s 6", "am", 99, 2010))
    fake_result = EndnoteResult(amendment_events=events)

    b = AknBuilder(meta)
    with patch("lexau.builder.parse_endnotes", return_value=fake_result), \
         patch("lexau.builder.DocxDocument", MagicMock()):
        xml, _ = b.build_with_report({}, last_volume_path=Path("fake.docx"))

    ns = {"akn": AKN_NS}
    td = xml.find(".//akn:meta/akn:temporalData", ns)
    assert td is not None


def test_temporal_group_exists(meta):
    """<temporalGroup eId='tg-1'> is a child of <temporalData>."""
    events = _make_events(("s 6", "am", 99, 2010))
    fake_result = EndnoteResult(amendment_events=events)

    b = AknBuilder(meta)
    with patch("lexau.builder.parse_endnotes", return_value=fake_result), \
         patch("lexau.builder.DocxDocument", MagicMock()):
        xml, _ = b.build_with_report({}, last_volume_path=Path("fake.docx"))

    ns = {"akn": AKN_NS}
    tg = xml.find(".//akn:temporalData/akn:temporalGroup[@eId='tg-1']", ns)
    assert tg is not None


def test_time_interval_open(meta):
    """<timeInterval start='#evt-creation'> has no end attribute (open-ended)."""
    events = _make_events(("s 6", "am", 99, 2010))
    fake_result = EndnoteResult(amendment_events=events)

    b = AknBuilder(meta)
    with patch("lexau.builder.parse_endnotes", return_value=fake_result), \
         patch("lexau.builder.DocxDocument", MagicMock()):
        xml, _ = b.build_with_report({}, last_volume_path=Path("fake.docx"))

    ns = {"akn": AKN_NS}
    ti = xml.find(".//akn:temporalGroup/akn:timeInterval[@start='#evt-creation']", ns)
    assert ti is not None
    assert ti.get("end") is None


# --- passiveModifications tests (Task 7) ---

def _build_tree_with_section(meta, section_num: str = "6"):
    """Build a minimal AKN tree containing a section with eId sec-{section_num}."""
    b = AknBuilder(meta)
    b.add(ParsedParagraph(ElementType.SECTION, number=section_num, heading="Definitions"))
    xml, _ = b.build()
    return xml


def test_passive_mod_emitted(meta):
    """A resolved provision + known lifecycle evt → <textualMod> inside <passiveModifications>."""
    from lexau.builder import inject_passive_mods, inject_lifecycle, inject_temporal_data

    events = [AmendmentEvent(provision="s 6", effect="am", act_number=99, act_year=2010)]
    xml = _build_tree_with_section(meta, "6")

    # Inject lifecycle so evt_map can resolve the event
    inject_lifecycle(xml, meta, events)
    inject_temporal_data(xml, events)
    inject_passive_mods(xml, events)

    ns = {"akn": AKN_NS}
    pm = xml.find(".//akn:meta/akn:analysis/akn:passiveModifications", ns)
    assert pm is not None, "<passiveModifications> not found"
    mods = pm.findall("akn:textualMod", ns)
    assert len(mods) == 1
    mod = mods[0]
    assert mod.get("eId") == "mod-1"
    src = mod.find("akn:source", ns)
    assert src is not None and src.get("href") == "#evt-amd-1"
    dest = mod.find("akn:destination", ns)
    assert dest is not None and dest.get("href") == "#sec-6"


def test_passive_mod_type_mapping(meta):
    """effect='am' → type='substitution', 'ad' → 'insertion', 'rep' → 'repeal'."""
    from lexau.builder import inject_passive_mods, inject_lifecycle, inject_temporal_data

    events = [
        AmendmentEvent(provision="s 6", effect="am", act_number=10, act_year=2010),
        AmendmentEvent(provision="s 6", effect="ad", act_number=20, act_year=2011),
        AmendmentEvent(provision="s 6", effect="rep", act_number=30, act_year=2012),
    ]
    xml = _build_tree_with_section(meta, "6")
    inject_lifecycle(xml, meta, events)
    inject_temporal_data(xml, events)
    inject_passive_mods(xml, events)

    ns = {"akn": AKN_NS}
    mods = xml.findall(".//akn:passiveModifications/akn:textualMod", ns)
    assert len(mods) == 3
    types = [m.get("type") for m in mods]
    assert "substitution" in types
    assert "insertion" in types
    assert "repeal" in types


def test_passive_mod_unresolved_skip(meta):
    """Unknown provision (no matching eId) → no <textualMod>, mods_unresolved incremented."""
    from lexau.builder import inject_passive_mods, inject_lifecycle, inject_temporal_data
    from lexau.models import ParseReport

    # Only sec-6 exists in the tree; provision "s 99" won't resolve
    events = [AmendmentEvent(provision="s 99", effect="am", act_number=99, act_year=2010)]
    xml = _build_tree_with_section(meta, "6")
    inject_lifecycle(xml, meta, events)
    inject_temporal_data(xml, events)

    report = ParseReport(act_name="Test")
    inject_passive_mods(xml, events, report=report)

    ns = {"akn": AKN_NS}
    # <analysis> must not be emitted (zero resolved)
    analysis = xml.find(".//akn:meta/akn:analysis", ns)
    assert analysis is None
    assert report.mods_unresolved == 1
    assert report.mods_resolved == 0


def test_passive_mod_not_applied(meta):
    """applied=False → event is skipped, no <textualMod> emitted."""
    from lexau.builder import inject_passive_mods, inject_lifecycle, inject_temporal_data
    from lexau.models import ParseReport

    events = [AmendmentEvent(provision="s 6", effect="am", act_number=99, act_year=2010, applied=False)]
    xml = _build_tree_with_section(meta, "6")
    inject_lifecycle(xml, meta, events)
    inject_temporal_data(xml, events)

    report = ParseReport(act_name="Test")
    inject_passive_mods(xml, events, report=report)

    ns = {"akn": AKN_NS}
    analysis = xml.find(".//akn:meta/akn:analysis", ns)
    assert analysis is None
    assert report.mods_resolved == 0


def test_passive_mod_empty_omitted(meta):
    """Zero resolved events → <analysis> element is NOT inserted into <meta>."""
    from lexau.builder import inject_passive_mods, inject_lifecycle, inject_temporal_data

    # No events at all
    xml = _build_tree_with_section(meta, "6")
    inject_passive_mods(xml, [])

    ns = {"akn": AKN_NS}
    analysis = xml.find(".//akn:meta/akn:analysis", ns)
    assert analysis is None


# ---------------------------------------------------------------------------
# Task 8: <quotedStructure> detection
# ---------------------------------------------------------------------------

def test_quoted_structure_detected(meta):
    """BODY('"') SECTION BODY('"') → <quotedStructure> wrapping <section>."""
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="5", heading="Amendments"),
        ParsedParagraph(ElementType.BODY, text='"'),
        ParsedParagraph(ElementType.SECTION, number="3A", heading="New provision"),
        ParsedParagraph(ElementType.BODY, text='"'),
    ]
    b = AknBuilder(meta)
    for p in paragraphs:
        b.add(p)
    xml, _ = b.build()
    ns = {"akn": AKN_NS}
    qs = xml.find(".//akn:quotedStructure", ns)
    assert qs is not None, "<quotedStructure> not found"
    inner_section = qs.find("akn:section", ns)
    assert inner_section is not None, "<section> not found inside <quotedStructure>"


def test_quoted_structure_content(meta):
    """Inner content of <quotedStructure> is valid AKN — has correct attributes."""
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="10", heading="Modification"),
        ParsedParagraph(ElementType.BODY, text="'"),
        ParsedParagraph(ElementType.SECTION, number="10A", heading="Inserted section"),
        ParsedParagraph(ElementType.SUBSECTION, number="1", text="Content here."),
        ParsedParagraph(ElementType.BODY, text="'"),
    ]
    b = AknBuilder(meta)
    for p in paragraphs:
        b.add(p)
    xml, _ = b.build()
    ns = {"akn": AKN_NS}
    qs = xml.find(".//akn:quotedStructure", ns)
    assert qs is not None, "<quotedStructure> not found"
    assert qs.get("startQuote") == "“"
    assert qs.get("endQuote") == "”"
    inner_sec = qs.find("akn:section", ns)
    assert inner_sec is not None
    subsec = inner_sec.find("akn:subsection", ns)
    assert subsec is not None
    p_el = subsec.find(".//akn:p", ns)
    assert p_el is not None and p_el.text == "Content here."


def test_quoted_structure_skipped(meta):
    """Multi-provision quote (SECTION SECTION between markers) → quoted_structures_unhandled incremented."""
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="5", heading="Amendments"),
        ParsedParagraph(ElementType.BODY, text='"'),
        ParsedParagraph(ElementType.SECTION, number="3A", heading="First inserted"),
        ParsedParagraph(ElementType.SECTION, number="3B", heading="Second inserted"),
        ParsedParagraph(ElementType.BODY, text='"'),
    ]
    b = AknBuilder(meta)
    for p in paragraphs:
        b.add(p)
    xml, report = b.build_with_report({})
    assert report.quoted_structures_unhandled >= 1


def test_figure_emitted(meta):
    """A FIGURE paragraph produces <figure><img> in the AKN output."""
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Diagrams"),
        ParsedParagraph(ElementType.FIGURE, text=""),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    fig = xml.find(".//akn:figure", ns)
    assert fig is not None
    img = fig.find("akn:img", ns)
    assert img is not None
    src = img.get("src", "")
    assert src.startswith("corpus/images/privacy-act-1988-fig-")
    assert src.endswith(".png")
    assert img.get("alt") == ""


def test_figure_src_increments(meta):
    """Multiple FIGURE paragraphs produce sequentially numbered img src attributes."""
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Diagrams"),
        ParsedParagraph(ElementType.FIGURE, text=""),
        ParsedParagraph(ElementType.FIGURE, text=""),
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    imgs = xml.findall(".//akn:figure/akn:img", ns)
    assert len(imgs) == 2
    assert imgs[0].get("src") == "corpus/images/privacy-act-1988-fig-1.png"
    assert imgs[1].get("src") == "corpus/images/privacy-act-1988-fig-2.png"


def test_figures_found_in_report(meta):
    """figures_found in ParseReport counts FIGURE paragraphs."""
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Diagrams"),
        ParsedParagraph(ElementType.FIGURE, text=""),
        ParsedParagraph(ElementType.FIGURE, text=""),
    ]
    b = AknBuilder(meta)
    for p in paragraphs:
        b.add(p)
    _, report = b.build_with_report({})
    assert report.figures_found == 2


def test_italic_span_emits_i_element(meta):
    """A ParsedParagraph with an italic span produces <p><i>...</i>...</p>."""
    from lexau.parser import InlineSpan
    p = ParsedParagraph(
        ElementType.BODY,
        text="personal information means something",
        spans=[
            InlineSpan(text="personal information", italic=True),
            InlineSpan(text=" means something"),
        ],
    )
    paragraphs = [
        ParsedParagraph(ElementType.SECTION, number="6", heading="Definitions"),
        p,
    ]
    xml, _ = build_xml(meta, paragraphs)
    ns = {"akn": AKN_NS}
    p_el = xml.find(".//akn:section/akn:content/akn:p", ns)
    assert p_el is not None
    i_el = p_el.find(f"{{{AKN_NS}}}i")
    assert i_el is not None
    assert i_el.text == "personal information"
    assert i_el.tail == " means something"


def test_bold_span_emits_b_element(meta):
    from lexau.parser import InlineSpan
    p = ParsedParagraph(
        ElementType.BODY,
        text="Important note",
        spans=[InlineSpan(text="Important note", bold=True)],
    )
    xml, _ = build_xml(meta, [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        p,
    ])
    ns = {"akn": AKN_NS}
    p_el = xml.find(".//akn:section/akn:content/akn:p", ns)
    assert p_el.find(f"{{{AKN_NS}}}b") is not None
    assert p_el.find(f"{{{AKN_NS}}}b").text == "Important note"


def test_plain_spans_no_children(meta):
    """Unformatted spans produce plain p.text, no children."""
    from lexau.parser import InlineSpan
    p = ParsedParagraph(
        ElementType.BODY,
        text="This Act is the Privacy Act 1988.",
        spans=[InlineSpan(text="This Act is the Privacy Act 1988.")],
    )
    xml, _ = build_xml(meta, [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        p,
    ])
    ns = {"akn": AKN_NS}
    p_el = xml.find(".//akn:section/akn:content/akn:p", ns)
    assert len(list(p_el)) == 0
    assert p_el.text == "This Act is the Privacy Act 1988."


def test_no_spans_falls_back_to_plain_text(meta):
    """ParsedParagraph with empty spans list behaves exactly as before."""
    p = ParsedParagraph(
        ElementType.BODY,
        text="This Act is the Privacy Act 1988.",
    )
    xml, _ = build_xml(meta, [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"),
        p,
    ])
    ns = {"akn": AKN_NS}
    p_el = xml.find(".//akn:section/akn:content/akn:p", ns)
    assert len(list(p_el)) == 0
    assert p_el.text == "This Act is the Privacy Act 1988."


def test_superscript_span_emits_sup_element(meta):
    from lexau.parser import InlineSpan
    p = ParsedParagraph(
        ElementType.BODY,
        text="CO2",
        spans=[InlineSpan(text="CO"), InlineSpan(text="2", superscript=True)],
    )
    xml, _ = build_xml(meta, [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Formula"),
        p,
    ])
    ns = {"akn": AKN_NS}
    p_el = xml.find(".//akn:section/akn:content/akn:p", ns)
    sup_el = p_el.find(f"{{{AKN_NS}}}sup")
    assert sup_el is not None
    assert sup_el.text == "2"


def test_bold_italic_span_emits_nested_b_i(meta):
    from lexau.parser import InlineSpan
    p = ParsedParagraph(
        ElementType.BODY,
        text="critical term",
        spans=[InlineSpan(text="critical term", bold=True, italic=True)],
    )
    xml, _ = build_xml(meta, [
        ParsedParagraph(ElementType.SECTION, number="1", heading="Definitions"),
        p,
    ])
    ns = {"akn": AKN_NS}
    p_el = xml.find(".//akn:section/akn:content/akn:p", ns)
    b_el = p_el.find(f"{{{AKN_NS}}}b")
    assert b_el is not None
    i_el = b_el.find(f"{{{AKN_NS}}}i")
    assert i_el is not None
    assert i_el.text == "critical term"


def test_build_with_report_list_defs_found(meta):
    """build_with_report counts list-form definitions in list_defs_found."""
    from unittest.mock import patch, MagicMock
    from lexau.endnote_parser import EndnoteResult
    from lexau.parser import InlineSpan

    b = AknBuilder(meta)
    b.add(ParsedParagraph(ElementType.SECTION, number="6", heading="Definitions"))
    b.add(ParsedParagraph(ElementType.SUBSECTION, number="1", text=""))
    # List-form definition paragraph
    b.add(ParsedParagraph(ElementType.BODY, text="agency means:"))
    # Followed by paragraph items
    b.add(ParsedParagraph(ElementType.PARAGRAPH, number="a", text="a body corporate; or"))
    b.add(ParsedParagraph(ElementType.PARAGRAPH, number="b", text="a natural person."))

    corpus_index: dict = {}
    with patch("lexau.builder.parse_endnotes", return_value=EndnoteResult([], [])):
        _, report = b.build_with_report(corpus_index, last_volume_path=None)

    assert report.list_defs_found >= 1


def test_asterisk_ref_injected_end_to_end(meta):
    """build_with_report resolves *term usages against the term registry into <ref> links."""
    b = AknBuilder(meta)
    b.add(ParsedParagraph(ElementType.SECTION, number="1", heading="Dictionary"))
    b.add(ParsedParagraph(ElementType.BODY, text='"entity" means a person or organisation.'))
    b.add(ParsedParagraph(ElementType.SECTION, number="2", heading="Obligations"))
    b.add(ParsedParagraph(ElementType.BODY, text="The *entity must comply with this Act."))
    corpus_index: dict = {}
    xml, report = b.build_with_report(corpus_index)

    assert report.asterisk_resolved == 1
    assert report.asterisk_unresolved == 0
    refs = xml.findall(f".//{{{AKN_NS}}}ref")
    assert any(r.get("href") == "#term-entity" for r in refs)


def test_asterisk_ref_and_narrative_guard_combined_end_to_end(meta):
    """Both features exercised in one builder run within one definitions section:
    a genuine quoted definition resolves an *entity usage into a <ref>, while a
    narrative-prose candidate in the same section (an embedded relative clause,
    "(who may include ...)") is correctly rejected by the narrative guard and
    injects no spurious <term>."""
    b = AknBuilder(meta)
    b.add(ParsedParagraph(ElementType.SECTION, number="1", heading="Dictionary"))
    b.add(ParsedParagraph(ElementType.BODY, text='"entity" means a person or organisation.'))
    b.add(ParsedParagraph(
        ElementType.BODY,
        text="a person (who may include the trustee) is empowered to exercise any power of appointment.",
    ))
    b.add(ParsedParagraph(ElementType.SECTION, number="2", heading="Obligations"))
    b.add(ParsedParagraph(ElementType.BODY, text="The *entity must comply with this Act."))
    corpus_index: dict = {}
    xml, report = b.build_with_report(corpus_index)

    # Genuine usage: asterisk-ref resolved against the registry.
    assert report.asterisk_resolved == 1
    assert report.asterisk_unresolved == 0
    refs = xml.findall(f".//{{{AKN_NS}}}ref")
    assert any(r.get("href") == "#term-entity" for r in refs)

    # Rejected narrative candidate: no spurious second <term> injected.
    assert report.terms_found == 1
    term_els = xml.findall(f".//{{{AKN_NS}}}term")
    assert len(term_els) == 1
    assert term_els[0].get("refersTo") == "#term-entity"
    assert not any("who may" in (t.text or "") for t in term_els)


def test_build_with_report_inline_formatted_count(meta):
    """build_with_report counts <p> elements with inline markup in inline_formatted."""
    from lexau.parser import InlineSpan

    b = AknBuilder(meta)
    b.add(ParsedParagraph(ElementType.SECTION, number="6", heading="Definitions"))
    b.add(ParsedParagraph(
        ElementType.BODY,
        text="personal information means something",
        spans=[
            InlineSpan(text="personal information", italic=True),
            InlineSpan(text=" means something"),
        ],
    ))
    corpus_index: dict = {}
    with patch("lexau.builder.parse_endnotes", return_value=EndnoteResult([], [])):
        _, report = b.build_with_report(corpus_index, last_volume_path=None)

    assert report.inline_formatted >= 1


def test_list_item_inline_formatting_not_emitted_known_limitation(meta):
    """v0.6.0: LIST_ITEM <p> body is plain text even when spans carry formatting.
    _emit_p_inline is not called in the LIST_ITEM branch of build() — known limitation."""
    from lexau.parser import InlineSpan
    from lexau.builder import _emit_p_inline
    # _emit_p_inline itself works fine for any paragraph type
    p_with_bold = ParsedParagraph(
        ElementType.LIST_ITEM,
        number="1",
        text="bold text",
        spans=[InlineSpan(text="bold text", bold=True)],
    )
    p_el = etree.Element(f"{{{AKN_NS}}}p")
    _emit_p_inline(p_el, p_with_bold)
    # _emit_p_inline correctly emits <b> — but the LIST_ITEM branch in build() never calls this
    assert p_el.find(f"{{{AKN_NS}}}b") is not None
    # The actual limitation: build() assigns p_el.text directly for LIST_ITEM
    p_el_direct = etree.Element(f"{{{AKN_NS}}}p")
    p_el_direct.text = p_with_bold.text  # what build() actually does
    assert p_el_direct.find(f"{{{AKN_NS}}}b") is None, "LIST_ITEM branch uses .text, not _emit_p_inline"


def test_bold_superscript_span_emits_b_only_known_limitation(meta):
    """v0.6.0: bold+superscript span emits <b> only — superscript is dropped.
    Only bold+italic nesting is handled; other combinations are not spec'd."""
    from lexau.parser import InlineSpan
    from lexau.builder import _emit_p_inline
    p = ParsedParagraph(
        ElementType.SECTION,
        number="1",
        text="CO2",
        spans=[InlineSpan(text="CO2", bold=True, superscript=True)],
    )
    p_el = etree.Element(f"{{{AKN_NS}}}p")
    _emit_p_inline(p_el, p)
    b_el = p_el.find(f"{{{AKN_NS}}}b")
    assert b_el is not None, "bold wins over superscript"
    assert b_el.text == "CO2"
    # superscript is dropped — known v0.6.0 limitation (plan only spec'd bold+italic nesting)
    assert p_el.find(f"{{{AKN_NS}}}sup") is None, "superscript not emitted when bold also set (v0.6.0 limitation)"
