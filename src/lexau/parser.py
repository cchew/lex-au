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
_LEGACY_SECTION_HEADING_STYLES = frozenset({"heading 5"})


def _normalize_style_name(style: str) -> str:
    """Fold a docx style name to its base form for legacy-shape matching.

    LibreOffice serializes the same conceptual style differently depending
    on whether the source was OLE2 .doc ("Heading 5") or RTF ("heading 5,s"
    — lowercase, comma-appended alias suffix). Comparing on text-before-
    first-comma, lowercased, treats both as the same style.
    """
    return style.split(",", 1)[0].strip().lower()


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

    if _normalize_style_name(style) in _LEGACY_SECTION_HEADING_STYLES:
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

# Legacy shape 4: number + heading FUSED on one line, e.g. "1 Short title"
# (single space, no period — unlike shape 1's "1.\tThis Act...", and unlike
# _SECTION_RE's 2+-whitespace "4  Short title" which only fires behind an
# ActHead style gate that legacy documents never carry). Confirmed against
# five 1996 omnibus amendment Acts (Task 12, family-F XSD triage) whose
# section headings are typeset as one "<n> Heading" paragraph followed by a
# separate body-text paragraph with no number of its own — e.g. vocational-
# education-and-training-funding-laws-amendment-act-1996's "1 Short title"
# / "2 Commencement" / "3 Schedule(s)" (fully bold in that Act). Despite
# the original design assuming shape 4 would always be bold, education-
# and-training-legislation-amendment-act-1996's OWN "1 Short title" is
# plain, unbolded text (only its sibling "2 Commencement" and "3
# Schedule(s)" are bold) — confirmed by re-inspecting all 8 target DOCX
# files directly rather than extrapolating from a few. Matching in
# classify_legacy_stream is therefore gated on `candidacy_open` (past the
# enacting formula, not past a Schedule heading) plus the sequential-number
# check, exactly like shape 1's non-bold donor fallback below — NOT on
# boldness, which this class of Act does not consistently carry. Heading
# text must start uppercase to avoid matching an arbitrary sentence that
# happens to open with a digit.
_LEGACY_SHAPE4_HEADING_RE = re.compile(r'^(\d+[A-Z]*)[ \t]+([A-Z].*)$', re.DOTALL)

# Leading integer of a legacy section number ("26WA" -> 26), used only for
# the sequential-continuity check below — never for eId/heading generation.
_LEGACY_NUMBER_INT_RE = re.compile(r'^(\d+)')

# Enacting-formula detector for the sequential-number gate below. Broader
# than builder.py's own _ENACTING_RE/_WHEREAS_RE (which are scoped to that
# module's <formula>/<preamble> tagging and only match the exact modern
# "...enacts:" phrasing) -- this one also has to catch the old-style "BE it
# enacted by the King's/Queen's Most Excellent Majesty ... as follows :—"
# formula used by the pre-1960s Acts this task fixes, which _ENACTING_RE
# does not match (no bare "enacts:"). `search`, not `match`: the formula
# text is never the start of the paragraph in either shape.
_LEGACY_ENACTED_RE = re.compile(r'\benact\w*\b.*:', re.IGNORECASE | re.DOTALL)

