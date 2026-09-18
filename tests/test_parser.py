import pytest
from lexau.parser import parse_paragraph, ElementType, InlineSpan, ParsedParagraph
from lexau.parser import is_legacy_document, parse_paragraph_legacy
from lexau.parser import classify_legacy_stream


def test_parse_part_with_roman_number():
    p = parse_paragraph("ActHead 2", "Part\xa0I—Preliminary")
    assert p.element_type == ElementType.PART
    assert p.number == "I"
    assert p.heading == "Preliminary"


def test_parse_part_with_decimal_number():
    p = parse_paragraph("ActHead 2", "Part\xa01-1—Introduction")
    assert p.element_type == ElementType.PART
    assert p.number == "1-1"
    assert p.heading == "Introduction"


def test_parse_division():
    p = parse_paragraph("ActHead 3", "Division\xa01—Preliminary")
    assert p.element_type == ElementType.DIVISION
    assert p.number == "1"
    assert p.heading == "Preliminary"


def test_parse_division_no_heading():
    # Criminal Code pattern: ActHead 4 with "Division 1" (no em dash)
    p = parse_paragraph("ActHead 4", "Division\xa01")
    assert p.element_type == ElementType.DIVISION
    assert p.number == "1"
    assert p.heading == ""


def test_parse_chapter():
    p = parse_paragraph("ActHead 1", "Chapter\xa01—Introduction")
    assert p.element_type == ElementType.CHAPTER
    assert p.number == "1"
    assert p.heading == "Introduction"


def test_parse_section_simple():
    p = parse_paragraph("ActHead 5", "1  Short title")
    assert p.element_type == ElementType.SECTION
    assert p.number == "1"
    assert p.heading == "Short title"


def test_parse_section_alphanumeric():
    p = parse_paragraph("ActHead 5", "2A  Objects of this Act")
    assert p.element_type == ElementType.SECTION
    assert p.number == "2A"
    assert p.heading == "Objects of this Act"


def test_parse_body_text():
    p = parse_paragraph("Body Text", "For the purposes of this Act...")
    assert p.element_type == ElementType.BODY
    assert p.text == "For the purposes of this Act..."


def test_parse_empty_paragraph_is_skip():
    p = parse_paragraph("Body Text", "   ")
    assert p.element_type == ElementType.SKIP


def test_parse_unknown_style_is_body():
    p = parse_paragraph("Normal", "Some text.")
    assert p.element_type == ElementType.BODY


def test_subsection_body_text_style():
    p = parse_paragraph("Body Text", "(1) The applicant must notify the entity.")
    assert p.element_type == ElementType.SUBSECTION
    assert p.number == "1"
    assert p.text == "The applicant must notify the entity."


def test_subsection_alphanumeric():
    p = parse_paragraph("Body Text", "(2A) Despite subsection (2), the entity may...")
    assert p.element_type == ElementType.SUBSECTION
    assert p.number == "2A"
    assert "Despite" in p.text


def test_paragraph_list_paragraph_style():
    p = parse_paragraph("List Paragraph", "(a) the person has suffered serious harm; or")
    assert p.element_type == ElementType.PARAGRAPH
    assert p.number == "a"
    assert "suffered" in p.text


def test_subparagraph_list_paragraph_style():
    p = parse_paragraph("List Paragraph", "(ii) the relevant information is sensitive.")
    assert p.element_type == ElementType.SUBPARAGRAPH
    assert p.number == "ii"
    assert "sensitive" in p.text


def test_style_fallback_subsection_no_style():
    p = parse_paragraph("Unknown", "(3) The notice must be given within 30 days.")
    assert p.element_type == ElementType.SUBSECTION
    assert p.number == "3"


def test_style_fallback_paragraph_no_style():
    p = parse_paragraph("Unknown", "(b) in relation to the matter...")
    assert p.element_type == ElementType.PARAGRAPH
    assert p.number == "b"


def test_body_text_without_leading_paren_remains_body():
    p = parse_paragraph("Body Text", "For the purposes of this Act...")
    assert p.element_type == ElementType.BODY


