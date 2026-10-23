"""Dictionary Schedules: unnumbered "Dictionary" ActHead 1 headings (TGA (Medical Devices) Regs, Evidence Act,
Criminal Code, CASR) become Schedules, and Schedules headed exactly "Dictionary" (numbered or not) are
definitions containers under the Commonwealth profile.

Shapes are trimmed from the real DOCX (therapeutic-goods-(medical-devices)-regulations-2002-c72,
evidence-act-1995-c35, civil-aviation-safety-regulations-1998-c102, patents-act-1990-c52).
"""
from dataclasses import replace
from datetime import date

from lxml import etree

from lexau.builder import AknBuilder
from lexau.models import ActMetadata
from lexau.parser import InlineSpan, ParsedParagraph, parse_paragraph
from lexau.profiles import CTH_PROFILE
from lexau.termlinks import inject_list_defs, inject_local_terms, inject_terms

NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
AKN = {"a": NS}


def _defn(term: str, rest: str) -> ParsedParagraph:
    p = parse_paragraph("Definition", term + rest)
    return replace(p, spans=[InlineSpan(text=term, bold=True, italic=True), InlineSpan(text=rest)])


def _p(style: str, text: str) -> ParsedParagraph:
    return parse_paragraph(style, text)


TGA = [
    _p("ActHead 2", "Part\xa01—Preliminary"),
    _p("ActHead 5", "1.1  Name of Regulations"),
    _p("subsection", "These Regulations are the Therapeutic Goods (Medical Devices) Regulations 2002."),
    _p("ActHead 1", "Schedule\xa05—Fees"),
    _p("ActHead 2", "Part\xa02—Additional fees"),
    _p("ActHead 5", "2.2  Costs of testing"),
    _p("subsection", "(1)\tIn addition to the fees mentioned in Part 1, the costs of testing are payable."),
    _p("ActHead 1", "Dictionary  "),
    _p("note(margin)", "(regulation 1.3)"),
    _p("note(text)", "Note:\tA number of expressions used in these Regulations are defined in the Act."),
    _defn("Act", " means the Therapeutic Goods Act 1989."),
    _defn("animal", " means an invertebrate or vertebrate member of the animal kingdom."),
]

EVIDENCE = [
    _p("ActHead 2", "Part\xa01—Preliminary"),
    _p("ActHead 5", "3  Definitions"),
    _p("subsection", "(1)\tExpressions defined in the Dictionary at the end of this Act have the meanings given to them in the Dictionary."),
    _p("ActHead 5", "197  Regulations"),
    _p("subsection", "The Governor-General may make regulations prescribing matters required by this Act."),
    _p("ActHead 1", "Dictionary"),
    _p("note(margin)", "Section 3"),
    _p("ActHead 2", "Part\xa01—Definitions"),
    _defn("admission", " means a previous representation that is adverse to the person's interest."),
    _p("ActHead 2", "Part\xa02—Other Expressions"),
    _p("ActHead 5", "1  References to businesses"),
    _p("subsection", "(1)\tA reference in this Act to a business includes a reference to a profession."),
]

CASR_DICT = [
    _p("ActHead 2", "Part\xa01—Preliminary"),
    _p("ActHead 5", "1.001  Name of Regulations"),
    _p("subsection", "These Regulations are the Civil Aviation Safety Regulations 1998."),
    _p("ActHead 1", "Dictionary"),
    _p("note(margin)", "(regulation 1.004)"),
    _p("ActHead 2", "Part\xa01—Definitions"),
    _defn("aeroplane", " means a power-driven heavier-than-air aircraft."),
    _p("ActHead 2", "Part\xa03—Definitions for this Part, Parts\xa042, 66, 145 and 147 and Subparts\xa0202.BA, 202.CG, 202.GE and 202.GG"),
    _p("subsection", "In this Part, Parts 42, 66, 145 and 147, and Subparts 202.BA, 202.CG, 202.GE and 202.GG:"),
    _defn("rating", " means an authorisation granted under regulation 66.080 or 66.095."),
]

PATENTS = [
    _p("ActHead 2", "Part\xa01—Preliminary"),
    _p("ActHead 5", "3  Definitions"),
    _p("subsection", "The expressions used in this Act that are defined in Schedule 1 have the meanings given by that Schedule."),
    _p("ActHead 2", "Part\xa02—Infringement"),
    _p("ActHead 5", "124  Interpretation"),
    _p("subsection", "In this Part:"),
    _defn("patentee", " includes an exclusive licensee."),
    _p("ActHead 1", "Schedule\xa01—Dictionary"),
    _p("note(margin)", "Section 3"),
    _p("subsection", "In this Act, unless the contrary intention appears:"),
    _defn("patentee", " means the person for the time being entered in the Register as the grantee of a patent."),
    _defn("Register", " means the Register of Patents kept under section 186."),
]


