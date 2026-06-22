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
    resolved, unresolved = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    ref = root.find(".//akn:ref", ns)
    assert ref is not None
    assert ref.get("href") == "#sec-6"
    assert resolved == 1
    assert unresolved == 0


def test_abbreviated_section_ref():
    root = _make_p("under s 16 of this Act")
    resolved, unresolved = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    ref = root.find(".//akn:ref", ns)
    assert ref is not None
    assert ref.get("href") == "#sec-16"


def test_subsection_ref():
    root = _make_p("as provided in s 6(1) of this Act")
    resolved, unresolved = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    ref = root.find(".//akn:ref", ns)
    assert ref is not None
    assert ref.get("href") == "#sec-6__subsec-1"


def test_cross_act_ref():
    root = _make_p("within the meaning of the Privacy Act 1988")
    resolved, unresolved = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    ref = root.find(".//akn:ref", ns)
    assert ref is not None
    assert "/akn/au/act/1988/119" in ref.get("href", "")
    assert resolved == 1


def test_unresolved_ref_has_no_href():
    root = _make_p("as defined in the Nonexistent Act 1999")
    resolved, unresolved = inject_refs(root, CORPUS_INDEX)
    ns = {"akn": AKN_NS}
    ref = root.find(".//akn:ref", ns)
    assert ref is not None
    assert ref.get("href") is None
    assert ref.get("class") == "unresolved"
    assert unresolved == 1


def test_quoted_text_skipped():
    root = _make_p('the term "section 6 means" is not a reference')
    resolved, unresolved = inject_refs(root, CORPUS_INDEX)
    assert resolved == 0


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
    resolved, _ = inject_refs(root, CORPUS_INDEX)
    assert resolved == 0