# Schedule-heading detector for the sequential-number gate below -- a local
# copy of builder.py's own _SCHEDULE_RE (not imported, to avoid a
# parser<->builder circular dependency; builder.py already imports FROM
# parser.py). Real corpus finding (veterans'-affairs-legislation-amendment-
# act-(no.-1)-1996, surfaced by a corpus-wide regression scan of this fix):
# a Schedule item can itself be a fully-bold "<n> Heading"-shaped line
# QUOTING a section being inserted into the *target* Act being amended --
# e.g. Schedule item "3 After section 4C" / "Insert:" / "4D Exclusion of
# Consumer Credit Codes..." -- where "4D" is the *target* Act's new section
# number, not a section of *this* amending Act at all. Schedule item
# numbering restarts at 1 within each Schedule (confirmed elsewhere in this
# corpus, e.g. customs-and-excise-legislation-amendment-act-(no.-1)-1996's
# own "2 Subsection 2(3)" schedule item, which the sequential check already
# rejects because it doesn't continue the Act's own count) -- but nothing
# stops an inserted-section number from coincidentally continuing where
# this Act's own last real section left off, exactly as "4D" did here.
# Legacy documents never carry an ActHead style, so builder.py's own
# _is_schedule_heading() (style-gated) never fires for them and schedule
# content is never split out of the body stream at all -- closing that gap
# is a separate, larger task (flagged in this task's report). The narrower,
# safe fix here: once a genuine (fully-bold, to exclude a stray body-prose
# cross-reference like "Schedule 1 to this Act specifies...") Schedule
# heading is seen, BOTH new candidacy paths below stop firing for the rest
# of the stream -- past that point, every "<n> Heading"-shaped line belongs
# to Schedule-item numbering, not this Act's own top-level sections, and
# the sequential check has no reliable way to tell the two apart.
_LEGACY_SCHEDULE_HEADING_RE = re.compile(r'^Schedule[\xa0 ](\d+|[IVX]+)', re.IGNORECASE)

# Second, independent trigger for the same schedule gate: this Act's own
# "<n> Schedule(s)" section (the standard modern-template section 3 that
# announces "each Act specified in a Schedule to this Act is amended...").
# Corpus evidence (2 more real false positives caught by the corpus-wide
# regression scan after the bold-gated _LEGACY_SCHEDULE_HEADING_RE fix
# above): parliamentary-contributory-superannuation-amendment-act-1996's
# real "Schedule 1—..." heading and retirement-assistance-for-farmers-
# scheme-extension-act-2000's "Schedule\xa01—Social Security Act 1991" are
# BOTH plain, unbolded text (unlike veterans'-affairs-1996's bolded one),
# so _LEGACY_SCHEDULE_HEADING_RE's bold gate misses them -- their Schedule
# item numbers (parliamentary's "4 Subsection 18(10B)", retirement-
# assistance's ItemHead-styled "4  Paragraph 1185B(2)(b)") then coincide
# with this Act's own next-expected number and get misclassified as
# top-level sections, the exact same failure shape as "4D" above. This
# Act's own SECTION heading reading "Schedule(s)"/"Schedules"/"Schedule"
# (there is no ambiguity here about *whose* heading it is -- it was itself
# only just accepted as a genuine section by one of the two candidacy
# paths below) is a reliable, earlier trigger: in every Act this task and
# its regression scan touched, this heading announces the Act's own final
# top-level section before its Schedules begin, so nothing of this Act's
# own is lost by stopping there, regardless of whether the literal
# "Schedule N—Heading" line downstream happens to be bold. Matches the
# bare plural "Schedules" too (national-food-authority-amendment-
# act-1995's own section 3 heading; the original "Schedule\(s?\)\?"
# pattern required a literal "(" and missed it).
_LEGACY_SCHEDULES_SECTION_RE = re.compile(r'^Schedules?(\(s\))?$', re.IGNORECASE)

# Third, independent trigger for the same schedule gate, and the most
# reliable of the three: the STANDARD BOILERPLATE sentence this Act's own
# "<n> Schedule(s)" section body carries ("each Act that is specified in a
# Schedule to this Act is amended or repealed as set out in the applicable
# items..."), confirmed byte-for-byte or near-identical across every 1990s+
# omnibus amendment Act this task's corpus-wide regression scan touched
# (customs-and-excise-1996, vocational-education-1996, retirement-
# assistance-2000, parliamentary-contributory-superannuation-1996, ...).
# Unlike the heading-text trigger above, this does not depend on the
# section's own heading wording at all ("Schedule(s)" vs "Schedules" vs
# something else entirely) -- it is drafting boilerplate, present verbatim
# regardless of formatting quirks in any one Act, which is why it is
# searched for on EVERY paragraph (not just section headings) below.
_LEGACY_SCHEDULE_BOILERPLATE_RE = re.compile(
    r'specified in a Schedule to this Act is amended or repealed', re.IGNORECASE
)

