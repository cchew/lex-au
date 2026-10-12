"""Step B extraction: locally scoped definitions (ParserProfile.local_definitions)."""
from lxml import etree

from lexau.termlinks import inject_local_terms, inject_scope_phrase_terms, inject_terms

NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
A = {"a": NS}


def _doc(section_body: str, heading: str = "Protection of confidential information") -> etree._Element:
    return etree.fromstring(
        f'<akomaNtoso xmlns="{NS}"><act><body><part eId="part-1"><num>1</num><heading>Part</heading>'
        f'<section eId="part-1__sec-5"><num>5</num><heading>{heading}</heading>{section_body}</section>'
        f'<section eId="part-1__sec-6"><num>6</num><heading>Other</heading><content><p>Plain.</p></content></section>'
        f"</part></body></act></akomaNtoso>"
    )


def _run(root: etree._Element) -> dict[str, str]:
    reg, _ = inject_terms(root, extended=True)
    inject_scope_phrase_terms(root, reg)
    inject_local_terms(root, reg)
    return reg


def _refs(root: etree._Element) -> list[str]:
    return [t.get("refersTo") for t in root.xpath("//a:term", namespaces=A)]


def test_formatted_term_in_ordinary_section_is_local() -> None:
    root = _doc("<content><p><b><i>disclose</i></b> means divulge or communicate.</p></content>")
    reg = _run(root)
    assert _refs(root) == ["#term-disclose--part-1__sec-5"]
    assert reg == {"term-disclose--part-1__sec-5": "disclose"}


def test_scope_phrase_names_the_container() -> None:
    root = _doc("<content><p>In this Part, <i>information</i> means a thing.</p></content>")
    _run(root)
    assert _refs(root) == ["#term-information--part-1"]
    p = root.xpath("//a:p[a:term]", namespaces=A)[0]
    assert p.text == "In this Part, "


def test_plain_text_outside_definitions_sections_is_not_tagged() -> None:
    root = _doc("<content><p>disclose means divulge or communicate.</p><p>The privacy commissioner has the following functions—</p></content>")
    _run(root)
    assert _refs(root) == []


def test_act_wide_scope_phrase_is_left_to_step_a() -> None:
    root = _doc("<content><p>In this Act, <i>agency</i> means a body.</p></content>")
    _run(root)
    assert _refs(root) == ["#term-agency"]


def test_local_term_id_differs_from_the_act_wide_id() -> None:
    root = _doc("<content><p><i>use</i> means employ.</p></content>", heading="Misc")
    reg = _run(root)
    assert "term-use--part-1__sec-5" in reg and "term-use" not in reg


def test_sentences_and_rules_of_construction_are_not_local_terms() -> None:
    root = _doc(
        "<content><p><i>Note</i> means something odd.</p><p>For example, <i>x</i> means y.</p>"
        "<p><i>a reference to a thing</i> includes another thing.</p></content>"
    )
    _run(root)
    assert _refs(root) == []


def test_quoted_amendment_text_is_not_a_definition_of_this_act() -> None:
    root = etree.fromstring(
        f'<akomaNtoso xmlns="{NS}"><act><body><section eId="s1"><num>1</num><heading>Amendment</heading>'
        "<content><p>Insert:</p></content>"
        '<quotedStructure><section eId="q1"><num>2</num><heading>Other</heading>'
        "<content><p>In this Act, <i>widget</i> means a thing.</p>"
        "<p><i>gadget</i> means a device.</p></content></section></quotedStructure>"
        "</section></body></act></akomaNtoso>"
    )
    reg, _ = inject_terms(root, extended=True)
    inject_scope_phrase_terms(root, reg)
    inject_local_terms(root, reg)
    assert root.xpath("//a:term", namespaces=A) == []


def test_closing_quote_without_opening_quote_is_skipped() -> None:
    root = _doc("<content><p><i>repeal day</i> has the same meaning as in Part 8 of the Sale Act 1994.”.</p></content>")
    _run(root)
    assert _refs(root) == []


def test_asterisk_links_ignore_local_terms() -> None:
    from lexau.quantlinks import inject_asterisk_refs

    root = _doc(
        "<content><p><i>amounts withheld</i> means the sum withheld.</p>"
        "<p>The *amounts withheld exceeded $1 million.</p></content>"
    )
    reg = _run(root)
    inject_asterisk_refs(root, {k: v for k, v in reg.items() if "--" not in k})
    usage = [x for x in root.xpath("//a:p", namespaces=A) if "exceeded" in "".join(x.itertext())][0]
    assert "".join(usage.itertext()) == "The *amounts withheld exceeded $1 million."
