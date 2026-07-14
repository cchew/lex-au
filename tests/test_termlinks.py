from lxml import etree
from lexau.termlinks import inject_terms, inject_list_defs

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


def test_meaning_and_operation_not_a_definition_section():
    root = _make_section(
        "Meaning and operation of orders",
        '"term" means something.',
    )
    registry, count = inject_terms(root)
    assert count == 0, "Heading 'Meaning and operation of orders' must not trigger term injection"


def test_this_act_means_not_a_term():
    root = _make_section(
        "Definitions",
        "This Act means the Privacy Act 1988 as in force from time to time.",
    )
    registry, count = inject_terms(root)
    assert count == 0
    assert "term-this-act" not in registry


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


def test_process_p_handles_italic_mixed_content():
    """inject_terms processes <p><i>personal information</i> means ...</p> correctly."""
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section", eId="sec-6")
    h = etree.SubElement(sec, f"{AKN_TAG}heading")
    h.text = "Definitions"
    content = etree.SubElement(sec, f"{AKN_TAG}content")
    # Simulate what builder emits when a run is italic
    p = etree.SubElement(content, f"{AKN_TAG}p")
    i_el = etree.SubElement(p, f"{AKN_TAG}i")
    i_el.text = "personal information"
    i_el.tail = " means information about an identified individual."

    registry, count = inject_terms(root)
    assert count == 1
    assert "term-personal-information" in registry
    # After injection, <p> should have <term> and <def> children
    term_el = p.find(f"{AKN_TAG}term")
    assert term_el is not None
    assert term_el.get("refersTo") == "#term-personal-information"
    def_el = p.find(f"{AKN_TAG}def")
    assert def_el is not None
    assert "identified individual" in def_el.text


def test_process_p_mixed_content_clears_inline_markup():
    """After injection, original <i> child should be gone."""
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section", eId="sec-6")
    h = etree.SubElement(sec, f"{AKN_TAG}heading")
    h.text = "Definitions"
    content = etree.SubElement(sec, f"{AKN_TAG}content")
    p = etree.SubElement(content, f"{AKN_TAG}p")
    i_el = etree.SubElement(p, f"{AKN_TAG}i")
    i_el.text = "document"
    i_el.tail = " includes a map."

    inject_terms(root)
    # <i> child should be replaced by <term> + <def>
    assert p.find(f"{AKN_TAG}i") is None
    assert p.find(f"{AKN_TAG}term") is not None


def test_process_p_structural_boundary_beats_greedy_relational_capture():
    """Real case (Corporations Act 2001): <b><i>lawyer</i></b> means a duly
    qualified legal practitioner and, in relation to a person, means such a
    practitioner acting for the person.

    The relational _DEF_PATTERNS entry would greedily capture "lawyer means a
    duly qualified legal practitioner and" as the definiendum (that clause itself
    contains "means"). Anchoring to the <b><i>lawyer</i></b> run instead must
    capture exactly "lawyer" as the term, AND the full remaining sentence as the
    definiens -- not just the tail after the second "means" (that would silently
    truncate the definition).
    """
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section", eId="sec-9")
    h = etree.SubElement(sec, f"{AKN_TAG}heading")
    h.text = "Definitions"
    content = etree.SubElement(sec, f"{AKN_TAG}content")
    p = etree.SubElement(content, f"{AKN_TAG}p")
    b_el = etree.SubElement(p, f"{AKN_TAG}b")
    i_el = etree.SubElement(b_el, f"{AKN_TAG}i")
    i_el.text = "lawyer"
    b_el.tail = (
        " means a duly qualified legal practitioner and, in relation to a "
        "person, means such a practitioner acting for the person."
    )

    registry, count = inject_terms(root)
    assert count == 1
    assert registry["term-lawyer"] == "lawyer"
    term_el = p.find(f"{AKN_TAG}term")
    assert term_el.text == "lawyer"
    def_el = p.find(f"{AKN_TAG}def")
    assert def_el.text == (
        "a duly qualified legal practitioner and, in relation to a person, "
        "means such a practitioner acting for the person."
    )