# Fourth guard, orthogonal to the three schedule triggers above (it applies
# regardless of whether a schedule boundary was ever detected): reject a
# shape-4 candidate whose heading text is itself an amendment INSTRUCTION,
# using the small, closed vocabulary of drafting verbs Australian Schedule
# items are built from (OPC drafting convention: Omit/Insert/Repeal/
# Substitute/Add/Before/After, each followed by a quoted or referenced
# fragment). A genuine section heading is a noun phrase describing what the
# section does ("Short title", "Closure of accounts and fund"); a Schedule
# item is an imperative editing instruction ("Omit \"the\", substitute
# \"a\".", "Add at the end \"...\"."). Corpus evidence: this is what every
# remaining false positive the three schedule triggers above miss (Acts
# whose own Schedule-announcing section is titled something none of them
# recognise at all, e.g. "Amendments" -- commonwealth-electoral-amendment-
# act-1995, life-insurance-(consequential-amendments-and-repeals)-
# act-1995) actually looks like, independent of which Act or which
# schedule-heading phrasing produced it -- so this is a second, independent
# line of defence, not a duplicate of the three triggers above.
_LEGACY_AMENDMENT_INSTRUCTION_RE = re.compile(
    r'^(Omit|Insert|Repeal|Substitute|Add|Renumber|Before|After)\b', re.IGNORECASE
)

# Hard backstop, independent of all three schedule triggers above: none of
# this corpus's Acts have more than a handful of real top-level sections
# before their Schedules begin (this task's 8 target files: 2-4; every
# Act sampled by the regression scan with a genuine, cleanly-detected
# Schedule boundary: well under 10). A corpus-wide regression scan of this
# fix surfaced several much older (pre-1990s) or differently-drafted Acts
# (e.g. quarantine-amendment-act-1985, commonwealth-electoral-amendment-
# act-1995) whose Schedule section is phrased in ways none of the three
# triggers above recognise (heading text "Amendments"/"Scope of
# quarantine"/no announcing section at all) -- for those, the
# sequential-number fallback can run on into genuine Schedule-item content
# and misclassify it, exactly the family of bug the three triggers above
# exist to prevent. This cap bounds the worst case:
# once the running count would exceed it, both new candidacy paths stop
# firing outright, for the rest of the stream, regardless of the schedule
# gate's state. It costs nothing for this task's 8 target files (all well
# under the cap) and turns an unbounded run of tens of fabricated sections
# into, at worst, a handful -- the same order of magnitude this corpus's
# genuinely narrow legacy-shape gaps (e.g. the 1955 Act's unhandled
# em-dash-fused subsection shape, noted in this task's report) already
# leave on the table.
_LEGACY_FALLBACK_MAX_SECTION = 12


