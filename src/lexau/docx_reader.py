from __future__ import annotations

from collections.abc import Iterator
from dataclasses import replace

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

from lexau.parser import (
    ElementType,
    InlineSpan,
    ParsedParagraph,
    classify_legacy_stream,
    is_legacy_document,
    parse_paragraph,
)


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


def _all_bold(spans: list[InlineSpan]) -> bool:
    """True iff every span with non-whitespace text is bold."""
    non_ws = [s for s in spans if s.text.strip()]
    return bool(non_ws) and all(s.bold for s in non_ws)


def iter_paragraphs(doc: Document) -> Iterator[ParsedParagraph]:
    """Yield ParsedParagraph for each Paragraph and Table in document order.

    Uses doc.iter_inner_content() (python-docx 1.2.0) to preserve document order.
    Tables are yielded as ParsedParagraph(TABLE, table_rows=[[cell, ...], ...]).
    cell.text concatenates all paragraph text in the cell; nested tables are flattened.
    FIGURE paragraphs (inline image) yield with empty spans.
    All other paragraphs populate spans from paragraph.runs.

    Acts whose DOCX has no ActHead*-styled paragraph anywhere ("legacy"
    documents, ~550 of 2,944 in the corpus) route through
    classify_legacy_stream instead of parse_paragraph, since legacy Acts
    have no reliable style signal and must be classified from paragraph
    text and bold-run shape instead.
    """
    blocks = list(doc.iter_inner_content())

    para_blocks: list[Paragraph] = [
        b for b in blocks if isinstance(b, Paragraph) and not _has_inline_image(b)
    ]
    styles = [b.style.name if b.style else "Default" for b in para_blocks]
    legacy = is_legacy_document(styles)

    para_spans: list[list[InlineSpan]] = []
    para_texts: list[str] = []
    for block in para_blocks:
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
        para_spans.append(spans)
        para_texts.append("".join(s.text for s in spans))

    if legacy:
        stream_input = [
            (text, _all_bold(spans), style)
            for text, spans, style in zip(para_texts, para_spans, styles)
        ]
        legacy_results = classify_legacy_stream(stream_input)
    else:
        legacy_results = None

    para_pos = 0
    for block in blocks:
        if isinstance(block, Paragraph):
            if _has_inline_image(block):
                yield ParsedParagraph(ElementType.FIGURE, text=block.text)
                continue
            style = styles[para_pos]
            full_text = para_texts[para_pos]
            spans = para_spans[para_pos]
            level = _list_level(block)

            if legacy:
                parsed_list = legacy_results[para_pos]
            else:
                parsed_list = [parse_paragraph(style, full_text)]

            for parsed in parsed_list:
                if level is not None and parsed.element_type == ElementType.BODY:
                    parsed = replace(parsed, element_type=ElementType.LIST_ITEM, number=str(level), spans=spans)
                else:
                    parsed = replace(parsed, spans=spans)
                yield parsed

            para_pos += 1
        elif isinstance(block, Table):
            rows = [
                [cell.text.strip() for cell in row.cells]
                for row in block.rows
            ]
            yield ParsedParagraph(element_type=ElementType.TABLE, table_rows=rows)
