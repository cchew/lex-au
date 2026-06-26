import pytest
from docx import Document
from docx.oxml import parse_xml
from lexau.docx_reader import iter_paragraphs
from lexau.parser import ElementType


def test_paragraph_passthrough():
    doc = Document()
    doc.add_paragraph("Hello world")
    results = list(iter_paragraphs(doc))
    texts = [p.text for p in results if p.text.strip()]
    assert "Hello world" in texts


def test_table_extracted_as_table_type():
    doc = Document()
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "H1"
    table.cell(0, 1).text = "H2"
    table.cell(1, 0).text = "D1"
    table.cell(1, 1).text = "D2"
    results = list(iter_paragraphs(doc))
    table_blocks = [p for p in results if p.element_type == ElementType.TABLE]
    assert len(table_blocks) == 1
    assert table_blocks[0].table_rows == [["H1", "H2"], ["D1", "D2"]]


def test_document_order_preserved():
    doc = Document()
    doc.add_paragraph("Before")
    t = doc.add_table(rows=1, cols=1)
    t.cell(0, 0).text = "Cell"
    doc.add_paragraph("After")
    results = list(iter_paragraphs(doc))
    meaningful = [p for p in results if p.text.strip() or p.element_type == ElementType.TABLE]
    table_idx = next(i for i, p in enumerate(meaningful) if p.element_type == ElementType.TABLE)
    assert meaningful[table_idx - 1].text.strip() == "Before"
    assert meaningful[table_idx + 1].text.strip() == "After"


def test_empty_paragraph_yields_skip():
    doc = Document()
    doc.add_paragraph("")
    results = list(iter_paragraphs(doc))
    skip_results = [p for p in results if p.element_type == ElementType.SKIP]
    assert len(skip_results) >= 1


def test_list_level_detection():
    """A DOCX paragraph with numPr at ilvl=0 yields LIST_ITEM with number='0'."""
    doc = Document()
    p = doc.add_paragraph("Plain list item text")
    # Inject numPr to mark paragraph as a list item at level 0
    pPr_xml = (
        '<w:pPr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:numPr>'
        '<w:ilvl w:val="0"/>'
        '<w:numId w:val="1"/>'
        '</w:numPr>'
        '</w:pPr>'
    )
    p._element.insert(0, parse_xml(pPr_xml))

    results = list(iter_paragraphs(doc))
    list_items = [r for r in results if r.element_type == ElementType.LIST_ITEM]
    assert len(list_items) == 1
    assert list_items[0].number == "0"
    assert list_items[0].text == "Plain list item text"


def test_list_level_detection_nested():
    """A list paragraph at ilvl=1 yields LIST_ITEM with number='1'."""
    doc = Document()
    p = doc.add_paragraph("Nested list item")
    pPr_xml = (
        '<w:pPr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:numPr>'
        '<w:ilvl w:val="1"/>'
        '<w:numId w:val="1"/>'
        '</w:numPr>'
        '</w:pPr>'
    )
    p._element.insert(0, parse_xml(pPr_xml))

    results = list(iter_paragraphs(doc))
    list_items = [r for r in results if r.element_type == ElementType.LIST_ITEM]
    assert len(list_items) == 1
    assert list_items[0].number == "1"
