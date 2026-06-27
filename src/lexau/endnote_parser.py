from __future__ import annotations

import re
from dataclasses import dataclass, field
from docx import Document
from docx.text.paragraph import Paragraph
from docx.table import Table

_ABBREV_NORMALISE = {"ad.": "ad", "am.": "am", "rep.": "rep", "rs.": "rs"}
_EFFECT_ALIASES = {
    "ad": "ad", "am": "am", "rep": "rep", "rs": "rs",
}

# Regex: "am No 70, 2009" or "am. No. 109, 2004" or "No 116, 1991" (continuation)
_SEGMENT = re.compile(
    r'^(?P<effect>[a-z]+)?\.?\s*'
    r'Nos?\.?\s*'
    r'(?P<nums>[\d][\d\s,and]+?)'
    r',\s*(?P<year>\d{4})',
    re.IGNORECASE,
)
_NUM_TOKENS = re.compile(r'\b(\d+)\b')

_NOT_APPLIED = re.compile(r'\(amdt\s+never\s+applied', re.IGNORECASE)
_STRUCTURAL_PROVISION = re.compile(
    r'^(Part|Division|Chapter|Subdivision)\s+', re.IGNORECASE
)


@dataclass
class LegislationHistoryEntry:
    act_name: str
    act_number: int | None
    act_year: int | None
    assent_raw: str
    commencement_raw: str


@dataclass
class AmendmentEvent:
    provision: str
    effect: str              # "am" | "ad" | "rep" | "rs"
    act_number: int
    act_year: int
    applied: bool = True
    raw_text: str = ""


@dataclass
class EndnoteResult:
    legislation_history: list[LegislationHistoryEntry] = field(default_factory=list)
    amendment_events: list[AmendmentEvent] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)


def parse_endnotes(doc: Document) -> EndnoteResult:
    result = EndnoteResult()
    in_endnotes = False
    current_section: str | None = None

    blocks = list(doc.iter_inner_content())

    for i, block in enumerate(blocks):
        if isinstance(block, Paragraph):
            style = block.style.name if block.style else ""
            text = block.text.strip()

            if style == "ENotesHeading 1" and text == "Endnotes":
                in_endnotes = True
                continue

            if not in_endnotes:
                continue

            if style == "ENotesHeading 2":
                current_section = text  # e.g. "Endnote 3—Legislation history"
                continue

        elif isinstance(block, Table) and in_endnotes:
            if current_section and "Endnote 3" in current_section:
                _parse_legislation_history_table(block, result)
            elif current_section and "Endnote 4" in current_section:
                _parse_amendment_history_table(block, result)

    return result


def _parse_legislation_history_table(table: Table, result: EndnoteResult) -> None:
    for row in table.rows:
        cells = [c.text.strip() for c in row.cells]
        if len(cells) < 2:
            continue
        act_name = cells[0]
        num_year_raw = cells[1] if len(cells) > 1 else ""
        assent_raw = cells[2] if len(cells) > 2 else ""
        comm_raw = cells[3] if len(cells) > 3 else ""

        if not act_name or act_name.lower() in {"act", "number and year"}:
            continue  # header row

        num, year = _parse_num_year(num_year_raw)
        result.legislation_history.append(LegislationHistoryEntry(
            act_name=act_name,
            act_number=num,
            act_year=year,
            assent_raw=assent_raw,
            commencement_raw=comm_raw,
        ))


def _parse_amendment_history_table(table: Table, result: EndnoteResult) -> None:
    current_provision: str = ""

    for row in table.rows:
        cells = [c.text.strip() for c in row.cells]
        if len(cells) < 2:
            continue

        col1 = cells[0]
        col2 = cells[1]

        # Skip header row
        if col1.lower() in {"provision affected", "provision\naffected"}:
            continue

        # Continuation row: col1 empty → inherit provision
        if col1:
            current_provision = col1

        if not current_provision:
            continue

        # Skip structural markers (Part I, Division 2, etc. with empty col2)
        if _STRUCTURAL_PROVISION.match(current_provision) and not col2:
            continue

        if not col2:
            continue

        events = _parse_how_affected(current_provision, col2, result)
        result.amendment_events.extend(events)


def _parse_num_year(raw: str) -> tuple[int | None, int | None]:
    m = re.search(r'(\d+),\s*(\d{4})', raw)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def _parse_how_affected(provision: str, raw: str, result: EndnoteResult) -> list[AmendmentEvent]:
    events: list[AmendmentEvent] = []
    applied = not bool(_NOT_APPLIED.search(raw))

    segments = re.split(r';\s*', raw)
    current_effect: str | None = None

    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        # Strip trailing editorial notes like "(amdt never applied...)"
        seg_clean = re.sub(r'\(amdt.*', '', seg, flags=re.IGNORECASE).strip()

        m = _SEGMENT.match(seg_clean)
        if not m:
            # Could be a free-text note — log and skip
            result.parse_errors.append(f"Unmatched segment: {seg!r} (provision: {provision!r})")
            continue

        effect_raw = m.group("effect")
        if effect_raw:
            effect_norm = _ABBREV_NORMALISE.get(effect_raw.lower() + ".", effect_raw.lower())
            current_effect = _EFFECT_ALIASES.get(effect_norm, effect_norm)
        # If no effect in this segment, carry forward current_effect

        if not current_effect:
            result.parse_errors.append(f"No effect code for segment: {seg!r}")
            continue

        year = int(m.group("year"))
        nums_raw = m.group("nums")
        nums = [int(n) for n in _NUM_TOKENS.findall(nums_raw)]

        for num in nums:
            events.append(AmendmentEvent(
                provision=provision,
                effect=current_effect,
                act_number=num,
                act_year=year,
                applied=applied,
                raw_text=raw,
            ))

    return events