def classify_legacy_stream(paragraphs: list[tuple[str, bool, str]]) -> list[list[ParsedParagraph]]:
    """Classify a full legacy-Act paragraph stream, applying shape-1/4 lookback.

    `paragraphs` is (text, all_bold, style) per DOCX paragraph, in document
    order, where all_bold is True iff every non-whitespace run in that
    paragraph is bold, and style is the paragraph's DOCX style name (used
    for shape 3's Heading-5 detection; irrelevant to shapes 1/2/4).

    Returns one list of ParsedParagraph per input paragraph, aligned by
    index, so callers can still attach that paragraph's InlineSpans. A
    paragraph consumed as a shape-1 heading donor returns [] (its text
    becomes the following SECTION's heading instead of standalone BODY).

    A bold heading is NOT consumed as a shape-1 donor if the following
    paragraph is itself a fused section+subsection (shape 2, e.g.
    "1. (1) text") — that paragraph defers to parse_paragraph_legacy's
    fused handling instead, preserving the SUBSECTION structure that a
    shape-1 collapse would otherwise discard.

    Non-bold shape-1 donor + sequential-number gate (Task 12, family-F XSD
    fix): the donor's boldness was, until now, the SOLE signal distinguishing
    a genuine marginal-note heading from an ordinary body sentence that
    happens to precede a numbered paragraph (see the original 2026-07-18
    design note — a pure text heuristic risked swallowing the last sentence
    of a multi-paragraph section as a false heading). That signal is absent
    for three pre-1960s Acts (e.g. constitution-alteration-(state-debts)-
    1909) whose marginal notes were never bolded at all -- confirmed against
    the SAME "Short title." / "1.\ttext" template a *bolded*-donor Act
    (loan-act-(no.-2)-1976) already handles correctly, i.e. this is a
    formatting-inconsistency in the source documents, not a different
    template. Dropping the bold requirement outright would reopen exactly
    the risk the 2026-07-18 note flagged. Instead, a non-bold donor is only
    consumed when the candidate section number is EXACTLY one more than the
    last SECTION number classified so far in this stream (starting at 0, so
    the very first section must be "1"). Legislative section numbers are
    strictly sequential in original enactment text, and old-style Acts of
    this shape number every subsection with parenthesised markers ("(2.)"),
    never a bare digit — so an un-numbered body sentence can never precede a
    bare "<next-expected-N>.\ttext" paragraph by coincidence. This is why
    `test_classify_legacy_stream_ignores_non_bold_candidate`'s adversarial
    "This concludes..." donor (immediately followed by "3.\ttext", with no
    section 1 or 2 having been seen) is correctly rejected: 3 != 0 + 1.

    Enacting-formula gate on BOTH new paths (shape 4 and the non-bold
    shape-1 fallback): a corpus-wide regression scan surfaced a real false
    positive the sequential check alone does not catch — a Table of
    Provisions. australian-trade-commission-(transitional-provisions-and-
    consequential-amendments)-act-1985's front matter lists its real
    section 1 as a TOC entry ("Section" / "1.\tShort title", both plain,
    unstyled "Normal" paragraphs, not this Act's "TOC Heading"/"TOC N"
    styles the builder's own TOC detection expects) *before* its enacting
    formula and *before* the real, later "Short title." / "1.\ttext" pair.
    "Section" satisfies every donor-exclusion check above (it doesn't look
    like any operative element) and the TOC's "1.\tShort title" is,
    trivially, the first candidate the sequential check ever sees — so it
    passed. A Table of Provisions previews the Act's real numbering and can
    restart from 1 anywhere in the front matter; sequential continuity
    alone cannot tell a preview from the real thing. The Act's enacting
    formula ("BE it enacted by..."/"...Parliament of Australia enacts:")
    can: every Act in this corpus has exactly one, and everything before it
    is definitionally front matter (title, TOC, long title, assent date),
    never real operative text. `last_section_num` alone still governs which
    candidate number is expected; this only adds "and we're past the
    formula" as a precondition, so `test_classify_legacy_stream_shape1_
    heading_plus_numbered_body` and the other existing shape-1 fixtures
    (whose streams start right after their own formula, with no TOC) are
    unaffected. The bold-donor path's OWN firing condition
    (`if all_bold or sequential:`) is intentionally left ungated by
    `candidacy_open` — gating it retroactively (formula/schedule/cap) is
    not this fix's job, and every existing bold-donor fixture still passes
    unchanged.

    `donor_is_operative` itself, however, is NOT bold-donor-unchanged: it
    now also excludes `_LEGACY_NUMBERED_RE` / `_SUBSEC_RE` matches on the
    donor — checks that previously ran for non-bold donors only are now
    also applied when `all_bold` is True (the exclusion list is shared
    code, not duplicated per branch). This is a real, deliberate behaviour
    change on the bold-donor path, not a side effect: pre-fix, a
    fully-bold "1. This Act may be cited..." donor immediately followed by
    another numbered paragraph ("2.\ttext") would have been swallowed as
    THAT paragraph's heading donor — discarding section 1's own text into
    a nonsensical heading for section 2 (see `test_classify_legacy_
    stream_bold_donor_matching_numbered_shape_not_swallowed`). Both
    additions require the donor's own text to already look like an
    operative numbered clause -- a genuine marginal note never does -- so
    neither can reject a real donor.

    A THIRD addition here originally -- `_LEGACY_SHAPE4_HEADING_RE` on the
    donor, meant to stop a rejected shape-4 candidate being reused as an
    unrelated donor -- was removed after a corpus-wide decrease-direction
    scan found it excluded a genuine one: veterans'-entitlements-
    (rewrite)-transition-act-1991's real donor "1990 Budget amendments"
    (a bold marginal note that happens to start with a year) immediately
    precedes "19.\tThe Principal Act is further amended...", and matches
    `_LEGACY_SHAPE4_HEADING_RE`'s digit-then-capital shape purely by
    coincidence, discarding section 19's heading. Unlike the two additions
    above, this one did NOT require the donor to already look like an
    operative clause -- a plain "<digits> Capitalised text" shape is far
    too common in ordinary prose to safely gate boldness-proven donor
    candidacy on. No confirmed corpus case (including the two false
    positives this task's report documents) actually depended on it: the
    full existing test suite, including both false-positive regression
    tests, passes with it removed. The change can only ever REMOVE a donor
    candidacy, never grant one it didn't already have, so neither addition
    can be the source of the corpus-wide fabricated-section false
    positives documented in this task's report — those are produced by the
    two NEW paths (shape 4, non-bold shape-1) reaching Schedule-item
    content, not by donor-exclusion widening. See this task's report for
    the decrease-direction scan commands, the veterans'-entitlements-1991
    finding and fix, and the coverage caveat (stitched from several
    overlapping runs after background-task instability prevented one
    continuous full-corpus pass).

    Schedule gate on the same two new paths (three independent triggers --
    see _LEGACY_SCHEDULE_HEADING_RE, _LEGACY_SCHEDULES_SECTION_RE and
    _LEGACY_SCHEDULE_BOILERPLATE_RE above for the full corpus findings --
    plus a hard numeric backstop, _LEGACY_FALLBACK_MAX_SECTION, for Acts
    none of the three text triggers recognise): once any trigger fires,
    `candidacy_open` goes False for the rest of the stream, so neither new
    path fires on Schedule-item numbering or on quoted section numbers
    describing the *target* Act being amended.
    """
    n = len(paragraphs)
    results: list[list[ParsedParagraph]] = [[] for _ in range(n)]
    last_section_num: int = 0
    past_enacting_formula = False
    past_schedule_heading = False
    i = 0
    while i < n:
        text, all_bold, style = paragraphs[i]
        stripped = text.strip()

        if not stripped:
            results[i] = [ParsedParagraph(ElementType.SKIP)]
            i += 1
            continue

        # Snapshot BEFORE updating. For the formula: the enacting-formula
        # paragraph itself must never be usable as a shape-1 donor in this
        # same iteration -- without the snapshot, a "the very next paragraph
        # is 1.\ttext" Act would have the formula's own text (which passes
        # every donor exclusion check; it is not a marginal note) wrongly
        # consumed as section 1's heading.
        #
        # For the schedule triggers the snapshot has the OPPOSITE effect:
        # it leaves candidacy OPEN on the very paragraph that flips
        # `past_schedule_heading` to True, not closed. This is deliberately
        # left as-is rather than "fixed" to close-on-the-same-paragraph: no
        # Schedule-heading-matching text ever also matches a candidate
        # shape in this corpus (a "Schedule N—Heading" line does not start
        # with a digit; the boilerplate sentence is ordinary prose), so the
        # exploitable window is empty in practice, and it is covered
        # regardless by the sequential-number and amendment-instruction
        # guards below if it were ever reached.
        formula_seen_before_this_para = past_enacting_formula
        schedule_seen_before_this_para = past_schedule_heading
        if _LEGACY_ENACTED_RE.search(stripped):
            past_enacting_formula = True
        if all_bold and _LEGACY_SCHEDULE_HEADING_RE.match(stripped):
            past_schedule_heading = True
        if _LEGACY_SCHEDULE_BOILERPLATE_RE.search(stripped):
            past_schedule_heading = True

        candidacy_open = (
            formula_seen_before_this_para
            and not schedule_seen_before_this_para
            and last_section_num < _LEGACY_FALLBACK_MAX_SECTION
        )

        if candidacy_open:
            # No _LEGACY_HEADING_RE / _LEGACY_FUSED_RE exclusion needed here
            # (unlike the shape-1 donor check below): _LEGACY_SHAPE4_HEADING_RE
            # requires a digit-leading string, HEADING_RE requires one of
            # Chapter/Part/Division/Subdivision, and FUSED_RE requires a
            # period immediately after the number -- none of the three can
            # match the same string m4 just matched.
            m4 = _LEGACY_SHAPE4_HEADING_RE.match(stripped)
            if m4:
                candidate_num = _leading_int(m4.group(1))
                heading = m4.group(2).strip()
                if (
                    candidate_num is not None
                    and candidate_num == last_section_num + 1
                    and not _LEGACY_AMENDMENT_INSTRUCTION_RE.match(heading)
                ):
                    results[i] = [
                        ParsedParagraph(ElementType.SECTION, number=m4.group(1), heading=heading)
                    ]
                    last_section_num = candidate_num
                    if _LEGACY_SCHEDULES_SECTION_RE.match(heading):
                        past_schedule_heading = True
                    i += 1
                    continue

        if i + 1 < n:
            next_stripped = paragraphs[i + 1][0].strip()
            m = _LEGACY_NUMBERED_RE.match(next_stripped)
            donor_is_operative = (
                _LEGACY_HEADING_RE.match(stripped)
                or _LEGACY_FUSED_RE.match(stripped)
                or _LEGACY_NUMBERED_RE.match(stripped)
                or _SUBSEC_RE.match(stripped)
            )
            if m and not donor_is_operative and not _LEGACY_FUSED_RE.match(next_stripped):
                candidate_num = _leading_int(m.group(1))
                sequential = (
                    candidacy_open
                    and candidate_num is not None
                    and candidate_num == last_section_num + 1
                )
                if all_bold or sequential:
                    results[i] = []  # consumed into next section's heading
                    results[i + 1] = [
                        ParsedParagraph(ElementType.SECTION, number=m.group(1), heading=stripped),
                        ParsedParagraph(ElementType.BODY, text=m.group(2).strip()),
                    ]
                    if candidate_num is not None:
                        last_section_num = candidate_num
                    if _LEGACY_SCHEDULES_SECTION_RE.match(stripped):
                        past_schedule_heading = True
                    i += 2
                    continue

        results[i] = parse_paragraph_legacy(text, style)
        for r in results[i]:
            if r.element_type == ElementType.SECTION:
                num = _leading_int(r.number)
                if num is not None:
                    last_section_num = num
                if _LEGACY_SCHEDULES_SECTION_RE.match(r.heading or ""):
                    past_schedule_heading = True
        i += 1

    return results


def _leading_int(number: str) -> int | None:
    """Leading integer of a legacy section number string, or None."""
    m = _LEGACY_NUMBER_INT_RE.match(number)
    return int(m.group(1)) if m else None


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
    volume_index: int = 0
    # For FIGURE paragraphs: (dotted-lowercase ext, image bytes) per embedded
    # image, in document order. Empty for every other element type and for a
    # FIGURE whose blips have no resolvable embed relationship.
    image_blobs: list[tuple[str, bytes]] = field(default_factory=list)


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
