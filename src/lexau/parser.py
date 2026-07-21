from __future__ import annotations

import re
from collections.abc import Iterable
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
    NOTE        = "note"
    EXAMPLE     = "example"
    PENALTY     = "penalty"
    LEVEL4      = "level4"
    LIST_ITEM   = "list-item"
    TABLE       = "table"
    FIGURE      = "figure"
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

# Note: "Note:" or "Notes:" prefix — any style, or "Note" style
_NOTE_RE = re.compile(r'^Notes?[\xa0: ]', re.IGNORECASE)

# Example: "Example:" or "Examples:" prefix — any style, or "Example" style
_EXAMPLE_RE = re.compile(r'^Examples?[\xa0: ]', re.IGNORECASE)

# Penalty: "Penalty:" prefix — any style, or "Penalty" style
_PENALTY_RE = re.compile(r'^Penalty[\xa0: ]', re.IGNORECASE)

# Level4: uppercase alpha (A)(B)(C) in List Paragraph
_LEVEL4_RE = re.compile(r'^\(([A-Z]+)\)\s+(.*)', re.DOTALL)


def is_legacy_document(styles: Iterable[str]) -> bool:
    """True if no paragraph style in the document starts with 'ActHead'.

    Acts authored outside the modern Word template have no ActHead* styles
    anywhere; `parse_paragraph`'s style gate then leaves every paragraph
    unclassified, so `_split_stream` never finds a structural boundary and
    the whole Act ends up in <preface> with an empty <body>.
    """
    return not any(s.startswith("ActHead") for s in styles)


# Legacy shape 2: fused section+subsection, e.g. "1. (1) This Act may be cited as..."
# Section-number group is intentionally left loose (\w[\w.\-]*, unlike
# _LEGACY_NUMBERED_RE's tightened \d+[A-Z]*) — the trailing "(\d+[A-Z]?) "
# anchor requires an actual parenthesised subsection number immediately
# after, which ordinary prose or citation lines (e.g. "No. 7 of 1976") won't
# satisfy. That anchor is what _LEGACY_NUMBERED_RE lacks, which is why only
# the latter needed tightening against real corpus false positives.
_LEGACY_FUSED_RE = re.compile(r'^(\w[\w.\-]*)\.\s+\((\d+[A-Z]?)\)\s+(.+)$', re.DOTALL)

# Legacy-only heading match. Reuses _HEADING_RE's prefix/heading grouping but
# tolerates BOTH a plain space and \xa0 between the prefix and the number, and
# matches case-insensitively. The plan's original assumption — "reuses
# _HEADING_RE unchanged, the pattern was never the problem" — does not hold
# for real legacy corpus text: a.c.t.-supreme-court-(transfer)-act-1992 (the
# Task 5 style-less-heading fixture) has "PART 1—PRELIMINARY" using a plain
# ASCII space (0x20, confirmed by byte inspection) and all-uppercase "PART",
# neither of which the shared _HEADING_RE (used by the ActHead-styled,
# non-legacy path in parse_paragraph) matches. A separate constant is used —
# not a change to _HEADING_RE itself — so the non-legacy path's behavior for
# the 2,394 already-indexed Acts is completely unaffected.
_LEGACY_HEADING_RE = re.compile(
    r'^(Chapter|Part|Division|Subdivision)[\xa0 ]([^—]+?)(?:—(.*))?$', re.IGNORECASE
)
# Caveat inherited from the original _HEADING_RE design (not newly introduced
# here): the "number" group is unconstrained text, not digits-only, matching
# the whole rest of the paragraph when there's no em-dash. In the non-legacy
# path this is safe because _HEADING_RE only runs behind the ActHead style
# gate. In the legacy path there is no style gate at all, so a one-line body
# paragraph that happens to start with "part "/"chapter "/etc. (now also
# case-insensitively) could false-positive as a heading. Not observed in the
# three Task 5 fixtures; worth a spot-check against Task 6's full corpus
# rebuild if the empty-<section> residual is unexpectedly high afterward.


