import pytest
from lexau.parser import parse_paragraph, ElementType


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