def test_parse_note_by_style():
    p = parse_paragraph("Note", "Note: See also section 6.")
    assert p.element_type == ElementType.NOTE
    assert p.text == "Note: See also section 6."
    assert p.number == ""


def test_parse_note_by_text_pattern():
    p = parse_paragraph("Body Text", "Note: The Commissioner may...")
    assert p.element_type == ElementType.NOTE


def test_parse_notes_plural_by_text_pattern():
    p = parse_paragraph("Body Text", "Notes: See sections 6 and 7.")
    assert p.element_type == ElementType.NOTE


def test_parse_example_by_style():
    p = parse_paragraph("Example", "Example: A person who transfers data...")
    assert p.element_type == ElementType.EXAMPLE
    assert p.text == "Example: A person who transfers data..."


def test_parse_example_by_text_pattern():
    p = parse_paragraph("Body Text", "Example: If an entity...")
    assert p.element_type == ElementType.EXAMPLE


def test_parse_examples_plural_by_text_pattern():
    p = parse_paragraph("Body Text", "Examples: 1. An APP entity...")
    assert p.element_type == ElementType.EXAMPLE


def test_parse_penalty_by_style():
    p = parse_paragraph("Penalty", "Penalty: 60 penalty units.")
    assert p.element_type == ElementType.PENALTY
    assert p.text == "Penalty: 60 penalty units."


def test_parse_penalty_by_text_pattern():
    p = parse_paragraph("Body Text", "Penalty: 120 penalty units.")
    assert p.element_type == ElementType.PENALTY


def test_parse_level4_uppercase_alpha():
    p = parse_paragraph("List Paragraph", "(A) the entity must comply with...")
    assert p.element_type == ElementType.LEVEL4
    assert p.number == "A"
    assert "entity" in p.text


def test_parse_level4_not_triggered_for_body_text():
    # (A) in Body Text style is NOT level4 — Body Text uses subsec/para detection only
    p = parse_paragraph("Body Text", "(A) some text")
    assert p.element_type != ElementType.LEVEL4


def test_parse_level4_not_triggered_for_unknown_style_lowercase():
    # (a) in unknown style should be PARAGRAPH, not LEVEL4
    p = parse_paragraph("Unknown", "(a) some text")
    assert p.element_type == ElementType.PARAGRAPH


def test_inline_span_defaults():
    span = InlineSpan(text="hello")
    assert span.bold is False
    assert span.italic is False
    assert span.superscript is False
    assert span.subscript is False


def test_parsed_paragraph_spans_default_empty():
    p = ParsedParagraph(ElementType.BODY, text="hello")
    assert p.spans == []


def test_parsed_paragraph_spans_field():
    spans = [InlineSpan(text="hello", italic=True), InlineSpan(text=" world")]
    p = ParsedParagraph(ElementType.BODY, text="hello world", spans=spans)
    assert len(p.spans) == 2
    assert p.spans[0].italic is True
    assert p.spans[1].italic is False


def test_is_legacy_document_true_when_no_acthead_style():
    assert is_legacy_document(["Normal", "Body Text2", "Body text (3)"]) is True


def test_is_legacy_document_false_when_any_acthead_style():
    assert is_legacy_document(["Normal", "ActHead 5", "Body Text"]) is False


def test_is_legacy_document_true_for_empty_list():
    assert is_legacy_document([]) is True


def test_legacy_part_heading_no_style_gate():
    # Same pattern as ActHead-styled Parts, but reached without a style check
    result = parse_paragraph_legacy("Part\xa01—Preliminary")
    assert len(result) == 1
    assert result[0].element_type == ElementType.PART
    assert result[0].number == "1"
    assert result[0].heading == "Preliminary"


def test_legacy_part_heading_uppercase_plain_space():
    # Mirrors a.c.t.-supreme-court-1992's real DOCX text: uppercase prefix,
    # plain ASCII space (0x20) instead of \xa0 — confirmed by byte
    # inspection, not the \xa0 the plan originally assumed for this path.
    result = parse_paragraph_legacy("PART 1—PRELIMINARY")
    assert len(result) == 1
    assert result[0].element_type == ElementType.PART
    assert result[0].number == "1"
    assert result[0].heading == "PRELIMINARY"


