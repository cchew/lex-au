"""Optional per-source parsing profiles.

A profile adapts the Commonwealth-tuned parser to documents authored with a different
template (state and territory registers). Every field defaults to "no change", so
passing ``None`` or ``ParserProfile()`` reproduces existing behaviour exactly.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ParserProfile:
    name: str = "cth"
    # Source paragraph style -> style name the parser already understands
    # (e.g. "Draft Heading 1" -> "ActHead 5", "Subsection" -> "Body Text").
    style_map: Mapping[str, str] = field(default_factory=dict)
    # Overrides for parser._HEADING_RE / parser._SECTION_RE (None = keep default).
    heading_re: re.Pattern[str] | None = None
    section_re: re.Pattern[str] | None = None
    # Overrides termlinks._DEF_HEADING_RE: section headings that mark a definitions section.
    def_heading_re: re.Pattern[str] | None = None
    # Paragraph text that is a schedule heading whatever its source style (retagged to ActHead 1).
    schedule_heading_re: re.Pattern[str] | None = None
    # Also treat a schedule whose heading matches (e.g. Qld 'Schedule 5 Dictionary') as a definitions section.
    definitions_in_schedules: bool = False
    # Inside a schedule, paragraphs matching one of these become clause headings or dotted
    # subclauses whatever their source style (principles are numbered "1.", "1.1" or "IPP 1" in
    # "Normal"-style text). Each pattern needs named groups `number` and `heading`.
    schedule_clause_res: tuple[re.Pattern[str], ...] = ()
    # Tag locally scoped definitions ("In this Part, X means ...", or a formatted term opening a paragraph
    # inside an ordinary section). Formatted terms only. The term id carries its container
    # (term-x--part-1__sec-4) so it cannot collide with an Act-wide term of the same word.
    local_definitions: bool = False
    # Headings that open an unnumbered schedule-like container (ACT "Dictionary"). The paragraph
    # becomes a schedule heading; everything after it, up to the next schedule heading, belongs to it.
    unnumbered_schedule_re: re.Pattern[str] | None = None
    # Paragraph styles dropped entirely (non-operative back matter such as amendment-history endnotes).
    skip_styles: frozenset[str] = frozenset()
    # Tag "In this Act, X means ..." (and "For this Act, ...") wherever it appears, not only in
    # definitions-headed sections. Act-wide scope only. Off by default; the Commonwealth corpus
    # stays off until a precision review passes.
    scope_phrase_definitions: bool = False
    # Extended definition grammar: qualifiers ("X, for Part 6A, ..."), "has the meaning given in",
    # signposts ("X see section N", "X, for Part 6A\u2014see section N") and lead-ins that end in a
    # dash as well as a colon. Off by default so Commonwealth output is unchanged.
    extended_definitions: bool = False
    # Trailing characters that mark a list-form definition lead-in ("X means:" / "X means\u2014").
    list_lead_ins: str = ":"
    # Character styles that mark a defined term (treated as bold+italic).
    char_def_styles: frozenset[str] = frozenset()
    # Treat a Schedule headed exactly "Dictionary" (numbered or not, no amendment items or quoted
    # text) as an Act-wide definitions container even when definitions_in_schedules is off.
    # Dictionary Parts whose heading or chapeau limits them ("In this Part, Parts 42, ...") are skipped.
    dictionary_schedules: bool = False

    def map_style(self, style: str) -> str:
        return self.style_map.get(style, style)


# Commonwealth Acts: tag locally scoped definitions and "In this Act, X means" wherever it appears.
CTH_PROFILE: ParserProfile = ParserProfile(
    local_definitions=True, scope_phrase_definitions=True, dictionary_schedules=True
)


def profile_for(doc_type: str, local_definitions: bool) -> ParserProfile | None:
    """Profile for a Commonwealth build; None (unchanged behaviour) unless opted in for Acts."""
    if local_definitions and doc_type == "act":
        return CTH_PROFILE
    return None
