from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class ElementType(Enum):
    CHAPTER     = "chapter"
    PART        = "part"
    DIVISION    = "dvs"
    SUBDIVISION = "subdvs"
    SECTION     = "section"
    SUBSECTION  = "subsec"
    PARAGRAPH   = "para"
    SUBPARAGRAPH = "subpara"
    BODY        = "body"
    SKIP        = "skip"


_PREFIX_TO_ELEMENT = {
    "Chapter":     ElementType.CHAPTER,
    "Part":        ElementType.PART,
    "Division":    ElementType.DIVISION,
    "Subdivision": ElementType.SUBDIVISION,
}

# Matches "Part\xa01—Heading", "Division\xa01" (no heading), etc.
_HEADING_RE = re.compile(
    r'^(Chapter|Part|Division|Subdivision)\xa0([^—]+?)(?:—(.*))?$'
)

# Matches "4  Short title", "2A  Objects of this Act"
_SECTION_RE = re.compile(r'^(\w[\w.\-]*)[ \t]{2,}(.+)$')

# Matches "(1) text", "(2A) text" — subsection pattern
_SUBSEC_RE = re.compile(r'^\((\d+[A-Z]?)\)\s+(.*)', re.DOTALL)

# Matches "(a) text", "(b) text" — lowercase letter pattern
_PARA_RE = re.compile(r'^\(([a-z]+)\)\s+(.*)', re.DOTALL)

# Matches "(i) text", "(ii) text", "(iii) text" — roman numeral pattern
_SUBPARA_RE = re.compile(r'^\(([ivxlcdm]+)\)\s+(.*)', re.DOTALL)


@dataclass
class ParsedParagraph:
    element_type: ElementType
    number: str = ""
    heading: str = ""
    text: str = ""
    raw_style: str = ""
    table_rows: list[list[str]] = field(default_factory=list)


def parse_paragraph(style: str, text: str) -> ParsedParagraph:
    stripped = text.strip()

    if not stripped:
        return ParsedParagraph(ElementType.SKIP, raw_style=style)

    if style.startswith("ActHead"):
        # Try prefix-based heading match first (determines element type from text)
        m = _HEADING_RE.match(stripped)
        if m:
            prefix, number, heading = m.group(1), m.group(2).strip(), (m.group(3) or "").strip()
            etype = _PREFIX_TO_ELEMENT[prefix]
            return ParsedParagraph(etype, number=number, heading=heading, raw_style=style)

        # ActHead 5 (sections): "4  Short title"
        m = _SECTION_RE.match(stripped)
        if m:
            return ParsedParagraph(
                ElementType.SECTION,
                number=m.group(1),
                heading=m.group(2).strip(),
                raw_style=style,
            )

    # Body Text and List Paragraph styles: check for subsection/paragraph/subparagraph patterns
    if style == "Body Text":
        m = _SUBSEC_RE.match(stripped)
        if m:
            return ParsedParagraph(
                ElementType.SUBSECTION,
                number=m.group(1),
                text=m.group(2).strip(),
                raw_style=style,
            )
        # No subsection pattern found; fall through to body text

    elif style == "List Paragraph":
        # Try subparagraph (roman numeral) first to avoid matching (ii) as (a-z)+
        m = _SUBPARA_RE.match(stripped)
        if m:
            return ParsedParagraph(
                ElementType.SUBPARAGRAPH,
                number=m.group(1),
                text=m.group(2).strip(),
                raw_style=style,
            )
        # Try paragraph (lowercase letter)
        m = _PARA_RE.match(stripped)
        if m:
            return ParsedParagraph(
                ElementType.PARAGRAPH,
                number=m.group(1),
                text=m.group(2).strip(),
                raw_style=style,
            )
        # No pattern found; fall through to body text

    else:
        # Fallback for unknown styles: try subsection, then paragraph
        m = _SUBSEC_RE.match(stripped)
        if m:
            return ParsedParagraph(
                ElementType.SUBSECTION,
                number=m.group(1),
                text=m.group(2).strip(),
                raw_style=style,
            )
        m = _PARA_RE.match(stripped)
        if m:
            return ParsedParagraph(
                ElementType.PARAGRAPH,
                number=m.group(1),
                text=m.group(2).strip(),
                raw_style=style,
            )

    # Everything else is body text
    return ParsedParagraph(ElementType.BODY, text=stripped, raw_style=style)