def test_legacy_standalone_subsection_continuation():
    # Mirrors albury-wodonga-1982: the subsection AFTER the first fused one
    # in a section has no section-number prefix at all — just "(N) text".
    result = parse_paragraph_legacy("(2) The Principal Act is in this Act referred to as the Principal Act.")
    assert len(result) == 1
    assert result[0].element_type == ElementType.SUBSECTION
    assert result[0].number == "2"
    assert result[0].text == "The Principal Act is in this Act referred to as the Principal Act."


def test_legacy_fused_section_subsection():
    # Confirmed shape 2: "1. (1) This Act may be cited..." — no separate heading paragraph
    result = parse_paragraph_legacy("1. (1) This Act may be cited as the Test Act 1982.")
    assert len(result) == 2
    assert result[0].element_type == ElementType.SECTION
    assert result[0].number == "1"
    assert result[0].heading == ""
    assert result[1].element_type == ElementType.SUBSECTION
    assert result[1].number == "1"
    assert result[1].text == "This Act may be cited as the Test Act 1982."


def test_legacy_fused_section_subsection_alnum_number():
    result = parse_paragraph_legacy("2A. (1) Objects of this Act.")
    assert result[1].number == "1"
    assert result[0].number == "2A"


def test_legacy_plain_body_falls_through():
    result = parse_paragraph_legacy("This is ordinary continuing body text.")
    assert len(result) == 1
    assert result[0].element_type == ElementType.BODY
    assert result[0].text == "This is ordinary continuing body text."


def test_legacy_empty_paragraph_is_skip():
    result = parse_paragraph_legacy("   ")
    assert result == [ParsedParagraph(ElementType.SKIP)]


def test_legacy_penalty_text_still_detected():
    # Style-agnostic annotation detection must still work in the legacy path
    result = parse_paragraph_legacy("Penalty: 60 penalty units.")
    assert result[0].element_type == ElementType.PENALTY


def test_classify_legacy_stream_shape1_heading_plus_numbered_body():
    # Mirrors the loan-act-1976 fixture: bold heading paragraph, then a
    # tab-separated numbered paragraph with no separate subsection.
    stream = [
        ("Short title.", True, ""),
        ("1.\tThis Act may be cited as the Loan Act (No. 2) 1976.", False, ""),
        ("Commencement.", True, ""),
        ("2.\tThis Act shall come into operation on the day of Royal Assent.", False, ""),
    ]
    results = classify_legacy_stream(stream)
    assert len(results) == 4
    assert results[0] == []  # heading donor consumed
    assert results[1][0].element_type == ElementType.SECTION
    assert results[1][0].number == "1"
    assert results[1][0].heading == "Short title."
    assert results[1][1].element_type == ElementType.BODY
    assert results[1][1].text == "This Act may be cited as the Loan Act (No. 2) 1976."
    assert results[2] == []
    assert results[3][0].heading == "Commencement."


def test_classify_legacy_stream_ignores_non_bold_candidate():
    # A plain (non-bold) sentence immediately before a numbered paragraph
    # must NOT be swallowed as a heading — only fully-bold paragraphs qualify.
    stream = [
        ("This concludes the previous section's body text.", False, ""),
        ("3.\tShort title for this new section.", False, ""),
    ]
    results = classify_legacy_stream(stream)
    assert results[0][0].element_type == ElementType.BODY
    assert results[1][0].element_type == ElementType.BODY  # no digit-prefixed structural match; stays BODY


def test_classify_legacy_stream_bold_heading_not_consumed_without_numbered_follower():
    # A bold paragraph not followed by a numbered paragraph is left as-is
    # (falls through to parse_paragraph_legacy, i.e. plain BODY here).
    stream = [("Some Bold Standalone Text", True, "")]
    results = classify_legacy_stream(stream)
    assert results[0][0].element_type == ElementType.BODY