def _build(paras: list[ParsedParagraph], profile=CTH_PROFILE):
    meta = ActMetadata(name="Test Act 2000", title_id="t", comp_id="t", comp_num="1",
                       year=2000, number=1, effective_date=date(2026, 7, 1))
    b = AknBuilder(meta, profile=profile)
    for p in paras:
        b.add(replace(p, volume_index=0))
    return b.build_with_report({}, last_volume_path=None)


def _scheds(xml) -> list[etree._Element]:
    return xml.xpath("//a:hcontainer[@name='schedule']", namespaces=AKN)


def _term_refs(el) -> list[tuple[str, str]]:
    return [("".join(t.itertext()).strip(), t.get("refersTo")) for t in el.xpath(".//a:term", namespaces=AKN)]


# --- structure ----------------------------------------------------------------------------------


def test_unnumbered_dictionary_after_a_schedule_is_its_own_schedule() -> None:
    xml, _ = _build(TGA, profile=None)
    scheds = _scheds(xml)
    assert [s.get("eId") for s in scheds] == ["schedule-1", "schedule-2"]
    dic = scheds[1]
    assert dic.find("a:num", namespaces=AKN) is None
    assert dic.findtext("a:heading", namespaces=AKN) == "Dictionary"
    assert "animal kingdom" in "".join(dic.itertext())
    assert "animal kingdom" not in "".join(scheds[0].itertext())


def test_unnumbered_dictionary_after_the_body_ends_the_body() -> None:
    xml, _ = _build(EVIDENCE, profile=None)
    sections = xml.xpath("//a:body//a:section/@eId", namespaces=AKN)
    assert sections == ["part-1__sec-3", "part-1__sec-197"]
    assert "adverse to the person" not in "".join(xml.xpath("//a:body", namespaces=AKN)[0].itertext())
    (dic,) = _scheds(xml)
    assert dic.get("eId") == "schedule-1"
    assert dic.findtext("a:heading", namespaces=AKN) == "Dictionary"
    assert dic.xpath("a:hcontainer[@name='part']/@eId", namespaces=AKN) == ["schedule-1__part-1", "schedule-1__part-2"]


def test_dictionary_text_in_other_styles_is_not_a_heading() -> None:
    paras = [
        _p("ActHead 2", "Part\xa01—Preliminary"),
        _p("ActHead 5", "3  Definitions"),
        _p("Definition", "Dictionary"),
        _p("subsection", "Dictionary"),
        _p("ActHead 1", "Dictionary of terms"),
        _p("subsection", "The end."),
    ]
    xml, _ = _build(paras, profile=None)
    assert _scheds(xml) == []


# --- terms ---------------------------------------------------------------------------------------


def test_unnumbered_dictionary_terms_are_act_wide_with_cth_profile() -> None:
    xml, report = _build(TGA)
    dic = _scheds(xml)[1]
    assert _term_refs(dic) == [("Act", "#term-act"), ("animal", "#term-animal")]
    assert report.local_term_scope.get("skipped_no_scope_in_schedule", 0) == 0


def test_dictionary_parts_are_tagged_act_wide() -> None:
    xml, _ = _build(EVIDENCE)
    assert _term_refs(_scheds(xml)[0]) == [("admission", "#term-admission")]


def test_dictionary_part_limited_to_other_parts_is_not_tagged() -> None:
    xml, report = _build(CASR_DICT)
    dic = _scheds(xml)[0]
    assert _term_refs(dic) == [("aeroplane", "#term-aeroplane")]
    assert not xml.xpath("//a:TLCTerm[@eId='rating' or starts-with(@eId, 'rating')]", namespaces=AKN)
    assert all("rating" not in (r or "") for _, r in _term_refs(xml))


def test_numbered_dictionary_schedule_terms_are_act_wide_with_cth_profile() -> None:
    xml, _ = _build(PATENTS)
    (dic,) = _scheds(xml)
    assert dic.findtext("a:num", namespaces=AKN) == "1"
    assert _term_refs(dic) == [("patentee", "#term-patentee"), ("Register", "#term-register")]


