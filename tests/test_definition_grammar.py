"""Extended definition grammar (ParserProfile.extended_definitions): state and territory shapes."""
from lxml import etree

from lexau.termlinks import complete_list_definitions, inject_list_defs, inject_terms

NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
A = {"a": NS}


def _doc(body: str, heading: str = "Definitions") -> etree._Element:
    return etree.fromstring(
        f'<akomaNtoso xmlns="{NS}"><act><body><section eId="s1"><num>1</num><heading>{heading}</heading>'
        f"{body}</section></body></act></akomaNtoso>"
    )


def _run(root: etree._Element, extended: bool = True) -> dict[str, str]:
    reg, _ = inject_terms(root, extended=extended)
    inject_list_defs(root, reg, extended=extended)
    complete_list_definitions(root, ":—–" if extended else ":")
    return reg


def _terms(root: etree._Element) -> list[str]:
    return ["".join(t.itertext()) for t in root.xpath("//a:term", namespaces=A)]


def _text(root: etree._Element) -> str:
    return " ".join("".join(root.xpath("//a:body", namespaces=A)[0].itertext()).split())


def test_colon_lead_in_with_following_list_is_tagged_and_folded() -> None:
    root = _doc(
        "<content><p><b><i>other</i></b> means a thing.</p><p><b><i>application</i></b> means:</p></content>"
        "<paragraph><num>(a)</num><content><p>an application for access; or</p></content></paragraph>"
        "<paragraph><num>(b)</num><content><p>a request.</p></content></paragraph>"
    )
    _run(root)
    assert _terms(root) == ["other", "application"]
    d = root.xpath("//a:p[a:term[.='application']]/a:def", namespaces=A)[0]
    assert "an application for access; or" in "".join(d.itertext())


def test_dash_lead_in_is_folded() -> None:
    root = _doc(
        "<content><p><b><i>class</i></b> means—</p></content>"
        "<paragraph><num>(a)</num><content><p>one kind; or</p></content></paragraph>"
    )
    _run(root)
    assert _terms(root) == ["class"]
    assert "one kind; or" in "".join(root.xpath("//a:def", namespaces=A)[0].itertext())


def test_signpost_with_formatted_term_keeps_source_text() -> None:
    root = _doc("<content><p><i>agency</i> see section 18.</p></content>")
    _run(root)
    assert _terms(root) == ["agency"]
    assert _text(root).endswith("agency see section 18.")


def test_qualified_signpost_plain_text() -> None:
    root = _doc("<content><p>affected individual, for Part 6A—see section 59D(2).</p></content>")
    _run(root)
    assert _terms(root) == ["affected individual"]
    assert "affected individual, for Part 6A—see section 59D(2)." in _text(root)


def test_signpost_term_containing_comma() -> None:
    root = _doc("<content><p>collects, personal information—see section 15.</p></content>")
    _run(root)
    assert _terms(root) == ["collects, personal information"]


def test_has_the_meaning_given_in() -> None:
    root = _doc("<content><p>compliance notice has the meaning given in section 122(1);</p></content>")
    _run(root)
    assert _terms(root) == ["compliance notice"]


def test_qualified_means() -> None:
    root = _doc("<content><p>relevant agency, for a government contract, means a body.</p></content>")
    _run(root)
    assert _terms(root) == ["relevant agency"]


def test_bare_lead_in_needs_following_list() -> None:
    with_list = _doc(
        "<content><p>australian law—</p></content>"
        "<paragraph><num>(a)</num><content><p>a statute; or</p></content></paragraph>"
    )
    _run(with_list)
    assert _terms(with_list) == ["australian law"]
    without = _doc("<content><p>australian law—</p></content>")
    _run(without)
    assert _terms(without) == []


def test_prose_is_not_tagged() -> None:
    root = _doc(
        "<content><p>In this section—</p><p>Note: see section 5 for details.</p>"
        "<p>The Minister may, by notice, require a report.</p></content>"
        "<paragraph><num>(a)</num><content><p>a thing;</p></content></paragraph>"
    )
    _run(root)
    assert _terms(root) == []


def test_default_mode_unchanged() -> None:
    body = (
        "<content><p>affected individual, for Part 6A—see section 59D(2).</p>"
        "<p><i>agency</i> see section 18.</p>"
        "<p>compliance notice has the meaning given in section 122(1);</p>"
        "<p><b><i>plain</i></b> means a thing.</p></content>"
    )
    root = _doc(body)
    _run(root, extended=False)
    assert _terms(root) == ["plain"]


def test_bare_lead_in_inside_list_item_is_not_a_definition() -> None:
    root = _doc(
        "<content><p><b><i>health information</i></b> means:</p></content>"
        "<paragraph><num>(a)</num><content><p>personal information about:</p></content>"
        "<paragraph><num>(i)</num><content><p>a person’s health; or</p></content></paragraph></paragraph>"
    )
    _run(root)
    assert _terms(root) == ["health information"]
    assert "personal information about:" in "".join(root.xpath("//a:def", namespaces=A)[0].itertext())


def test_sentences_and_cross_references_are_not_definitions() -> None:
    root = _doc(
        "<content><p>For subsection (1)—the services must be for the contracting agency.</p>"
        "<p>otherwise—see section 4(4).</p>"
        "<p>A TPP code may do 1 or more of the following:</p></content>"
        "<paragraph><num>(a)</num><content><p>impose requirements;</p></content></paragraph>"
    )
    _run(root)
    assert "A TPP code may do" not in " ".join(_terms(root))
    assert "For subsection (1)" not in _terms(root)


def test_stacked_qualifiers_and_comma_see() -> None:
    root = _doc(
        "<content><p><b><i>review period</i></b>, for a privacy complaint, for chapter 5, part 1, see section 164A(1).</p>"
        "<p><b><i>modify</i></b>, for schedule 3, in relation to information, means change it.</p>"
        "<p><i>emergency</i>, see section 18(1) of the Emergency Management Act 2013.</p>"
        "<p><b><i>meaning thing</i></b> has a meaning affected by section 10;</p></content>"
    )
    _run(root)
    assert _terms(root) == ["review period", "modify", "emergency", "meaning thing"]


def test_formatted_term_with_qualifier_and_dash_lead_in_nested_in_a_list_item() -> None:
    root = _doc(
        "<paragraph><num>(a)</num><content><p>an earlier item;</p></content></paragraph>"
        "<paragraph><num>(b)</num><content><p>a later item.</p>"
        "<p><b><i>collect</i></b>, in relation to information —</p></content></paragraph>"
        "<paragraph><num>(a)</num><content><p>the information is gathered; or</p></content></paragraph>"
    )
    _run(root)
    assert _terms(root) == ["collect"]


def test_notes_and_examples_are_not_definitions_in_extended_mode() -> None:
    body = (
        "<content><p>Note\tState includes the Northern Territory.</p>"
        "<p>For example, the signpost definition 'x'—see section 5.</p>"
        "<p><b><i>real</i></b> means a thing.</p></content>"
    )
    assert _terms(_run_doc(body, True)) == ["real"]


def _run_doc(body: str, extended: bool) -> etree._Element:
    root = _doc(body)
    _run(root, extended=extended)
    return root
