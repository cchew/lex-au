from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from lexau.parser import ElementType, InlineSpan, ParsedParagraph, parse_paragraph


def _has_inline_image(para: Paragraph) -> bool:
    """Return True if the paragraph contains at least one DrawingML inline image."""
    return bool(para._element.findall(f".//{qn('a:blip')}"))


def _list_level(para: Paragraph) -> int | None:
    """Return 0-based list level if paragraph is a list item, else None."""
    pPr = para._element.pPr
    if pPr is None:
        return None
    numPr = pPr.numPr
    if numPr is None:
        return None
    ilvl = numPr.ilvl
    return int(ilvl.val) if ilvl is not None else 0


def iter_paragraphs(doc: Document) -> Iterator[ParsedParagraph]:
    """Yield ParsedParagraph for each Paragraph and Table in document order.

    Uses doc.iter_inner_content() (python-docx 1.2.0) to preserve document order.
    Tables are yielded as ParsedParagraph(TABLE, table_rows=[[cell, ...], ...]).
    cell.text concatenates all paragraph text in the cell; nested tables are flattened.
    FIGURE paragraphs (inline image) yield with empty spans.
    All other paragraphs populate spans from paragraph.runs.
    """
    for block in doc.iter_inner_content():
        if isinstance(block, Paragraph):
            if _has_inline_image(block):
                yield ParsedParagraph(ElementType.FIGURE, text=block.text)
                continue
            style = block.style.name if block.style else "Default"
            spans = [
                InlineSpan(
                    text=run.text,
                    bold=bool(run.bold),
                    italic=bool(run.italic),
                    superscript=bool(run.font.superscript),
                    subscript=bool(run.font.subscript),
                )
                for run in block.runs
                if run.text
            ]
            full_text = "".join(s.text for s in spans)
            parsed = parse_paragraph(style, full_text)
            level = _list_level(block)
            if level is not None and parsed.element_type == ElementType.BODY:
                parsed = replace(parsed, element_type=ElementType.LIST_ITEM, number=str(level), spans=spans)
            else:
                parsed = replace(parsed, spans=spans)
            yield parsed
        elif isinstance(block, Table):
            rows = [
                [cell.text.strip() for cell in row.cells]
                for row in block.rows
            ]
            yield ParsedParagraph(element_type=ElementType.TABLE, table_rows=rows)