def test_classify_legacy_stream_defers_structural_and_fused_to_parse_paragraph_legacy():
    # A bold Part heading must classify as PART, not be consumed as a
    # shape-1 donor, even if immediately followed by a numbered paragraph.
    stream = [
        ("Part\xa01—Preliminary", True, ""),
        ("1.\tShort title.", False, ""),
    ]
    results = classify_legacy_stream(stream)
    assert results[0][0].element_type == ElementType.PART
    assert results[1][0].element_type == ElementType.BODY  # "1.\tShort title." has no further body para in this stream; matches _LEGACY_NUMBERED_RE fallback as plain text here is fine since it's exercised in isolation


def test_classify_legacy_stream_bold_heading_before_fused_defers_to_fused_shape():
    # Mirrors the albury-wodonga-1982 fixture: a bold heading paragraph
    # ("Short title, &c.") immediately precedes a fused section+subsection
    # paragraph ("1. (1) ..."). _LEGACY_NUMBERED_RE would also match the
    # fused text, so without the next-paragraph fused-shape exclusion the
    # heading would be wrongly consumed as a shape-1 donor, collapsing the
    # SUBSECTION structure into plain BODY text.
    stream = [
        ("Short title, &c.", True, ""),
        ("1. (1) This Act may be cited as the Test Act 1982.", False, ""),
        ("(2) The Principal Act is in this Act referred to as the Principal Act.", False, ""),
    ]
    results = classify_legacy_stream(stream)
    assert results[0][0].element_type == ElementType.BODY  # heading NOT consumed
    assert results[0][0].text == "Short title, &c."
    assert results[1][0].element_type == ElementType.SECTION
    assert results[1][0].number == "1"
    assert results[1][1].element_type == ElementType.SUBSECTION
    assert results[1][1].number == "1"


def test_classify_legacy_stream_bold_title_before_act_citation_line_not_shape1():
    # Mirrors the loan-act-1976 fixture: the bold Act-title paragraph
    # ("LOAN ACT (No. 2) 1976") is immediately followed by the Act-citation
    # line ("No. 7 of 1976"), which is NOT a numbered clause. Before the
    # digit-only _LEGACY_NUMBERED_RE fix, "No" matched the old \w[\w.\-]*
    # number group, producing a spurious SECTION(number="No").
    stream = [
        ("LOAN ACT (No. 2) 1976", True, ""),
        ("No. 7 of 1976", False, ""),
    ]
    results = classify_legacy_stream(stream)
    assert results[0][0].element_type == ElementType.BODY  # title NOT consumed as heading donor
    assert results[1][0].element_type == ElementType.BODY  # citation line NOT parsed as SECTION


def test_classify_legacy_stream_uppercase_part_heading_not_consumed_as_shape1():
    # Mirrors a.c.t.-supreme-court-1992: an uppercase, plain-space Part
    # heading ("PART 1—PRELIMINARY") is bold in this fixture. The shared
    # _HEADING_RE (title-case, \xa0-only) would miss this and wrongly let the
    # shape-1 lookback consume it if it were immediately followed by a
    # numbered paragraph. _LEGACY_HEADING_RE (case-insensitive, tolerates a
    # plain space) must exclude it correctly.
    stream = [
        ("PART 1—PRELIMINARY", True, ""),
        ("1.\tShort title.", False, ""),
    ]
    results = classify_legacy_stream(stream)
    assert results[0][0].element_type == ElementType.PART
    assert results[0][0].number == "1"


def test_classify_legacy_stream_shape4_fused_heading_non_bold():
    # Shape 4 (fused "<n> Heading", no period): matches regardless of
    # boldness, gated on the enacting-formula + sequential-number check
    # instead -- mirrors education-and-training-legislation-amendment-
    # act-1996's own "1 Short title", which is plain unbolded text (unlike
    # its bold siblings "2 Commencement" / "3 Schedule(s)").
    stream = [
        ("The Parliament of Australia enacts:", False, ""),
        ("1 Short title", False, ""),
        ("This Act may be cited as the Test Act 1996.", False, ""),
        ("2 Commencement", True, ""),
        ("This Act commences on Royal Assent.", False, ""),
    ]
    results = classify_legacy_stream(stream)
    assert results[1][0].element_type == ElementType.SECTION
    assert results[1][0].number == "1"
    assert results[1][0].heading == "Short title"
    assert results[3][0].element_type == ElementType.SECTION
    assert results[3][0].number == "2"