def test_flags_off_leaves_dictionary_schedules_untagged() -> None:
    for paras in (TGA, EVIDENCE, PATENTS):
        xml, _ = _build(paras, profile=None)
        assert all(_term_refs(s) == [] for s in _scheds(xml))


def test_duplicate_definition_in_part_and_dictionary_keeps_both() -> None:
    xml, report = _build(PATENTS)
    defs = [t for t in _term_refs(xml) if t[1] == "#term-patentee"]
    assert len(defs) == 2
    body = xml.xpath("//a:body", namespaces=AKN)[0]
    assert _term_refs(body) == [("patentee", "#term-patentee")]
    assert report.duplicate_terms == 1
    tlc = xml.xpath("//a:TLCTerm[@eId='term-patentee']", namespaces=AKN)
    assert len(tlc) == 1
    again, _ = _build(PATENTS)
    assert etree.tostring(xml) == etree.tostring(again)


# --- guards at the term-pass level ------------------------------------------------------------


def _act(schedules: str, body: str = "") -> etree._Element:
    return etree.fromstring(
        f'<akomaNtoso xmlns="{NS}"><act><body>{body}</body>'
        f"<attachments><attachment>{schedules}</attachment></attachments></act></akomaNtoso>"
    )


def test_amending_schedule_headed_dictionary_is_not_tagged() -> None:
    root = _act(
        '<hcontainer name="schedule" eId="schedule-11"><num>11</num><heading>Dictionary</heading>'
        '<hcontainer name="item" eId="schedule-11__item-1"><num>1</num><heading>Subsection 995-1(1)</heading>'
        "<content><p>Insert:</p></content>"
        '<quotedStructure><content><p><b><i>widget</i></b> means a thing.</p></content></quotedStructure>'
        "</hcontainer></hcontainer>"
    )
    reg, n = inject_terms(root, dictionary_schedules=True)
    n += inject_list_defs(root, reg, dictionary_schedules=True)
    assert n == 0 and reg == {}


def test_amending_dictionary_schedule_without_quoted_structure_is_not_tagged() -> None:
    root = _act(
        '<hcontainer name="schedule" eId="schedule-3"><num>3</num><heading>Dictionary</heading>'
        '<hcontainer name="item" eId="schedule-3__item-1"><num>1</num><heading>Section 3</heading>'
        "<content><p><b><i>widget</i></b> means a thing.</p></content>"
        "</hcontainer></hcontainer>"
    )
    reg, n = inject_terms(root, dictionary_schedules=True)
    assert n == 0 and reg == {}


def test_definitions_headed_schedule_is_not_a_dictionary() -> None:
    root = _act(
        '<hcontainer name="schedule" eId="schedule-1"><num>1</num><heading>Ownership definitions</heading>'
        "<content><p><b><i>widget</i></b> means a thing.</p></content></hcontainer>"
    )
    reg, n = inject_terms(root, dictionary_schedules=True)
    assert n == 0


def test_dictionary_schedules_off_by_default() -> None:
    root = _act(
        '<hcontainer name="schedule" eId="schedule-1"><num>1</num><heading>Dictionary</heading>'
        "<content><p><b><i>widget</i></b> means a thing.</p></content></hcontainer>"
    )
    reg, n = inject_terms(root)
    assert n == 0
    reg, n = inject_terms(root, dictionary_schedules=True)
    assert n == 1 and "term-widget" in reg


def test_part_limited_dictionary_part_is_left_to_nobody() -> None:
    """Fail closed: the local pass treats the whole Dictionary as inject_terms territory, so a
    Part-limited Dictionary Part stays untagged rather than tagged Act-wide."""
    root = _act(
        '<hcontainer name="schedule" eId="schedule-1"><heading>Dictionary</heading>'
        '<hcontainer name="part" eId="schedule-1__part-3"><num>3</num>'
        "<heading>Definitions for this Part, Parts 42, 66, 145 and 147</heading>"
        "<content><p>In this Part, Parts 42, 66, 145 and 147:</p></content>"
        "<content><p><b><i>rating</i></b> means an authorisation.</p></content>"
        "</hcontainer></hcontainer>"
    )
    stats: dict[str, int] = {}
    reg, n = inject_terms(root, dictionary_schedules=True)
    n += inject_list_defs(root, reg, dictionary_schedules=True)
    n += inject_local_terms(root, reg, stats=stats)
    assert n == 0 and reg == {}