def test_process_p_structural_boundary_skips_exclusion_clause():
    """Real case (Corporations Act 2001): <i>lease</i> does not include a lease
    of goods that gives rise to a PPSA security interest in the goods.

    Not a new definition -- an exclusion clarifying an already-defined term. "does
    not" between the italic run and "include" breaks the immediate-adjacency
    requirement, so the structural path must decline (same outcome as the existing
    _FALSE_CONNECTOR_TAIL_RE guard for the non-structural case), leaving the
    paragraph untouched.
    """
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section", eId="sec-9")
    h = etree.SubElement(sec, f"{AKN_TAG}heading")
    h.text = "Definitions"
    content = etree.SubElement(sec, f"{AKN_TAG}content")
    p = etree.SubElement(content, f"{AKN_TAG}p")
    i_el = etree.SubElement(p, f"{AKN_TAG}i")
    i_el.text = "lease"
    i_el.tail = " does not include a lease of goods that gives rise to a PPSA security interest in the goods."

    registry, count = inject_terms(root)
    assert count == 0
    assert registry == {}
    assert p.find(f"{AKN_TAG}term") is None


# ---------------------------------------------------------------------------
# inject_list_defs tests
# ---------------------------------------------------------------------------

def _make_list_def_section(term_text: str, list_items: list[str]) -> etree._Element:
    """Build AKN <section> with a list-form definition (X means: followed by <paragraph> items)."""
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section", eId="sec-6")
    h = etree.SubElement(sec, f"{AKN_TAG}heading")
    h.text = "Definitions"
    subsec = etree.SubElement(sec, f"{AKN_TAG}subsection", eId="sec-6__subsec-1")
    content = etree.SubElement(subsec, f"{AKN_TAG}content")
    p = etree.SubElement(content, f"{AKN_TAG}p")
    p.text = term_text
    for i, item_text in enumerate(list_items, start=1):
        para = etree.SubElement(subsec, f"{AKN_TAG}paragraph", eId=f"sec-6__subsec-1__para-{i}")
        num = etree.SubElement(para, f"{AKN_TAG}num")
        num.text = str(i)
        c = etree.SubElement(para, f"{AKN_TAG}content")
        ip = etree.SubElement(c, f"{AKN_TAG}p")
        ip.text = item_text
    return root


def test_inject_list_defs_simple():
    """'sensitive information means:' with following paragraphs gets <term> + <intro>."""
    root = _make_list_def_section(
        "sensitive information means:",
        ["racial or ethnic origin; or", "political opinions; or"],
    )
    registry = {}
    count = inject_list_defs(root, registry)
    assert count == 1
    assert "term-sensitive-information" in registry
    assert registry["term-sensitive-information"] == "sensitive information"


def test_inject_list_defs_converts_content_to_intro():
    """The <content> element is renamed to <intro> after injection."""
    root = _make_list_def_section(
        "agency means:",
        ["a body corporate; or", "a natural person."],
    )
    registry = {}
    inject_list_defs(root, registry)
    subsec = root.find(f".//{AKN_TAG}subsection")
    # <content> should no longer exist; <intro> should
    assert subsec.find(f"{AKN_TAG}content") is None
    intro = subsec.find(f"{AKN_TAG}intro")
    assert intro is not None


def test_inject_list_defs_injects_term_element():
    """The lead <p> gets <term> element after injection."""
    root = _make_list_def_section(
        "enforcement body means:",
        ["the Australian Federal Police."],
    )
    registry = {}
    inject_list_defs(root, registry)
    intro = root.find(f".//{AKN_TAG}intro")
    p = intro.find(f"{AKN_TAG}p")
    term_el = p.find(f"{AKN_TAG}term")
    assert term_el is not None
    assert term_el.get("refersTo") == "#term-enforcement-body"
    assert term_el.text == "enforcement body"
    assert term_el.tail == " means:"


def test_inject_list_defs_qualifier_trimmed():
    """'contracted service provider, for a government contract, means:' uses text before first comma."""
    root = _make_list_def_section(
        "contracted service provider, for a government contract, means:",
        ["a person contracted to provide services to the government."],
    )
    registry = {}
    inject_list_defs(root, registry)
    assert "term-contracted-service-provider" in registry
    assert registry["term-contracted-service-provider"] == "contracted service provider"


def test_inject_list_defs_long_qualifier_not_capped():
    """Real case (ITAA 1936): a qualifier-style list definiendum whose full span
    (term + qualifier clause) exceeds 60 chars, but whose actual term (before the
    first comma) does not. The definiendum-length cap must apply only to the part
    before the first comma -- capping the whole span (term + qualifier) rejected
    this real, legitimate definition when first tried.
    """
    root = _make_list_def_section(
        "the relevant holding company or holding companies, in relation to "
        "another company in relation to a year of income of that other "
        "company, means:",
        ["something."],
    )
    registry = {}
    count = inject_list_defs(root, registry)
    assert count == 1
    assert "term-the-relevant-holding-company-or-holding-companies" in registry
    assert (
        registry["term-the-relevant-holding-company-or-holding-companies"]
        == "the relevant holding company or holding companies"
    )