def test_classify_legacy_stream_rejects_toc_preview_before_enacting_formula():
    # Reproduces australian-trade-commission-(transitional-provisions-and-
    # consequential-amendments)-act-1985's Table of Provisions: a TOC entry
    # can look exactly like a genuine shape-1 donor+candidate pair -- a
    # short, non-operative-looking donor immediately followed by a
    # "1.\ttext"-shaped candidate -- and, being the TOC's first listed
    # section, trivially satisfies the sequential check too. It appears
    # BEFORE the Act's enacting formula, where nothing is ever real
    # operative text; the REAL "Short title." / "1.\ttext" pair appears
    # again, correctly, after the formula.
    stream = [
        ("Section", False, ""),
        ("1.\tShort title", False, ""),
        ("The Parliament of Australia enacts:", False, ""),
        ("Short title", False, ""),
        ("1. This Act may be cited as the Test Act 1985.", False, ""),
    ]
    results = classify_legacy_stream(stream)
    assert results[0][0].element_type == ElementType.BODY  # TOC "Section" not consumed
    assert results[1][0].element_type == ElementType.BODY  # TOC entry not promoted to SECTION
    assert results[3] == []  # real donor consumed
    assert results[4][0].element_type == ElementType.SECTION
    assert results[4][0].number == "1"
    assert results[4][0].heading == "Short title"


def test_classify_legacy_stream_rejects_quoted_section_from_target_act():
    # Reproduces veterans'-affairs-legislation-amendment-act-(no.-1)-1996:
    # a Schedule item can itself be a bold "<n> Heading"-shaped line
    # QUOTING a section being inserted into the *target* Act being amended
    # ("3 After section 4C" / "Insert:" / "4D Exclusion..." -- "4D" belongs
    # to the target Act, not this one). Once this Act's own Schedule
    # boundary is detected ("3 Schedule(s)" plus its boilerplate body
    # text), neither new candidacy path may fire again, so the
    # coincidentally-sequential "4D" (continuing from this Act's own last
    # real section, "3") is correctly rejected.
    stream = [
        ("The Parliament of Australia enacts:", False, ""),
        ("1 Short title", True, ""),
        ("This Act may be cited as the Test Amendment Act 1996.", False, ""),
        ("2 Commencement", True, ""),
        ("This Act commences on Royal Assent.", False, ""),
        ("3 Schedule(s)", True, ""),
        (
            "Each Act that is specified in a Schedule to this Act is amended "
            "or repealed as set out in the applicable items in the Schedule "
            "concerned.",
            False,
            "",
        ),
        ("Schedule 1—Amendment of the Test Principal Act 1990", True, ""),
        ("3 After section 4C", True, ""),
        ("Insert:", False, ""),
        ("4D Exclusion of test provisions", True, ""),
        ("(1) This is the inserted section's own text.", False, ""),
    ]
    results = classify_legacy_stream(stream)
    numbers = [r.number for rl in results for r in rl if r.element_type == ElementType.SECTION]
    assert numbers == ["1", "2", "3"]
    assert "4D" not in numbers


def test_classify_legacy_stream_rejects_amendment_instruction_heading():
    # A "<n> Heading"-shaped line whose heading text is itself an
    # amendment instruction (Omit/Insert/Repeal/Substitute/Add/Renumber)
    # is never a genuine section heading, even when sequential and past
    # the enacting formula -- catches Schedule items in Acts whose own
    # Schedule-announcing section is titled something none of the other
    # Schedule-boundary triggers recognise (e.g. "Amendments").
    stream = [
        ("The Parliament of Australia enacts:", False, ""),
        ("1 Short title", True, ""),
        ("This Act may be cited as the Test Act 1995.", False, ""),
        ("2 Commencement", True, ""),
        ("This Act commences on Royal Assent.", False, ""),
        ('3 Omit "the", substitute "a".', True, ""),
        ("Some schedule item body text.", False, ""),
    ]
    results = classify_legacy_stream(stream)
    numbers = [r.number for rl in results for r in rl if r.element_type == ElementType.SECTION]
    assert numbers == ["1", "2"]


