from __future__ import annotations

from collections.abc import Iterator

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from lexau.parser import ElementType, ParsedParagraph, parse_paragraph


def iter_paragraphs(doc: Document) -> Iterator[ParsedParagraph]:
    """Yield ParsedParagraph for each Paragraph and Table in document order.

    Uses doc.iter_inner_content() (python-docx 1.2.0) to preserve document order.
    Tables are yielded as ParsedParagraph(TABLE, table_rows=[[cell, ...], ...]).
    cell.text concatenates all paragraph text in the cell; nested tables are flattened.
    """
    for block in doc.iter_inner_content():
        if isinstance(block, Paragraph):
            style = block.style.name if block.style else "Default"
            yield parse_paragraph(style, block.text)
        elif isinstance(block, Table):
            rows = [
                [cell.text.strip() for cell in row.cells]
                for row in block.rows
            ]
            yield ParsedParagraph(element_type=ElementType.TABLE, table_rows=rows)