def test_inject_list_defs_no_following_siblings_skipped():
    """A 'X means:' paragraph with no following <paragraph> siblings is not processed."""
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section", eId="sec-6")
    h = etree.SubElement(sec, f"{AKN_TAG}heading")
    h.text = "Definitions"
    content = etree.SubElement(sec, f"{AKN_TAG}content")
    p = etree.SubElement(content, f"{AKN_TAG}p")
    p.text = "agency means:"
    # No following siblings
    registry = {}
    count = inject_list_defs(root, registry)
    assert count == 0


def test_inject_list_defs_non_def_section_skipped():
    """inject_list_defs respects _is_definition_section — skips non-definition sections."""
    root = _make_list_def_section(
        "agency means:",
        ["a body corporate."],
    )
    # Change heading to non-definition
    heading = root.find(f".//{AKN_TAG}heading")
    heading.text = "Objects of this Act"
    registry = {}
    count = inject_list_defs(root, registry)
    assert count == 0


def test_inject_list_defs_stop_words_skipped():
    """'This Act means:' is not treated as a term definition."""
    root = _make_list_def_section(
        "This Act means:",
        ["the Privacy Act 1988."],
    )
    registry = {}
    count = inject_list_defs(root, registry)
    assert count == 0


def test_inject_list_defs_rejects_leading_subsection_number():
    """Real case (Corporations Act 2001): '(2A)\tIn Part 1.2A means:' -- a
    subsection-number artifact, not a definiendum. _LIST_DEF_COLON_RE previously
    had no character-class restriction (unlike _DEF_PATTERNS), so it accepted
    this. Requiring the definiendum to start with a letter rejects it outright.
    """
    root = _make_list_def_section(
        "(2A)\tIn Part 1.2A means:",
        ["something."],
    )
    registry = {}
    count = inject_list_defs(root, registry)
    assert count == 0
    assert registry == {}


def test_inject_list_defs_rejects_narrative_scoping_clause():
    """Real case (Corporations Act 2001): 'In this Division and Division 4
    transfer of a financial product means:' -- a scoping clause, not a
    definiendum. Caught by the same _is_narrative_false_positive guard used in
    _process_p (stop-opener: 'in this division').
    """
    root = _make_list_def_section(
        "In this Division transfer of a financial product means:",
        ["something."],
    )
    registry = {}
    count = inject_list_defs(root, registry)
    assert count == 0
    assert registry == {}


def test_dictionary_heading_is_a_definition_section():
    root = _make_section(
        "Dictionary",
        '"disclosure" means the act of making information available.',
    )
    registry, count = inject_terms(root)
    assert count == 1
    assert "term-disclosure" in registry


def test_the_dictionary_heading_is_a_definition_section():
    root = _make_section(
        "The Dictionary",
        '"disclosure" means the act of making information available.',
    )
    registry, count = inject_terms(root)
    assert count == 1


def test_defined_terms_heading_is_a_definition_section():
    root = _make_section(
        "Defined terms",
        '"disclosure" means the act of making information available.',
    )
    registry, count = inject_terms(root)
    assert count == 1


def test_process_p_formatted_definiens_flattened_known_limitation():
    """v0.6.0: formatted content inside the definiens is lost when _process_p
    handles a mixed-content <p>. The <def> element gets plain itertext() only."""
    from lexau.termlinks import _process_p
    # Build <p>term<i> means </i><b>body corporate</b></p>
    p_el = etree.Element(f"{AKN_TAG}p")
    p_el.text = "term"
    i_el = etree.SubElement(p_el, f"{AKN_TAG}i")
    i_el.text = " means "
    b_el = etree.SubElement(p_el, f"{AKN_TAG}b")
    b_el.text = "body corporate"

    registry = {}
    _process_p(p_el, registry)

    # <term> is injected
    term_el = p_el.find(f"{AKN_TAG}term")
    assert term_el is not None
    assert term_el.text == "term"

    # <def> gets plain text — the <b> inside definiens is flattened (known v0.6.0 limitation)
    def_el = p_el.find(f"{AKN_TAG}def")
    assert def_el is not None
    assert def_el.find(f"{AKN_TAG}b") is None, "formatted definiens flattened to plain text (v0.6.0 limitation)"
    assert "body corporate" in (def_el.text or "")


