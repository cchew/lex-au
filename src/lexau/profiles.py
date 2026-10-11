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
    # Extended definition grammar: qualifiers ("X, for Part 6A, ..."), "has the meaning given in",
    # signposts ("X see section N", "X, for Part 6A\u2014see section N") and lead-ins that end in a
    # dash as well as a colon. Off by default so Commonwealth output is unchanged.
    extended_definitions: bool = False
    # Trailing characters that mark a list-form definition lead-in ("X means:" / "X means\u2014").
    list_lead_ins: str = ":"
    # Character styles that mark a defined term (treated as bold+italic).
    char_def_styles: frozenset[str] = frozenset()

    def map_style(self, style: str) -> str:
        return self.style_map.get(style, style)
