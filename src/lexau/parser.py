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


@dataclass
class ParsedParagraph:
    element_type: ElementType
    number: str = ""
    heading: str = ""
    text: str = ""
    raw_style: str = ""


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

    # Everything else is body text
    return ParsedParagraph(ElementType.BODY, text=stripped, raw_style=style)
