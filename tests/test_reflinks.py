from __future__ import annotations

import pytest
from lxml import etree
from lexau.reflinks import inject_refs

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
AKN = f"{{{AKN_NS}}}"


def _make_p(text: str) -> etree._Element:
    root = etree.fromstring(
        f'<akomaNtoso xmlns="{AKN_NS}">'
        f'  <act name="act"><body>'
        f'    <section eId="sec-16">'
        f'      <content><p>{text}</p></content>'
        f'    </section>'
        f'  </body></act>'
        f'</akomaNtoso>'
    )
    return root


CORPUS_INDEX = {
    "Privacy Act 1988": {"frbr_uri": "/akn/au/act/1988/119/eng@2024-01-01"},
    "Fair Work Act 2009": {"frbr_uri": "/akn/au/act/2009/28/eng@2024-01-01"},
}


def test_same_act_section_ref():
    root = _make_p("as defined in section 6 of this Act")
    resolved, unresolved, *_ = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    ref = root.find(".//akn:ref", ns)
    assert ref is not None
    assert ref.get("href") == "#sec-6"
    assert resolved == 1
    assert unresolved == 0


def test_abbreviated_section_ref():
    root = _make_p("under s 16 of this Act")
    resolved, unresolved, *_ = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    ref = root.find(".//akn:ref", ns)
    assert ref is not None
    assert ref.get("href") == "#sec-16"


def test_subsection_ref():
    root = _make_p("as provided in s 6(1) of this Act")
    resolved, unresolved, *_ = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    ref = root.find(".//akn:ref", ns)
    assert ref is not None
    assert ref.get("href") == "#sec-6__subsec-1"


def test_cross_act_ref():
    root = _make_p("within the meaning of the Privacy Act 1988")
    resolved, unresolved, *_ = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    ref = root.find(".//akn:ref", ns)
    assert ref is not None
    assert "/akn/au/act/1988/119" in ref.get("href", "")
    assert resolved == 1


def test_unresolved_ref_has_no_href():
    root = _make_p("as defined in the Nonexistent Act 1999")
    resolved, unresolved, *_ = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    ref = root.find(".//akn:ref", ns)
    assert ref is not None
    assert ref.get("href") is None
    assert ref.get("class") == "unresolved"
    assert unresolved == 1


def test_quoted_text_skipped():
    root = _make_p('the term "section 6 means" is not a reference')
    resolved, unresolved, *_ = inject_refs(root, CORPUS_INDEX)
    assert resolved == 0


def test_three_level_inline_ref():
    root = _make_p("as provided in s 6(1)(a) of this Act")
    resolved, *_ = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    ref = root.find(".//akn:ref", ns)
    assert ref is not None
    assert ref.get("href") == "#sec-6__subsec-1__para-a"
    assert resolved == 1


def test_part_intra_act_ref():
    root = _make_p("as set out in Part III")
    resolved, *_ = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    ref = root.find(".//akn:ref", ns)
    assert ref is not None
    assert ref.get("href") == "#part-III"
    assert resolved == 1


def test_division_intra_act_ref():
    root = _make_p("as defined in Division 3")
    resolved, *_ = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    ref = root.find(".//akn:ref", ns)
    assert ref is not None
    assert ref.get("href") == "#dvs-3"
    assert resolved == 1


def test_part_of_another_act_not_matched():
    # "Part III of the Criminal Code Act 1995" — part_div should NOT match
    root = _make_p("under Part III of the Criminal Code Act 1995")
    inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    refs = root.findall(".//akn:ref", ns)
    hrefs = [r.get("href", "") for r in refs]
    assert "#part-III" not in hrefs


def test_subsidiary_legislation_unresolved():
    root = _make_p("under the Privacy Regulation 2013")
    resolved, unresolved, *_ = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    ref = root.find(".//akn:ref", ns)
    assert ref is not None
    assert ref.get("class") == "unresolved"
    assert unresolved == 1


def test_definitional_ref_subsection():
    root = _make_p("as defined in subsection 6(1)")
    resolved, *_ = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    ref = root.find(".//akn:ref", ns)
    assert ref is not None
    assert ref.get("href") == "#sec-6__subsec-1"
    assert resolved == 1


def test_definitional_ref_section_only():
    root = _make_p("within the meaning of section 6 of this Act")
    resolved, *_ = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    ref = root.find(".//akn:ref", ns)
    assert ref is not None
    assert ref.get("href") == "#sec-6"


def test_heading_text_skipped():
    root = etree.fromstring(
        f'<akomaNtoso xmlns="{AKN_NS}">'
        f'  <act name="act"><body>'
        f'    <section eId="sec-1">'
        f'      <heading>section 6 reference in heading</heading>'
        f'      <content><p>Normal body text.</p></content>'
        f'    </section>'
        f'  </body></act>'
        f'</akomaNtoso>'
    )
    resolved, *_ = inject_refs(root, CORPUS_INDEX)
    assert resolved == 0


# ---------------------------------------------------------------------------
# Task 10: <rref> range reference tests
# ---------------------------------------------------------------------------

def _make_p_with_sections(text: str, section_eids: list[str]) -> etree._Element:
    """Build a document with explicit section eIds so rref can resolve endpoints."""
    sections_xml = "".join(
        f'<section eId="{eid}"><content><p>.</p></content></section>'
        for eid in section_eids
    )
    return etree.fromstring(
        f'<akomaNtoso xmlns="{AKN_NS}">'
        f'  <act name="act"><body>'
        f'    {sections_xml}'
        f'    <section eId="sec-99"><content><p>{text}</p></content></section>'
        f'  </body></act>'
        f'</akomaNtoso>'
    )


def test_rref_emitted():
    """'sections 7 to 12' with both eIds in corpus → <rref from="#sec-7" upTo="#sec-12">"""
    root = _make_p_with_sections("see sections 7 to 12 for details", ["sec-7", "sec-12"])
    resolved, unresolved, range_resolved, range_unresolved = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    rref = root.find(".//akn:rref", ns)
    assert rref is not None, "Expected <rref> element to be emitted"
    assert rref.get("from") == "#sec-7"
    assert rref.get("upTo") == "#sec-12"
    assert rref.text == "sections 7 to 12"
    assert range_resolved == 1
    assert range_unresolved == 0


def test_rref_unresolvable():
    """Endpoint not in corpus → no <rref>, range_unresolved counter incremented."""
    # sec-99 exists (the wrapping section), but sec-999 does not
    root = _make_p_with_sections("see sections 99 to 999 for details", ["sec-99"])
    resolved, unresolved, range_resolved, range_unresolved = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    rref = root.find(".//akn:rref", ns)
    assert rref is None, "Expected no <rref> when an endpoint is unresolvable"
    assert range_unresolved == 1
    assert range_resolved == 0


def test_rref_not_date():
    """'from 1 July to 30 June' must NOT produce an <rref> (it is a date range)."""
    root = _make_p_with_sections("from 1 July to 30 June", [])
    resolved, unresolved, range_resolved, range_unresolved = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    rref = root.find(".//akn:rref", ns)
    assert rref is None, "Date ranges must not produce <rref>"