def test_parenthetical_and_asterisk_in_definiendum():
    root = _make_section(
        "Dictionary",
        "ABN (Australian Business Number) for an *entity means the entity's ABN as shown in the *Australian Business Register.",
    )
    registry, count = inject_terms(root)
    assert count == 1
    assert "term-abn-australian-business-number-for-an-entity" in registry


def test_relational_definition_in_relation_to():
    root = _make_section(
        "Dictionary",
        "Court, in relation to a matter, means any court having jurisdiction in the matter.",
    )
    registry, count = inject_terms(root)
    assert count == 1
    assert registry["term-court"] == "Court"


def test_relational_definition_with_parenthetical_qualifier():
    root = _make_section(
        "Dictionary",
        "index number, in relation to an index year, means the All Groups Consumer Price Index number.",
    )
    registry, count = inject_terms(root)
    assert count == 1
    assert "term-index-number" in registry


def test_relational_definition_comma_in_y_falls_through_unmatched():
    # Regression guard: the relational pattern's Y clause is [^,]{1,60} and
    # cannot match if Y itself contains a comma. The loop then falls through
    # to the plain unquoted pattern (index 3) -- but that pattern's
    # definiendum group excludes commas too (_DEFINIENDUM_CHARS has no ","),
    # so it also cannot span past the same internal comma. Net effect,
    # verified by running inject_terms directly: neither pattern matches and
    # no term is injected at all. This documents that actual behavior rather
    # than assuming the plain pattern silently "recovers" the term.
    root = _make_section(
        "Dictionary",
        "X, in relation to Y with a comma, and more, means Z.",
    )
    registry, count = inject_terms(root)
    assert count == 0
    assert registry == {}


def test_does_not_include_is_not_a_definition():
    root = _make_section(
        "Definitions",
        "Act does not include regulations, etc.",
    )
    registry, count = inject_terms(root)
    assert count == 0
    assert "term-act-does-not" not in registry


def test_does_not_include_inside_definiens_still_extracted():
    # Regression guard: "does not include" appearing AFTER the real connector,
    # as a legitimate exclusion clause, must NOT be treated as a false match.
    root = _make_section(
        "Definitions",
        "animal includes a dead animal and any part of an animal, but does not include a human being at any stage of development.",
    )
    registry, count = inject_terms(root)
    assert count == 1
    assert registry["term-animal"] == "animal"
    # confirm the full definiens (including "but does not include...") survived intact
    body = root.find(f".//{AKN_TAG}def")
    assert "does not include a human being" in body.text


def test_embedded_connector_falls_through_to_clean_match():
    # "lease" is genuinely defined twice in one compound sentence (plain +
    # relational). The relational pattern's non-greedy capture would otherwise
    # swallow "lease includes a sublease and" as if it were the definiendum,
    # because that clause itself contains the word "includes". Guard 1 rejects
    # that match; the loop's existing `continue` falls through to the plain
    # unquoted pattern, which correctly captures just "lease".
    root = _make_section(
        "Dictionary",
        "lease includes a sublease and, in relation to a company title interest in land, "
        "includes an agreement similar to a lease or sublease.",
    )
    registry, count = inject_terms(root)
    assert count == 1
    assert registry["term-lease"] == "lease"


def test_embedded_relative_clause_rejected():
    root = _make_section(
        "Dictionary",
        "a person (who may include the trustee) is empowered to exercise any power of appointment.",
    )
    registry, count = inject_terms(root)
    assert count == 0
    assert not any("who may" in v for v in registry.values())


def test_dangling_function_word_rejected():
    root = _make_section(
        "Dictionary",
        "Some provisions of this Subdivision say that a payment can include giving property.",
    )
    registry, count = inject_terms(root)
    assert count == 0


def test_dangling_function_word_single_word_exemption_preserved():
    # Regression guard: "will" is a real single-word term in the actual corpus
    # (Corporations Act 2001, Copyright Act 1968) meaning a testamentary
    # document. Guard 3 must not fire on single-word definienda.
    root = _make_section(
        "Dictionary",
        "will includes a codicil and any other testamentary writing.",
    )
    registry, count = inject_terms(root)
    assert count == 1
    assert registry["term-will"] == "will"


def test_stop_opener_reference_clause_rejected():
    root = _make_section(
        "Dictionary",
        "A reference in subsection (5) to successive arrangements includes a reference to:",
    )
    registry, count = inject_terms(root)
    assert count == 0