# Legacy shape 3: style-driven section heading. A "Heading 5"-styled
# paragraph carries the section number+heading on one line, in the same
# "N<2+ spaces>text" shape _SECTION_RE already recognises for the
# ActHead-styled non-legacy path (e.g. "1  Short title"). Confirmed
# against agricultural-and-veterinary-chemical-products-levy-imposition-
# (customs)-act-1994, northern-territory-(commonwealth-lands)-act-1980, and
# loan-(war-service-land-settlement)-act-1970 (real corpus fixtures,
# 2026-07-21 residual). Reuses _SECTION_RE rather than a new pattern since
# the text shape is identical to the non-legacy path's — only the trigger
# (style, not an ActHead* gate) differs. Confirmed safe across 20+
# multi-heading-level fixtures (e.g. anti-terrorism-act-(no.-2)-2004, where
# "Heading 6"/"Heading 9" carry Schedule/related-Act headings using \xa0 or
# em-dash separators that don't satisfy _SECTION_RE's 2-space-or-tab
# requirement, so they're untouched by this branch).
_LEGACY_SECTION_HEADING_STYLES = frozenset({"Heading 5"})


def parse_paragraph_legacy(text: str, style: str = "") -> list[ParsedParagraph]:
    """Style-agnostic classification for a single legacy-Act paragraph.

    Returns a list because the fused shape below yields two elements (a
    SECTION containing a SUBSECTION) from one DOCX paragraph.

    Handles Chapter/Part/Division/Subdivision headings (via the legacy-only
    _LEGACY_HEADING_RE), a style-driven section heading ("Heading 5" style
    + "N  Heading" text — shape 3), fused section+subsection
    ("1. (1) text"), and standalone continuation subsections ("(2) text"
    with no section-number prefix). Does NOT handle the separate-heading-
    plus-numbered-body shape (a bold heading paragraph followed by
    "1.\ttext") — that needs the preceding paragraph's bold-run info, so
    it's handled by classify_legacy_stream instead.
    """
    stripped = text.strip()
    if not stripped:
        return [ParsedParagraph(ElementType.SKIP)]

    m = _LEGACY_HEADING_RE.match(stripped)
    if m:
        prefix = m.group(1).capitalize()
        number, heading = m.group(2).strip(), (m.group(3) or "").strip()
        return [ParsedParagraph(_PREFIX_TO_ELEMENT[prefix], number=number, heading=heading)]

    if style in _LEGACY_SECTION_HEADING_STYLES:
        m = _SECTION_RE.match(stripped)
        if m:
            return [ParsedParagraph(ElementType.SECTION, number=m.group(1), heading=m.group(2).strip())]

    m = _LEGACY_FUSED_RE.match(stripped)
    if m:
        section_num, subsec_num, subsec_text = m.group(1), m.group(2), m.group(3)
        return [
            ParsedParagraph(ElementType.SECTION, number=section_num),
            ParsedParagraph(ElementType.SUBSECTION, number=subsec_num, text=subsec_text.strip()),
        ]

    m = _SUBSEC_RE.match(stripped)
    if m:
        return [ParsedParagraph(ElementType.SUBSECTION, number=m.group(1), text=m.group(2).strip())]

    annotation = _classify_annotation("", stripped)
    if annotation is not None:
        return [annotation]

    return [ParsedParagraph(ElementType.BODY, text=stripped)]


# Legacy shape 1's numbered paragraph, e.g. "1.\tThis Act may be cited as..."
# (single tab or space after the number+dot — not the 2+ whitespace _SECTION_RE requires)
# Number group is digits + optional uppercase-letter suffix (e.g. "26WA") — NOT
# \w[\w.\-]*, because that also matches "No" in an Act-citation line like
# "No. 7 of 1976" (real corpus text: the loan-act-(no.-2)-1976 fixture has this
# line immediately after the bold Act-title paragraph, producing a spurious
# extra SECTION before this fix — confirmed against the Task 5 fixture).
_LEGACY_NUMBERED_RE = re.compile(r'^(\d+[A-Z]*)\.[ \t]+(.+)$', re.DOTALL)