def test_classify_legacy_stream_fallback_capped_at_max_section():
    # Hard numeric backstop: a pathological stream with no recognisable
    # Schedule boundary but a sequential-looking "<n> Heading" run well
    # beyond anything a real Act in this corpus needs before its Schedules
    # begin must still stop -- both new candidacy paths shut off once
    # last_section_num reaches the cap, regardless of the schedule gate's
    # state.
    stream = [("The Parliament of Australia enacts:", False, "")]
    for n in range(1, 20):
        stream.append((f"{n} Heading {n}", True, ""))
        stream.append((f"Body text for section {n}.", False, ""))
    results = classify_legacy_stream(stream)
    numbers = [int(r.number) for rl in results for r in rl if r.element_type == ElementType.SECTION]
    assert numbers  # the cap doesn't suppress everything
    assert max(numbers) <= 12  # _LEGACY_FALLBACK_MAX_SECTION
    assert len(numbers) <= 12


def test_classify_legacy_stream_bold_donor_matching_numbered_shape_not_swallowed():
    # A bold "N.\ttext" line -- itself a genuine numbered candidate, not a
    # marginal-note donor -- must not be silently consumed as ANOTHER
    # section's heading merely because the whole line happens to be bold.
    # Pre-Task-12, the bold-donor path only excluded _LEGACY_HEADING_RE /
    # _LEGACY_FUSED_RE matches on the donor; a fully-bold "1. This Act may
    # be cited..." line would have been wrongly swallowed as the heading
    # donor for section 2's "2.\ttext" candidate, discarding section 1's
    # own text into a nonsensical heading for section 2. donor_is_operative
    # now also excludes _LEGACY_NUMBERED_RE matches on the donor,
    # regardless of boldness, so this text is correctly left alone instead
    # of vanishing into section 2's heading.
    stream = [
        ("1. This Act may be cited as the Test Act 1999.", True, ""),
        ("2.\tCommencement provisions apply.", False, ""),
    ]
    results = classify_legacy_stream(stream)
    assert results[1][0].heading != "1. This Act may be cited as the Test Act 1999."


def test_classify_legacy_stream_bold_marginal_note_starting_with_digits_not_excluded():
    # Regression: reproduces veterans'-entitlements-(rewrite)-transition-
    # act-1991's real "1990 Budget amendments" donor -- a genuine bold
    # marginal note that happens to start with a 4-digit year followed by
    # capitalised text, immediately preceding "19.\tThe Principal Act is
    # further amended...". An earlier version of this fix's donor_is_
    # operative also excluded any donor matching the shape-4 "<digits>
    # Capitalised text" shape (to stop a REJECTED shape-4 candidate being
    # reused as an unrelated donor) -- too broad: a plain-prose marginal
    # note that happens to open with digits satisfies that shape purely by
    # coincidence, and got wrongly excluded, discarding section 19's real
    # heading. donor_is_operative must not reject a donor merely for
    # matching shape-4's text pattern; only for looking like an already-
    # operative numbered clause (_LEGACY_NUMBERED_RE / _SUBSEC_RE).
    stream = [
        ("18.\tThe Principal Act is amended as set out in Schedule 1.", False, "Normal"),
        (
            "PART 4—1990 BUDGET AMENDMENTS OF THE VETERANS’ ENTITLEMENTS ACT 1986",
            True,
            "Normal",
        ),
        ("1990 Budget amendments", True, "Normal"),
        (
            "19.\tThe Principal Act is further amended as set out in Schedule 2.",
            False,
            "Normal",
        ),
    ]
    results = classify_legacy_stream(stream)
    assert results[2] == []  # donor consumed
    assert results[3][0].element_type == ElementType.SECTION
    assert results[3][0].number == "19"
    assert results[3][0].heading == "1990 Budget amendments"


