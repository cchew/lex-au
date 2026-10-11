"""Step A: 'In this Act, X means ...' outside definitions sections (ParserProfile.scope_phrase_definitions)."""
from lxml import etree

from lexau.termlinks import complete_list_definitions, inject_scope_phrase_terms, inject_terms

NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
A = {"a": NS}


def _doc(body: str, heading: str = "Meaning of personal information") -> etree._Element:
    return etree.fromstring(
        f'<akomaNtoso xmlns="{NS}"><act><body><section eId="s1"><num>4</num><heading>{heading}</heading>'
        f"{body}</section></body></act></akomaNtoso>"
    )


def _run(root: etree._Element) -> list[str]:
    reg, _ = inject_terms(root, extended=True)
    inject_scope_phrase_terms(root, reg)
    complete_list_definitions(root, ":—–")
    return ["".join(t.itertext()) for t in root.xpath("//a:term", namespaces=A)]


def _text(root: etree._Element) -> str:
    return " ".join("".join(root.xpath("//a:body", namespaces=A)[0].itertext()).split())


def test_formatted_term_after_scope_phrase() -> None:
    root = _doc("<content><p>In this Act, <b><i>personal information</i></b> means information about a person.</p></content>")
    assert _run(root) == ["personal information"]
    p = root.xpath("//a:p", namespaces=A)[0]
    assert "".join(p.itertext()) == "In this Act, personal information means information about a person."
    assert p.text == "In this Act, "


def test_article_before_the_term_is_kept_as_prefix() -> None:
    root = _doc("<content><p>In this Act, an <i>agency</i> means—</p></content><paragraph><num>(a)</num><content><p>a body.</p></content></paragraph>")
    assert _run(root) == ["agency"]
    assert "In this Act, an agency means" in _text(root)


def test_for_this_act_plain_text_fallback() -> None:
    root = _doc("<content><p>For this Act, a public sector agency means a department.</p></content>")
    assert _run(root) == ["public sector agency"]


def test_scoped_phrases_are_not_act_wide() -> None:
    root = _doc(
        "<content><p>In this section, <i>judicial functions</i> means a thing.</p>"
        "<p>In this Part, <i>information</i> means other things.</p></content>"
    )
    assert _run(root) == []


def test_exclusion_and_sentences_are_not_definitions() -> None:
    root = _doc(
        "<content><p>In this Act, a document does not include a document mentioned in schedule 1.</p>"
        "<p>In this Act, a reference to a thing includes a reference to another thing.</p>"
        "<p>In this Act, the Minister may make guidelines.</p></content>"
    )
    assert _run(root) == []


def test_already_tagged_paragraph_is_left_alone() -> None:
    root = _doc("<content><p>In this Act, <b><i>agency</i></b> means a body.</p></content>", heading="Definitions")
    names = _run(root)
    assert names.count("agency") <= 1