def classify_legacy_stream(paragraphs: list[tuple[str, bool, str]]) -> list[list[ParsedParagraph]]:
    """Classify a full legacy-Act paragraph stream, applying shape-1 lookback.

    `paragraphs` is (text, all_bold, style) per DOCX paragraph, in document
    order, where all_bold is True iff every non-whitespace run in that
    paragraph is bold, and style is the paragraph's DOCX style name (used
    for shape 3's Heading-5 detection; irrelevant to shapes 1/2 lookback).

    Returns one list of ParsedParagraph per input paragraph, aligned by
    index, so callers can still attach that paragraph's InlineSpans. A
    paragraph consumed as a shape-1 heading donor returns [] (its text
    becomes the following SECTION's heading instead of standalone BODY).

    A bold heading is NOT consumed as a shape-1 donor if the following
    paragraph is itself a fused section+subsection (shape 2, e.g.
    "1. (1) text") — that paragraph defers to parse_paragraph_legacy's
    fused handling instead, preserving the SUBSECTION structure that a
    shape-1 collapse would otherwise discard.
    """
    n = len(paragraphs)
    results: list[list[ParsedParagraph]] = [[] for _ in range(n)]
    i = 0
    while i < n:
        text, all_bold, style = paragraphs[i]
        stripped = text.strip()

        if not stripped:
            results[i] = [ParsedParagraph(ElementType.SKIP)]
            i += 1
            continue

        if all_bold and i + 1 < n:
            next_stripped = paragraphs[i + 1][0].strip()
            m = _LEGACY_NUMBERED_RE.match(next_stripped)
            if (
                m
                and not _LEGACY_HEADING_RE.match(stripped)
                and not _LEGACY_FUSED_RE.match(stripped)
                and not _LEGACY_FUSED_RE.match(next_stripped)
            ):
                results[i] = []  # consumed into next section's heading
                results[i + 1] = [
                    ParsedParagraph(ElementType.SECTION, number=m.group(1), heading=stripped),
                    ParsedParagraph(ElementType.BODY, text=m.group(2).strip()),
                ]
                i += 2
                continue

        results[i] = parse_paragraph_legacy(text, style)
        i += 1

    return results


@dataclass
class InlineSpan:
    text: str
    bold: bool = False
    italic: bool = False
    superscript: bool = False
    subscript: bool = False


@dataclass
class ParsedParagraph:
    element_type: ElementType
    number: str = ""
    heading: str = ""
    text: str = ""
    raw_style: str = ""
    table_rows: list[list[str]] = field(default_factory=list)
    spans: list[InlineSpan] = field(default_factory=list)


def _classify_annotation(style: str, stripped: str) -> ParsedParagraph | None:
    """Return NOTE/EXAMPLE/PENALTY ParsedParagraph if text or style matches; else None."""
    if style == "Note" or _NOTE_RE.match(stripped):
        return ParsedParagraph(ElementType.NOTE, text=stripped, raw_style=style)
    if style == "Example" or _EXAMPLE_RE.match(stripped):
        return ParsedParagraph(ElementType.EXAMPLE, text=stripped, raw_style=style)
    if style == "Penalty" or _PENALTY_RE.match(stripped):
        return ParsedParagraph(ElementType.PENALTY, text=stripped, raw_style=style)
    return None


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

    # Check for Note/Example/Penalty annotations (any non-ActHead style)
    if not style.startswith("ActHead"):
        annotation = _classify_annotation(style, stripped)
        if annotation is not None:
            return annotation

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
        # Try level4 (uppercase alpha)
        m = _LEVEL4_RE.match(stripped)
        if m:
            return ParsedParagraph(
                ElementType.LEVEL4,
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