def test_stop_opener_some_provisions_rejected():
    root = _make_section(
        "Dictionary",
        "Some provisions of this Subdivision say that a payment can include giving property.",
    )
    registry, count = inject_terms(root)
    assert count == 0


def test_stop_opener_for_the_purposes_of_rejected():
    root = _make_section(
        "Dictionary",
        "For the purposes of this section a reference includes a reference to a subsidiary.",
    )
    registry, count = inject_terms(root)
    assert count == 0


def _make_level0_def(show_as: str, eid: str, def_text: str, list_items: list[str]) -> etree._Element:
    """Build a <section> with an already-injected <term>+<def> pair (the
    truncated shape _process_p produces today) directly followed, at the
    same tree level, by <paragraph> list items -- the level-0 shape."""
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section", eId="sec-6")
    h = etree.SubElement(sec, f"{AKN_TAG}heading")
    h.text = "Definitions"
    subsec = etree.SubElement(sec, f"{AKN_TAG}subsection", eId="sec-6__subsec-1")
    content = etree.SubElement(subsec, f"{AKN_TAG}content")
    p = etree.SubElement(content, f"{AKN_TAG}p")
    term_el = etree.SubElement(p, f"{AKN_TAG}term")
    term_el.set("refersTo", f"#{eid}")
    term_el.text = show_as
    term_el.tail = " means "
    def_el = etree.SubElement(p, f"{AKN_TAG}def")
    def_el.text = def_text
    for i, item_text in enumerate(list_items, start=1):
        para = etree.SubElement(subsec, f"{AKN_TAG}paragraph", eId=f"sec-6__subsec-1__para-{i}")
        c = etree.SubElement(para, f"{AKN_TAG}content")
        ip = etree.SubElement(c, f"{AKN_TAG}p")
        ip.text = item_text
    return root


def test_find_qualifying_anchor_level_0():
    """When the <def>'s own <content> is immediately followed by a
    <paragraph>, that <content> itself is the anchor (level 0)."""
    from lexau.termlinks import _find_qualifying_anchor

    root = _make_level0_def(
        "collective work", "term-collective-work", "any of the following:",
        ["an encyclopaedia;", "a newspaper;"],
    )
    def_el = root.find(f".//{AKN_TAG}def")
    anchor = _find_qualifying_anchor(def_el)
    assert anchor is not None
    assert anchor.tag == f"{AKN_TAG}content"


def test_find_qualifying_anchor_level_1_nested():
    """When the <def>'s <content> is nested inside an outer <paragraph> with
    no following siblings of its own, walk up one level to find the outer
    <paragraph>'s following siblings (mirrors bankruptcy-act-1966.xml's
    'related entity' shape)."""
    from lexau.termlinks import _find_qualifying_anchor

    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section", eId="sec-5")
    h = etree.SubElement(sec, f"{AKN_TAG}heading")
    h.text = "Interpretation"
    subsec = etree.SubElement(sec, f"{AKN_TAG}subsection", eId="sec-5__subsec-1")

    outer = etree.SubElement(subsec, f"{AKN_TAG}paragraph", eId="sec-5__subsec-1__para-b")
    c1 = etree.SubElement(outer, f"{AKN_TAG}content")
    p1 = etree.SubElement(c1, f"{AKN_TAG}p")
    p1.text = "a Registrar of the Court."
    c2 = etree.SubElement(outer, f"{AKN_TAG}content")
    p2 = etree.SubElement(c2, f"{AKN_TAG}p")
    term_el = etree.SubElement(p2, f"{AKN_TAG}term")
    term_el.set("refersTo", "#term-related-entity")
    term_el.text = "related entity"
    term_el.tail = " means "
    def_el = etree.SubElement(p2, f"{AKN_TAG}def")
    def_el.text = "any of the following:"

    etree.SubElement(subsec, f"{AKN_TAG}paragraph", eId="sec-5__subsec-1__para-a")

    anchor = _find_qualifying_anchor(def_el)
    assert anchor is not None
    assert anchor.tag == f"{AKN_TAG}paragraph"
    assert anchor.get("eId") == "sec-5__subsec-1__para-b"


def test_find_qualifying_anchor_no_following_list_returns_none():
    """A colon-terminated <def> with genuinely no following list content
    anywhere returns None."""
    from lexau.termlinks import _find_qualifying_anchor

    root = _make_level0_def(
        "class", "term-class", "any of these:", [],
    )
    def_el = root.find(f".//{AKN_TAG}def")
    anchor = _find_qualifying_anchor(def_el)
    assert anchor is None
