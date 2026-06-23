from lxml import etree
from lexau.termlinks import inject_terms

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
AKN_TAG = f"{{{AKN_NS}}}"


def _make_section(heading: str, *para_texts: str) -> etree._Element:
    """Build a minimal AKN <section> with a heading and body <p> elements."""
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section", eId="sec-6")
    h = etree.SubElement(sec, f"{AKN_TAG}heading")
    h.text = heading
    content = etree.SubElement(sec, f"{AKN_TAG}content")
    for text in para_texts:
        p = etree.SubElement(content, f"{AKN_TAG}p")
        p.text = text
    return root


def test_means_pattern_injects_term_and_def():
    root = _make_section(
        "Definitions",
        '"personal information" means information or an opinion about an identified individual.',
    )
    registry, count = inject_terms(root)
    assert count == 1
    assert "term-personal-information" in registry
    assert registry["term-personal-information"] == "personal information"

    p = root.find(f".//{AKN_TAG}p")
    term_el = p.find(f"{AKN_TAG}term")
    assert term_el is not None
    assert term_el.get("refersTo") == "#term-personal-information"
    def_el = p.find(f"{AKN_TAG}def")
    assert def_el is not None
    assert "identified individual" in def_el.text


def test_includes_pattern_injects_term_and_def():
    root = _make_section(
        "Interpretation",
        '"document" includes a map, plan, drawing or photograph.',
    )
    registry, count = inject_terms(root)
    assert count == 1
    assert "term-document" in registry
    p = root.find(f".//{AKN_TAG}p")
    assert p.find(f"{AKN_TAG}def") is not None


def test_non_definition_section_not_processed():
    root = _make_section(
        "Objects of this Act",
        '"personal information" means information about an individual.',
    )
    registry, count = inject_terms(root)
    assert count == 0
    assert len(registry) == 0
    p = root.find(f".//{AKN_TAG}p")
    assert p.find(f"{AKN_TAG}term") is None


def test_eid_derivation_kebab_case():
    root = _make_section(
        "Definitions",
        '"eligible data breach" means a data breach meeting the criteria in section 26WA.',
    )
    registry, _ = inject_terms(root)
    assert "term-eligible-data-breach" in registry
    assert registry["term-eligible-data-breach"] == "eligible data breach"


def test_multiple_definitions_in_one_section():
    root = _make_section(
        "Definitions",
        '"personal information" means information about an individual.',
        '"sensitive information" includes health information about an individual.',
    )
    registry, count = inject_terms(root)
    assert count == 2
    assert "term-personal-information" in registry
    assert "term-sensitive-information" in registry


def test_meaning_of_heading_also_detected():
    root = _make_section(
        "Meaning of personal information",
        '"personal information" means information about an identified individual.',
    )
    registry, count = inject_terms(root)
    assert count == 1


def test_p_text_cleared_after_injection():
    root = _make_section(
        "Definitions",
        '"individual" means a natural person.',
    )
    inject_terms(root)
    p = root.find(f".//{AKN_TAG}p")
    # p.text should be None or empty after injection (content moved to <term> + <def>)
    assert (p.text or "") == ""


def test_unquoted_means_pattern_injects_term_and_def():
    # Privacy Act s.6(1) form: italicised in DOCX, plain text after parsing — no quotes
    root = _make_section(
        "Interpretation",
        "personal information means information or an opinion about an identified individual.",
    )
    registry, count = inject_terms(root)
    assert count == 1
    assert "term-personal-information" in registry
    p = root.find(f".//{AKN_TAG}p")
    term_el = p.find(f"{AKN_TAG}term")
    assert term_el is not None
    assert term_el.get("refersTo") == "#term-personal-information"
    # Unquoted form: term_el.text should NOT have surrounding quotes
    assert term_el.text == "personal information"
    assert p.find(f"{AKN_TAG}def") is not None


def test_unquoted_includes_pattern():
    root = _make_section(
        "Definitions",
        "base rate of pay includes the minimum wage rate payable to the employee.",
    )
    registry, count = inject_terms(root)
    assert count == 1
    assert "term-base-rate-of-pay" in registry


def test_nested_p_in_subsection_processed():
    # Definitions sections often use <subsection>/<content>/<p> nesting in real AKN output
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section", eId="sec-6")
    h = etree.SubElement(sec, f"{AKN_TAG}heading")
    h.text = "Definitions"
    subsec = etree.SubElement(sec, f"{AKN_TAG}subsection", eId="sec-6__subsec-1")
    content = etree.SubElement(subsec, f"{AKN_TAG}content")
    p = etree.SubElement(content, f"{AKN_TAG}p")
    p.text = '"eligible data breach" means a data breach as described in section 26WA.'
    registry, count = inject_terms(root)
    assert count == 1
    assert "term-eligible-data-breach" in registry


def test_duplicate_term_eids_last_write_wins():
    # Same term defined twice — registry keeps last definition; both <p> elements get markup
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section", eId="sec-6")
    h = etree.SubElement(sec, f"{AKN_TAG}heading")
    h.text = "Definitions"
    content = etree.SubElement(sec, f"{AKN_TAG}content")
    p1 = etree.SubElement(content, f"{AKN_TAG}p")
    p1.text = '"personal information" means information about an individual.'
    p2 = etree.SubElement(content, f"{AKN_TAG}p")
    p2.text = '"personal information" means any information relating to a natural person.'
    registry, count = inject_terms(root)
    assert count == 2  # both <p> elements get markup
    assert "term-personal-information" in registry  # last definition wins