def test_legacy_style_heading5_short_title():
    # Shape 3: style-driven section heading. Confirmed against
    # agricultural-and-veterinary-chemical-products-levy-imposition-
    # (customs)-act-1994's real DOCX: "1  Short title" styled "Heading 5",
    # no separate bold-heading paragraph, no fused "N. (M)" pattern.
    result = parse_paragraph_legacy("1  Short title", style="Heading 5")
    assert len(result) == 1
    assert result[0].element_type == ElementType.SECTION
    assert result[0].number == "1"
    assert result[0].heading == "Short title"


def test_legacy_style_heading5_alnum_section_number():
    # Confirmed against us-free-trade-agreement-implementation-act-2004:
    # "153Y  Simplified outline" styled Heading 5, deep in a Division.
    result = parse_paragraph_legacy("153Y  Simplified outline", style="Heading 5")
    assert result[0].number == "153Y"
    assert result[0].heading == "Simplified outline"


def test_legacy_style_heading5_rtf_alias_suffix():
    # RTF-sourced Acts (australian-national-railways-commission-sale-act-1997,
    # corporate-law-economic-reform-program-act-1999) serialize the same
    # conceptual style as "heading 5,s" (lowercase, comma-appended alias)
    # rather than OLE2 LibreOffice's "Heading 5". Must match identically.
    result = parse_paragraph_legacy("1  Short title", style="heading 5,s")
    assert len(result) == 1
    assert result[0].element_type == ElementType.SECTION
    assert result[0].number == "1"
    assert result[0].heading == "Short title"


def test_legacy_style_heading5_normalization_no_false_positive():
    # Normalization (before-first-comma, lowercased) must not cause an
    # unrelated style like "Heading 50" or "Normal" to match "Heading 5".
    result = parse_paragraph_legacy("1  Short title", style="heading 50")
    assert result[0].element_type == ElementType.BODY

    result = parse_paragraph_legacy("1  Short title", style="Normal")
    assert result[0].element_type == ElementType.BODY


def test_legacy_style_heading5_requires_section_re_shape():
    # A Heading-5-styled paragraph that doesn't match "N<2+ spaces>text"
    # (no number prefix) falls through to ordinary classification, same as
    # the non-legacy path's ActHead-gated _SECTION_RE behaves today.
    result = parse_paragraph_legacy("Preliminary", style="Heading 5")
    assert result[0].element_type == ElementType.BODY


def test_legacy_style_heading5_does_not_override_structural_heading():
    # Belt-and-braces: even if a Part/Division heading were ever styled
    # Heading 5, _LEGACY_HEADING_RE must still win (checked first) so a
    # genuine "Part 1—Preliminary" line is never misread as a SECTION.
    result = parse_paragraph_legacy("Part\xa01—Preliminary", style="Heading 5")
    assert result[0].element_type == ElementType.PART


def test_classify_legacy_stream_threads_style_for_heading5_shape():
    # End-to-end through classify_legacy_stream: Heading-5 section headings
    # interleaved with "subsection"-styled body/numbered-subsection text.
    stream = [
        ("1  Short title", False, "Heading 5"),
        ("This Act may be cited as the Test Act 1994.", False, "subsection"),
        ("2  Commencement", False, "Heading 5"),
        ("(1)\tThis section commences on Royal Assent.", False, "subsection"),
    ]
    results = classify_legacy_stream(stream)
    assert results[0][0].element_type == ElementType.SECTION
    assert results[0][0].number == "1"
    assert results[0][0].heading == "Short title"
    assert results[1][0].element_type == ElementType.BODY
    assert results[2][0].element_type == ElementType.SECTION
    assert results[2][0].number == "2"
    assert results[3][0].element_type == ElementType.SUBSECTION
    assert results[3][0].number == "1"
