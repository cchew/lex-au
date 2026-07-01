import pytest
from lexau.parser import parse_paragraph, ElementType, InlineSpan, ParsedParagraph


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
