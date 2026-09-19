from __future__ import annotations

import re
from dataclasses import replace, dataclass
from datetime import date
from pathlib import Path
from lxml import etree
from lxml.builder import ElementMaker
from itertools import groupby

from lexau.models import ActMetadata, ParseReport
from lexau.parser import ParsedParagraph, ElementType, InlineSpan
from lexau.frbr import make_eid
from lexau.validator import validate_akn, ValidationResult
from lexau.reflinks import inject_refs
from lexau.termlinks import inject_terms, inject_list_defs, complete_list_definitions
from lexau.quantlinks import inject_quantities, inject_roles, inject_asterisk_refs
from lexau.datelinks import inject_dates
from lexau.figures import materialise_figures
from docx import Document as DocxDocument
from lexau.endnote_parser import parse_endnotes, AmendmentEvent, EndnoteResult

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
AKN = ElementMaker(namespace=AKN_NS, nsmap={None: AKN_NS})

# ElementType.value → AKN tag name
_AKN_TAG = {
    ElementType.CHAPTER:      "chapter",
    ElementType.PART:         "part",
    ElementType.DIVISION:     "division",
    ElementType.SUBDIVISION:  "subDivision",
    ElementType.SECTION:      "section",
    ElementType.SUBSECTION:   "subsection",
    ElementType.PARAGRAPH:    "paragraph",
    ElementType.SUBPARAGRAPH: "subparagraph",
    ElementType.LEVEL4:       "hcontainer",  # uses name="level4" — handled specially
}

# Hierarchy depth (lower = higher in tree)
_DEPTH = {
    ElementType.CHAPTER:      0,
    ElementType.PART:         1,
    ElementType.DIVISION:     2,
    ElementType.SUBDIVISION:  3,
    ElementType.SECTION:      4,
    ElementType.SUBSECTION:   5,
    ElementType.PARAGRAPH:    6,
    ElementType.LIST_ITEM:    6,
    ElementType.SUBPARAGRAPH: 7,
    ElementType.LEVEL4:       8,
}

_ROMAN_CHARS = frozenset("ivxlcdm")

_TOC_HEADING_STYLE = "TOC Heading"
_TOC_ITEM_STYLES = {"TOC 1", "TOC 2", "TOC 3"}
_SCHEDULE_RE = re.compile(r'^Schedule[\xa0 ](\d+|[IVX]+)', re.IGNORECASE)
_ENACTING_RE = re.compile(r'\benacts?\s*:', re.IGNORECASE)
_WHEREAS_RE  = re.compile(r'^WHEREAS\b', re.IGNORECASE)
_STRUCTURAL = frozenset({
    ElementType.CHAPTER, ElementType.PART, ElementType.DIVISION,
    ElementType.SUBDIVISION, ElementType.SECTION,
})

# Schedule clause detection — applied to BODY paragraphs within schedule content
# Check order: APP_CLAUSE first, then SUBCLAUSE (3+ parts), then CLAUSE (1-2 parts)
_APP_CLAUSE_RE = re.compile(
    r'^APP\s+(\d+(?:\.\d+)*)\s*(?:[—–\-]\s*)?([A-Z].*)',
    re.DOTALL,
)
_SUBCLAUSE_RE = re.compile(r'^(\d+(?:\.\d+){1,})\s+([A-Z].*)', re.DOTALL)
_CLAUSE_RE    = re.compile(r'^(\d+[A-Z]?(?:\.\d+[A-Z]?)*)\s+([A-Z].*)', re.DOTALL)
_DATE_PREFIX_RE = re.compile(r'^(?:January|February|March|April|May|June|July|August|September|October|November|December)\b', re.IGNORECASE)
_DATE_PATTERN_RE = re.compile(r'^\d{1,2}\s+\w+\s+\d{4}')

_NOTE_REF_RE = re.compile(r'\[note\s+(\d+)\]', re.IGNORECASE)

# Single-character quote markers that delimit quoted structures in amendments
_QUOTE_MARKERS = frozenset({'"', "'", "“", "”", "‘", "’"})

# Structural element types that can appear inside a quotedStructure
_QUOTED_STRUCTURAL = frozenset({
    ElementType.CHAPTER, ElementType.PART, ElementType.DIVISION,
    ElementType.SUBDIVISION, ElementType.SECTION, ElementType.SUBSECTION,
})

@dataclass
class _QuotedSpan:
    """Sentinel inserted into a preprocessed paragraph stream to represent a single-provision quoted structure."""
    inner_paras: list[ParsedParagraph]


def _preprocess_quoted_structures(
    body_paras: list[ParsedParagraph],
) -> tuple[list[ParsedParagraph | _QuotedSpan], int, int]:
    """Scan body_paras for single-quote-marker spans and replace with _QuotedSpan sentinels.

    Returns (new_stream, found_count, unhandled_count).

    Rules:
    - Opening marker: BODY paragraph whose stripped text is a single quote character.
    - Closing marker: same (any single quote char).
    - Single-provision: exactly one top-level structural element between markers → emit as _QuotedSpan.
    - Multi-provision: 2+ top-level structural elements between markers → unhandled, emit inner content as-is (drop markers).
    """
    found = 0
    unhandled = 0
    result: list[ParsedParagraph | _QuotedSpan] = []
    i = 0
    n = len(body_paras)

    while i < n:
        p = body_paras[i]
        # Detect opening quote marker
        if (
            p.element_type == ElementType.BODY
            and p.text is not None
            and p.text.strip() in _QUOTE_MARKERS
        ):
            # Search for closing marker
            close_idx = None
            for j in range(i + 1, n):
                q = body_paras[j]
                if (
                    q.element_type == ElementType.BODY
                    and q.text is not None
                    and q.text.strip() in _QUOTE_MARKERS
                ):
                    close_idx = j
                    break

            if close_idx is not None:
                inner = body_paras[i + 1 : close_idx]
                # Count top-level structural elements in inner.
                # "Top-level" = the minimum depth seen among structural elements;
                # only elements at that exact depth level count as provisions.
                structural_depths = [
                    _DEPTH[ip.element_type]
                    for ip in inner
                    if ip.element_type in _QUOTED_STRUCTURAL
                ]
                if structural_depths:
                    min_depth = min(structural_depths)
                    top_level_structural = sum(
                        1 for d in structural_depths if d == min_depth
                    )
                else:
                    top_level_structural = 0
                if top_level_structural == 1:
                    found += 1
                    result.append(_QuotedSpan(inner_paras=inner))
                else:
                    # Multi-provision or empty — drop markers, emit inner as-is
                    unhandled += 1
                    result.extend(inner)
                i = close_idx + 1
                continue

        result.append(p)
        i += 1

    return result, found, unhandled


# --- Schedule structure (spec §3 B4 + the B1 grouping-wrapper increment) ----
#
# DOCX paragraph *style names* (as python-docx reports them, not styleIds) that
# mark the two independent numbering spaces inside an amending schedule:
#   ItemHead / Item — the amendment-instruction list ("30  Section 9 ...",
#                     "Repeal the section, substitute:")
#   ActHead 1-5     — the amended Act's OWN hierarchy; inside a schedule these
#                     only ever appear as *quoted* replacement law
#   ActHead 6/7/8   — the schedule's own Schedule/Part/Division headings
#   ActHead 9       — the amended-Act citation heading that groups items
# Before B4 both numbering spaces collapsed into one flat
# `schedule-N__clause-<num>` namespace (P1 note, mechanisms M3b/M3bt/M2/M1).
_ITEM_HEAD_STYLE = "ItemHead"
_INSTRUCTION_STYLE_PREFIXES = ("Item", "Subitem")
_SCHEDULE_HEAD_STYLES = frozenset({"ActHead 6", "ActHead 7", "ActHead 8"})
_AMENDED_ACT_STYLE = "ActHead 9"
# Editorial marginal note about an amendment item ("Note: This item fixes a
# misdescribed amendment."). Never part of the quoted replacement text.
_MARGIN_NOTE_STYLE = "note(margin)"
# Item-head styles used INSIDE quoted replacement law (a whole amendment item
# being re-enacted). Once one appears, `Item`-styled instructions in that run
# belong to the quoted item, not to the outer schedule item.
_NESTED_ITEM_HEAD_STYLES = frozenset({"Special ih", "SubitemHead"})
# Amendment verbs that open a quoted replacement provision. Built from a
# corpus-wide scan of every `Item`/`Subitem`-styled, colon-terminated paragraph
# in schedule content -- see `_is_quote_opening_instruction` for why style plus
# a trailing colon is not a sufficient test on its own.
_INSTRUCTION_VERB_RE = re.compile(
    r'^(?:insert|omit|repeal|add|substitute|after|before)\b',
    re.IGNORECASE,
)
# Rendered table-of-contents lines inside schedule content. The schedule's own
# sections already carry these headings, so the TOC line is pure duplication
# (P1 note mechanism M3bt).
_TOC_STYLE_RE = re.compile(r'^(?:Special\s+TOC|Schedule\s+TOC|TOC)\b')
# "1  Section 12" -> ("1", "Section 12"). Same two-or-more-separator shape the
# parser's _SECTION_RE uses, widened to accept \xa0 as a separator.
_ITEM_HEAD_RE = re.compile(r'^(\S+)[ \t\xa0]{2,}(.+)$', re.DOTALL)
_ITEM_NUM_RE = re.compile(r'^\d+[A-Z]*$')
# Element types that get a schedule-scoped grouping wrapper.
_SCHEDULE_GROUPING = (
    ElementType.CHAPTER, ElementType.PART,
    ElementType.DIVISION, ElementType.SUBDIVISION,
)


@dataclass
class _ScheduleItem:
    """One amendment-instruction item: an `ItemHead` line plus everything up to
    the next schedule-level structural break, with quoted replacement provisions
    already isolated as `_QuotedSpan` sentinels."""
    num: str
    heading: str
    body: list["ParsedParagraph | _QuotedSpan"]


def _is_toc_paragraph(p: ParsedParagraph) -> bool:
    return bool(_TOC_STYLE_RE.match(p.raw_style.strip()))


def _is_item_head(p: ParsedParagraph) -> bool:
    return (
        p.element_type == ElementType.BODY
        and p.raw_style == _ITEM_HEAD_STYLE
        and bool(p.text)
    )


def _is_instruction_paragraph(p: ParsedParagraph) -> bool:
    return (
        p.element_type == ElementType.BODY
        and p.raw_style.startswith(_INSTRUCTION_STYLE_PREFIXES)
        and bool(p.text)
    )


def _is_amended_act_heading(p: ParsedParagraph) -> bool:
    return (
        p.element_type == ElementType.BODY
        and p.raw_style == _AMENDED_ACT_STYLE
        and bool(p.text)
    )


def _is_schedule_structural_break(p: ParsedParagraph) -> bool:
    """A heading that closes any open amendment item (and any quoted run inside it).

    Deliberately style-gated on ActHead 6/7/8 rather than on ElementType alone:
    a PART/DIVISION paragraph styled ActHead 2/3 inside an amending schedule is
    the *amended Act's* Part being re-enacted (quoted law), not a boundary in the
    schedule's own structure.
    """
    return (
        _is_item_head(p)
        or _is_amended_act_heading(p)
        or (p.element_type in _STRUCTURAL and p.raw_style in _SCHEDULE_HEAD_STYLES)
        or _is_schedule_heading(p)
    )


def _is_quote_opening_instruction(p: ParsedParagraph) -> bool:
    """True if `p` is an amendment instruction that introduces quoted text.

    Style + trailing colon alone is NOT enough, in either direction, and both
    failure modes are real (measured over every `Item`/`Subitem`-styled,
    colon-terminated schedule paragraph in the corpus):

    - *False positive* — `Item`-styled prose inside a transitional or
      application provision routinely ends in a colon without being an
      instruction: "In this Part:", "If:", "The repeal of section 5 does not
      affect:", "eligible financial year means:". Treating those as openers
      wraps ordinary prose in a spurious `<quotedStructure>`.
    - *False negative* — a second instruction inside one item ("... substitute:"
      after an earlier "Omit:") must CLOSE the open quoted run and open its own.

    The leading amendment verb is what separates the two, so it gates both the
    opening decision and the mid-run termination in `_preprocess_schedule_group`.
    """
    if not _is_instruction_paragraph(p):
        return False
    text = p.text.rstrip()
    return text.endswith(":") and bool(_INSTRUCTION_VERB_RE.match(text))


def _ends_quoted_run(p: ParsedParagraph) -> bool:
    return _is_schedule_structural_break(p) or p.raw_style == _MARGIN_NOTE_STYLE


def _split_item_head(text: str) -> tuple[str, str]:
    """Split "30  Section 9 of the Code" into ("30", "Section 9 of the Code")."""
    stripped = text.strip()
    m = _ITEM_HEAD_RE.match(stripped)
    if m:
        return m.group(1), m.group(2).strip()
    m = re.match(r'^(\S+)\s+(.+)$', stripped, re.DOTALL)
    if m and _ITEM_NUM_RE.match(m.group(1)):
        return m.group(1), m.group(2).strip()
    return "", stripped


def _preprocess_schedule_group(
    paragraphs: list[ParsedParagraph],
) -> list[ParsedParagraph | _ScheduleItem]:
    """Segment a schedule's paragraph stream before any clause fabrication runs.

    Three transforms, all confined to the schedule subtree:
      1. `Special TOC *` / `Schedule TOC` / `TOC *` paragraphs are dropped (M3bt).
      2. An `ItemHead` line and everything up to the next schedule-level
         structural break become one `_ScheduleItem` (M3b half a).
      3. Inside an item, the run following an instruction line that ends in a
         colon ("Insert:", "Repeal the section, substitute:") is the quoted
         replacement provision and becomes a `_QuotedSpan` (M3b half b).

    A schedule with no `ItemHead` anywhere round-trips unchanged apart from
    TOC removal, which is what keeps plain non-amending schedules byte-identical.
    """
    out: list[ParsedParagraph | _ScheduleItem] = []
    i = 0
    n = len(paragraphs)
    while i < n:
        p = paragraphs[i]
        if _is_toc_paragraph(p):
            i += 1
            continue
        if not _is_item_head(p):
            out.append(p)
            i += 1
            continue

        num, heading = _split_item_head(p.text)
        item = _ScheduleItem(num=num, heading=heading, body=[])
        i += 1
        while i < n and not _is_schedule_structural_break(paragraphs[i]):
            q = paragraphs[i]
            i += 1
            if _is_toc_paragraph(q):
                continue
            item.body.append(q)
            if not _is_quote_opening_instruction(q):
                continue
            # Scan to the end of the quoted replacement provision. As well as a
            # structural break, a FRESH amendment instruction closes the run --
            # one item can carry several ("Omit: <old>" then "substitute: <new>"),
            # and without this the second instruction and everything after it is
            # swallowed into the first <quotedStructure> and rendered as quoted
            # law. Suppressed once the run has opened its own nested
            # amendment-item context (`Special ih` / `SubitemHead`): from there
            # on an "Insert:" belongs to the replacement item being quoted, not
            # to the outer schedule item.
            j = i
            nested = False
            while j < n:
                q2 = paragraphs[j]
                if _ends_quoted_run(q2):
                    break
                if not nested and _is_quote_opening_instruction(q2):
                    break
                if q2.raw_style in _NESTED_ITEM_HEAD_STYLES:
                    nested = True
                j += 1
            inner = [x for x in paragraphs[i:j] if not _is_toc_paragraph(x)]
            if inner:
                item.body.append(_QuotedSpan(inner_paras=inner))
            i = j
        out.append(item)
    return out


def _unique_quoted_eid(eid: str, seen: set[str]) -> str:
    """Disambiguate `eid` against `seen` with a numeric occurrence suffix,
    leaving the first occurrence unchanged (same shape as `_build_schedule_
    content`'s local `_unique`, extracted so `_build_quoted_content` can share
    one collision-tracking set across every call for one schedule (Task 13).

    `_build_quoted_content` had no uniquification at all before Task 13: two
    structural siblings at the same stack depth -- e.g. two independent
    nested-item quotes each restarting at "Part 1" (`_NESTED_ITEM_HEAD_STYLES`),
    or two un-spanned instruction-prose chunks in one item that both carry a
    bare paragraph letter -- minted the identical `@eId` twice. Schedule-only:
    called from `_build_quoted_content`, which is only ever reached via
    `_build_item_body` / `_build_schedule_content`, never from `AknBuilder.
    build()`'s body loop.
    """
    if eid not in seen:
        seen.add(eid)
        return eid
    n = 2
    while f"{eid}-{n}" in seen:
        n += 1
    seen.add(f"{eid}-{n}")
    return f"{eid}-{n}"


def _build_quoted_content(
    container: etree._Element,
    eid_prefix: str,
    paragraphs: list[ParsedParagraph],
    seen_eids: set[str],
) -> None:
    """Build a body-shaped hierarchy under `container`, with every eId rooted at
    `eid_prefix`.

    Used for the inside of a schedule `<quotedStructure>` and for an amendment
    item's own instruction prose. Mirrors the body loop in `AknBuilder.build()`
    but is a separate function on purpose: `eid_prefix` is always a
    `schedule-*` string, so nothing here can shift a body-level `@eId`.
    `make_eid` is only *read* — the body eId generator is untouched.

    `seen_eids` (Task 13) is the same set across every call belonging to one
    schedule -- shared with `_build_item_body`'s sibling calls for the same
    item and across items -- so a residual same-scope collision gets an
    occurrence suffix instead of a silent duplicate `@eId`.
    """
    stack: list[tuple[ElementType, str, etree._Element]] = []
    current_content: etree._Element | None = None
    blocklist_el: etree._Element | None = None
    blocklist_level: int = -1
    blocklist_count: int = 0

    def _join(*parts: str) -> str:
        return "__".join(x for x in parts if x)

    for p in paragraphs:
        p = _resolve_para_ambiguity(p, stack)

        if p.element_type in _AKN_TAG:
            blocklist_el = None
            blocklist_level = -1
            blocklist_count = 0
            current_content = None
            target_depth = _DEPTH.get(p.element_type, 99)
            while stack and _DEPTH.get(stack[-1][0], -1) >= target_depth:
                stack.pop()
            parent = stack[-1][2] if stack else container
            # Read the immediate ancestor's *actual* (already-disambiguated)
            # eId rather than re-deriving it from (type, num) pairs on the
            # stack -- necessary since Task 13, where a sibling collision
            # further up can give an ancestor an occurrence-suffixed eId that
            # `make_eid(et.value, num)` would not reproduce.
            prefix = parent.get("eId", eid_prefix)
            full_eid = _unique_quoted_eid(
                _join(prefix, make_eid(p.element_type.value, p.number)), seen_eids
            )
            if p.element_type == ElementType.LEVEL4:
                elem = etree.SubElement(
                    parent, f"{{{AKN_NS}}}hcontainer", name="level4", eId=full_eid
                )
            else:
                tag = _AKN_TAG[p.element_type]
                elem = etree.SubElement(parent, f"{{{AKN_NS}}}{tag}", eId=full_eid)
            etree.SubElement(elem, f"{{{AKN_NS}}}num").text = p.number
            if p.heading:
                etree.SubElement(elem, f"{{{AKN_NS}}}heading").text = p.heading
            stack.append((p.element_type, p.number, elem))
            if p.element_type in {
                ElementType.SUBSECTION, ElementType.PARAGRAPH,
                ElementType.SUBPARAGRAPH, ElementType.LEVEL4,
            } and p.text:
                content_el = etree.SubElement(elem, f"{{{AKN_NS}}}content")
                p_el = etree.SubElement(content_el, f"{{{AKN_NS}}}p")
                _emit_p_inline(p_el, p)

        elif p.element_type == ElementType.LIST_ITEM:
            level = int(p.number) if p.number.isdigit() else 0
            parent = stack[-1][2] if stack else container
            # Same ancestor-eId read as the structural branch above, for the
            # same reason: a disambiguated ancestor's ".value, num)" pair no
            # longer matches its actual eId.
            section_prefix = parent.get("eId", eid_prefix)
            if blocklist_el is None or level != blocklist_level:
                # `blocklist_count` resets to 0 at the top of every
                # `_build_quoted_content` call (like `_build_item_body`'s
                # other per-call state), so two prose chunks in one item that
                # each open a list both mint "list-1" under the same
                # `item_eid` prefix. Same collision class this task exists to
                # close -- run through the shared `seen_eids` too.
                blocklist_count += 1
                blocklist_level = level
                blocklist_el = etree.SubElement(parent, f"{{{AKN_NS}}}blockList")
                blocklist_el.set(
                    "eId",
                    _unique_quoted_eid(
                        _join(section_prefix, f"list-{blocklist_count}"), seen_eids
                    ),
                )
            item_el = etree.SubElement(blocklist_el, f"{{{AKN_NS}}}item")
            item_el.set(
                "eId", f"{blocklist_el.get('eId')}__item-{len(list(blocklist_el))}"
            )
            num_m = re.match(r'^(\([^)]+\))\s+(.*)', p.text, re.DOTALL)
            if num_m:
                etree.SubElement(item_el, f"{{{AKN_NS}}}num").text = num_m.group(1)
                etree.SubElement(item_el, f"{{{AKN_NS}}}p").text = num_m.group(2)
            else:
                etree.SubElement(item_el, f"{{{AKN_NS}}}p").text = p.text
            current_content = None

        elif p.element_type == ElementType.NOTE:
            blocklist_el = None
            blocklist_level = -1
            parent = stack[-1][2] if stack else container
            note_el = etree.SubElement(
                parent, f"{{{AKN_NS}}}authorialNote", placement="end"
            )
            content_el = etree.SubElement(note_el, f"{{{AKN_NS}}}content")
            _emit_p_inline(etree.SubElement(content_el, f"{{{AKN_NS}}}p"), p)
            # Reset so prose following the note opens a fresh <content> AFTER it
            # in document order. The body loop omits this reset (same class as
            # the P1 note's §6 PARAGRAPH/SUBPARAGRAPH finding); without it the
            # trailing prose is appended back into the <content> opened before
            # the note and renders above it.
            current_content = None

        elif p.element_type in {ElementType.EXAMPLE, ElementType.PENALTY}:
            blocklist_el = None
            blocklist_level = -1
            parent = stack[-1][2] if stack else container
            name = "example" if p.element_type == ElementType.EXAMPLE else "penalty"
            wrap_el = etree.SubElement(parent, f"{{{AKN_NS}}}hcontainer", name=name)
            content_el = etree.SubElement(wrap_el, f"{{{AKN_NS}}}content")
            _emit_p_inline(etree.SubElement(content_el, f"{{{AKN_NS}}}p"), p)
            current_content = None

        elif p.element_type == ElementType.TABLE:
            blocklist_el = None
            blocklist_level = -1
            parent = stack[-1][2] if stack else container
            table_el = etree.SubElement(parent, f"{{{AKN_NS}}}table")
            for row in p.table_rows:
                tr_el = etree.SubElement(table_el, f"{{{AKN_NS}}}tr")
                for cell in row:
                    etree.SubElement(tr_el, f"{{{AKN_NS}}}td").text = cell
            current_content = None

        elif p.text:
            blocklist_el = None
            blocklist_level = -1
            parent = stack[-1][2] if stack else container
            if current_content is None or current_content.getparent() is not parent:
                current_content = etree.SubElement(parent, f"{{{AKN_NS}}}content")
            _emit_p_inline(etree.SubElement(current_content, f"{{{AKN_NS}}}p"), p)


def _build_item_body(
    item_el: etree._Element,
    item_eid: str,
    body: list[ParsedParagraph | _QuotedSpan],
    seen_eids: set[str],
) -> None:
    """Emit an amendment item's instruction prose and its quoted provisions.

    `seen_eids` (Task 13) is threaded into every `_build_quoted_content` call
    below -- one item can make several such calls (a chunk before a span, the
    span's own inner content, a chunk after it, ...), and without a set shared
    across all of them two calls sharing the same `item_eid` prefix (or two
    quoted spans that each restart a nested item's own numbering) can mint the
    identical structural `@eId` twice.
    """
    qs_idx = 0
    chunk: list[ParsedParagraph] = []
    for entry in body:
        if isinstance(entry, _QuotedSpan):
            if chunk:
                _build_quoted_content(item_el, item_eid, chunk, seen_eids)
                chunk = []
            qs_idx += 1
            qs_eid = f"{item_eid}__qstr-{qs_idx}"
            qs_el = etree.SubElement(
                item_el, f"{{{AKN_NS}}}quotedStructure", eId=qs_eid
            )
            qs_el.set("startQuote", "“")
            qs_el.set("endQuote", "”")
            qs_el.set("from", "#")
            qs_el.set("to", "#")
            _build_quoted_content(qs_el, qs_eid, entry.inner_paras, seen_eids)
        else:
            chunk.append(entry)
    if chunk:
        _build_quoted_content(item_el, item_eid, chunk, seen_eids)


def inject_note_refs(root: etree._Element) -> int:
    """Inject <noteRef> elements in <p> text where [note N] markers appear.

    Returns count of <noteRef> elements injected.
    """
    count = 0
    for p_el in root.iter(f"{{{AKN_NS}}}p"):
        text = p_el.text
        if not text or len(list(p_el)) > 0:
            continue
        matches = list(_NOTE_REF_RE.finditer(text))
        if not matches:
            continue
        p_el.text = None
        prev_el: etree._Element | None = None
        cursor = 0
        for m in matches:
            marker = m.group(1)
            pre = text[cursor:m.start()]
            ref_el = etree.SubElement(p_el, f"{{{AKN_NS}}}noteRef")
            ref_el.set("href", f"#note-{marker}")
            ref_el.set("marker", marker)
            # <noteRef> is self-closing — display value carried by marker attribute, not text
            if prev_el is None:
                p_el.text = pre or None
            else:
                prev_el.tail = pre or None
            prev_el = ref_el
            cursor = m.end()
            count += 1
        if prev_el is not None:
            prev_el.tail = text[cursor:] or None
    return count


def _emit_p_inline(p_el: etree._Element, p: "ParsedParagraph") -> None:
    """Emit p.text or inline children into p_el, preserving run-level formatting.

    If p.spans is empty or all spans are unformatted, falls back to p_el.text = p.text
    (same behaviour as before v0.6.0). Otherwise emits <b>, <i>, <sup>, <sub> children.
    Bold+italic is rendered as <b><i>text</i></b>.

    Every newly created child is given tail = "" (not left at lxml's default
    None), even when the immediately following span is itself formatted and
    so has no plain-text separator to write there. Two consecutive DOCX runs
    with identical formatting (e.g. split only by an intervening
    <w:bookmarkStart>/<w:bookmarkEnd>, or an rsid boundary from an old
    revision -- no real whitespace in the source) otherwise produce two
    sibling elements with tail=None; lxml's pretty-print serializer (used for
    the persisted corpus/xml/*.xml output, see corpus.py) then fills that
    None tail with newline+indent whitespace, which downstream
    whitespace-normalisation collapses into a spurious literal space --
    corrupting a contiguous word into two tokens (confirmed real cases, Task
    1 triage 2026-09-08, wp_garble Group C, 819 records / 62% of all
    wp_garble: "Excise" -> "E xcise", "sunsetting" -> "sunset ting"). An
    explicit "" tail is inert either way (a following plain span still
    overwrites it via `(prev.tail or "") + span.text`) but blocks
    pretty-print from treating it as unset.
    """
    if not p.spans or not any(
        s.bold or s.italic or s.superscript or s.subscript for s in p.spans
    ):
        p_el.text = p.text
        return

    prev: etree._Element | None = None
    for span in p.spans:
        if not span.text:
            continue
        if span.bold or span.italic or span.superscript or span.subscript:
            if span.bold and span.italic:
                outer = etree.SubElement(p_el, f"{{{AKN_NS}}}b")
                outer.tail = ""
                child = etree.SubElement(outer, f"{{{AKN_NS}}}i")
                child.text = span.text
                prev = outer
            elif span.bold:
                child = etree.SubElement(p_el, f"{{{AKN_NS}}}b")
                child.text = span.text
                child.tail = ""
                prev = child
            elif span.italic:
                child = etree.SubElement(p_el, f"{{{AKN_NS}}}i")
                child.text = span.text
                child.tail = ""
                prev = child
            elif span.superscript:
                child = etree.SubElement(p_el, f"{{{AKN_NS}}}sup")
                child.text = span.text
                child.tail = ""
                prev = child
            else:  # subscript
                child = etree.SubElement(p_el, f"{{{AKN_NS}}}sub")
                child.text = span.text
                child.tail = ""
                prev = child
        else:
            # Plain span — append as tail of last element, or text of p_el
            if prev is None:
                p_el.text = (p_el.text or "") + span.text
            else:
                prev.tail = (prev.tail or "") + span.text


def _resolve_para_ambiguity(
    p: ParsedParagraph,
    stack: list[tuple[ElementType, str, etree._Element]],
) -> ParsedParagraph:
    """Reclassify PARAGRAPH->SUBPARAGRAPH when number is all roman chars and an open PARAGRAPH is on the stack.

    Only reclassify if the open PARAGRAPH is a container (no inline content emitted yet).
    If the open PARAGRAPH has a <content> child it is a leaf node, not a parent.
    """
    if p.element_type != ElementType.PARAGRAPH:
        return p
    if not set(p.number.lower()).issubset(_ROMAN_CHARS):
        return p
    if stack and stack[-1][0] == ElementType.PARAGRAPH:
        open_para_elem = stack[-1][2]
        # If the open paragraph already has a <content> child, it's a leaf — (l) is a sibling
        has_content = any(
            child.tag == f"{{{AKN_NS}}}content" for child in open_para_elem
        )
        if not has_content:
            return replace(p, element_type=ElementType.SUBPARAGRAPH)
    return p


def _is_schedule_heading(p: ParsedParagraph) -> bool:
    """True if p is an actual schedule heading, not body prose that happens to start with
    "Schedule N" (e.g. a cross-reference like "Schedule 1 to the Taxation Administration Act
    1953 contains provisions relating to..."). Confirmed live across Privacy Act, Fair Work
    Act, TG(MD)R 2002, and Corporations Act: genuine schedule headings are always styled
    "ActHead N"; false-positive body prose is styled "subsection", "Definition", etc.
    """
    return (
        p.element_type == ElementType.BODY
        and p.raw_style.startswith("ActHead")
        and bool(_SCHEDULE_RE.match(p.text))
    )


def _split_stream(
    paragraphs: list[ParsedParagraph],
) -> tuple[list[ParsedParagraph], list[ParsedParagraph], list[list[ParsedParagraph]]]:
    """Return (preface_paras, body_paras, list_of_schedule_para_groups).

    Paragraphs are grouped by volume_index (the DOCX volume of origin, set
    by the CLI's volume loop; `groupby` therefore requires the input stream
    to be volume-contiguous, which that loop guarantees by construction).

    A schedule heading found before any body content has appeared does NOT
    permanently flip classification into schedule mode -- the search for a
    schedule heading restarts in the next volume. This handles the
    schedule-first shape where a Regulation's schedules precede its body
    across a volume boundary (e.g. Superannuation Industry (Supervision)
    Regulations 1994, whose volume 1 is entirely Schedule content and
    volume 2 the real body).

    Once body content HAS been seen AND a schedule cut point has been
    crossed, the classification is one-directional: every remaining
    paragraph, in this and every later volume, is schedule content. Those
    later volumes are not re-searched for a schedule heading -- they
    continue the still-open schedule group. This handles the common shape
    where a body-first Act's schedules begin partway through one volume
    and run on into the next with no repeated "Schedule N" heading at that
    volume's start (e.g. Customs Tariff Act 1995, whose later volumes are
    pure Schedule 3 continuation). A genuine new schedule heading anywhere
    in those later volumes still starts a new schedule group.

    A volume that ends in body mode (no schedule heading found in it at
    all) does not trigger that carry-over -- the next volume is searched
    afresh. Otherwise a body-first Act whose body merely spans several
    volumes before its schedules begin, or that has no schedules at all
    (e.g. Income Tax Assessment Act 1997), would have every volume after
    the first swallowed into a schedule.

    For a single-volume Act (every paragraph defaults to volume_index=0)
    this groups into exactly one group. Output is identical to the
    pre-volume-scoping behaviour for every Act in the current corpus; it is
    not identical in general, because the volume-0 preface cut also ends
    the preface at a leading schedule heading, so a single-volume Act whose
    preface region contains an `_is_schedule_heading()` match before its
    first `_STRUCTURAL` element would classify differently.

    The preface cut only ever runs against the first volume's own slice --
    a preface only makes sense at the very start of an Act, never partway
    through a later volume.
    """
    volumes: list[list[ParsedParagraph]] = [
        list(group) for _, group in groupby(paragraphs, key=lambda p: p.volume_index)
    ]

    preface: list[ParsedParagraph] = []
    body: list[ParsedParagraph] = []
    schedules: list[list[ParsedParagraph]] = []

    # body_seen: has any body content been emitted yet, in any volume?
    # in_schedule: did the volume just processed END in schedule mode?
    # Both are needed. body_seen alone would treat every volume after the
    # first as schedule continuation for a body-first Act whose body simply
    # spans several volumes before its schedules begin (or that has no
    # schedules at all, e.g. Income Tax Assessment Act 1997).
    body_seen = False
    in_schedule = False
    current: list[ParsedParagraph] = []

    for vol_num, volume_paragraphs in enumerate(volumes):
        if vol_num == 0:
            # Preface ends at the first structural element or first schedule, whichever is first
            first_structural = next(
                (i for i, p in enumerate(volume_paragraphs) if p.element_type in _STRUCTURAL),
                len(volume_paragraphs),
            )
            first_schedule = next(
                (i for i, p in enumerate(volume_paragraphs) if _is_schedule_heading(p)),
                len(volume_paragraphs),
            )
            preface_end = min(first_structural, first_schedule)
            preface = volume_paragraphs[:preface_end]
            rest = volume_paragraphs[preface_end:]
        else:
            rest = volume_paragraphs

        if in_schedule and body_seen:
            # Body has already appeared AND the previous volume ended in
            # schedule mode, so this whole volume continues the currently-open
            # schedule group -- unless a genuine schedule heading below starts
            # a new one. No fresh search: a later volume of a body-first Act
            # routinely carries schedule content with no repeated heading.
            schedule_paras = rest
        else:
            # Either no body content anywhere yet (schedule-first Act, whose
            # later volume may still hold the real body), or the previous
            # volume ended in body mode. Search this volume for the cut point.
            schedule_start = next(
                (i for i, p in enumerate(rest) if _is_schedule_heading(p)),
                len(rest),
            )
            new_body = rest[:schedule_start]
            if new_body:
                body_seen = True
            body.extend(new_body)
            schedule_paras = rest[schedule_start:]
            in_schedule = bool(schedule_paras)

        for p in schedule_paras:
            if _is_schedule_heading(p):
                if current:
                    schedules.append(current)
                current = [p]
            else:
                current.append(p)

    if current:
        schedules.append(current)

    return preface, body, schedules


def _build_preface(
    preface_paras: list[ParsedParagraph],
    meta: ActMetadata | None = None,
) -> tuple[etree._Element | None, etree._Element | None]:
    """Returns (preface_el, preamble_el). preamble_el must be inserted as a sibling of preface_el under <act>."""
    if not preface_paras and (meta is None or not meta.long_title):
        return None, None
    preface_el = etree.Element(f"{{{AKN_NS}}}preface")

    # Emit <longTitle> as first child if available
    if meta and meta.long_title:
        lt_el = etree.SubElement(preface_el, f"{{{AKN_NS}}}longTitle")
        p_el = etree.SubElement(lt_el, f"{{{AKN_NS}}}p")
        p_el.text = meta.long_title

    toc_el: etree._Element | None = None
    preamble_el: etree._Element | None = None
    recitals_el: etree._Element | None = None

    for p in preface_paras:
        if p.raw_style == _TOC_HEADING_STYLE:
            toc_el = etree.SubElement(preface_el, f"{{{AKN_NS}}}toc")
        elif p.raw_style in _TOC_ITEM_STYLES:
            parent = toc_el if toc_el is not None else preface_el
            item = etree.SubElement(parent, f"{{{AKN_NS}}}tocItem")
            item.text = p.text
        elif _ENACTING_RE.search(p.text or ""):
            formula_el = etree.SubElement(preface_el, f"{{{AKN_NS}}}formula")
            formula_el.set("name", "enacting")
            p_el = etree.SubElement(formula_el, f"{{{AKN_NS}}}p")
            _emit_p_inline(p_el, p)
        elif _WHEREAS_RE.match(p.text or ""):
            # <preamble> is a sibling of <preface> under <act> — build separately
            if preamble_el is None:
                preamble_el = etree.Element(f"{{{AKN_NS}}}preamble")
                recitals_el = etree.SubElement(preamble_el, f"{{{AKN_NS}}}recitals")
            recital_el = etree.SubElement(recitals_el, f"{{{AKN_NS}}}recital")
            p_el = etree.SubElement(recital_el, f"{{{AKN_NS}}}p")
            _emit_p_inline(p_el, p)
        else:
            p_el = etree.SubElement(preface_el, f"{{{AKN_NS}}}p")
            _emit_p_inline(p_el, p)

    return preface_el, preamble_el


def _build_schedule_content(
    hcontainer: etree._Element,
    schedule_eid: str,
    paragraphs: list[ParsedParagraph],
) -> int:
    """Build clause hierarchy inside a schedule hcontainer. Returns count of top-level clauses.

    Since §3 B4 the stream is segmented first (`_preprocess_schedule_group`), so
    amendment-instruction items and quoted replacement provisions no longer share
    the flat `schedule-N__clause-*` namespace, and genuine Part/Division/
    amended-Act boundaries carry a grouping wrapper. Every eId minted here is
    rooted at `schedule_eid`; the body Part/Division/section eId generator is not
    reached from this function.
    """
    stream = _preprocess_schedule_group(paragraphs)

    clause_count = 0
    clause_idx = 0
    current_clause: etree._Element | None = None
    current_subclause: etree._Element | None = None  # dotted subclause (e.g. 7.1) from SECTION
    current_para: etree._Element | None = None
    # Mirrors the body builder's `current_content` pointer: prose accumulates into
    # this <content> until a structural sibling (clause/subclause boundary, table)
    # forces a fresh one. Preserves document order when prose follows a <table>.
    current_content: etree._Element | None = None

    # Schedule-scoped grouping wrappers (the B1 increment folded into B4).
    group_stack: list[tuple[ElementType, etree._Element]] = []
    amdact_el: etree._Element | None = None
    amdact_idx = 0
    item_idx = 0
    seen_eids: set[str] = set()
    # Task 13: separate from `seen_eids` above (which only tracks this
    # schedule's own grouping/item/amdact wrapper eIds) -- shared across every
    # `_build_item_body` / `_build_quoted_content` call for this schedule, so
    # a structural collision inside quoted content gets an occurrence suffix.
    quoted_seen_eids: set[str] = set()

    def _unique(eid: str) -> str:
        if eid not in seen_eids:
            seen_eids.add(eid)
            return eid
        n = 2
        while f"{eid}-{n}" in seen_eids:
            n += 1
        seen_eids.add(f"{eid}-{n}")
        return f"{eid}-{n}"

    def _container() -> etree._Element:
        if amdact_el is not None:
            return amdact_el
        return group_stack[-1][1] if group_stack else hcontainer

    def _container_eid() -> str:
        return _container().get("eId", schedule_eid)

    def _content_for(parent: etree._Element) -> etree._Element:
        nonlocal current_content
        # Reuse the running pointer only when it already sits under the requested
        # parent. Two call sites pass different parents (BODY prose resolves to the
        # subclause; the NOTE/EXAMPLE/PENALTY catch-all resolves to the clause), so
        # without the parent-affinity check a catch-all <content> under the clause
        # would swallow the next subclause-scoped prose paragraph and strip its eId
        # association. The `is None` arm still lets fresh prose after a <table> open
        # a new <content> in document order.
        if current_content is None or current_content.getparent() is not parent:
            current_content = etree.SubElement(parent, f"{{{AKN_NS}}}content")
        return current_content

    for entry in stream:
        # --- amendment-instruction item (§3 B4 item 2) ----------------------
        if isinstance(entry, _ScheduleItem):
            parent = _container()
            item_idx += 1
            item_eid = _unique(f"{_container_eid()}__item-{item_idx}")
            item_el = etree.SubElement(
                parent, f"{{{AKN_NS}}}hcontainer", name="item", eId=item_eid
            )
            if entry.num:
                etree.SubElement(item_el, f"{{{AKN_NS}}}num").text = entry.num
            if entry.heading:
                etree.SubElement(item_el, f"{{{AKN_NS}}}heading").text = entry.heading
            _build_item_body(item_el, item_eid, entry.body, quoted_seen_eids)
            current_clause = None
            current_subclause = None
            current_para = None
            current_content = None
            continue

        p = entry

        # --- grouping wrappers (the B1 increment) --------------------------
        if p.element_type in _SCHEDULE_GROUPING:
            target_depth = _DEPTH[p.element_type]
            while group_stack and _DEPTH[group_stack[-1][0]] >= target_depth:
                group_stack.pop()
            parent = group_stack[-1][1] if group_stack else hcontainer
            eid = _unique(
                f"{parent.get('eId', schedule_eid)}__"
                f"{make_eid(p.element_type.value, p.number)}"
            )
            group_el = etree.SubElement(
                parent, f"{{{AKN_NS}}}hcontainer",
                name=_AKN_TAG[p.element_type], eId=eid,
            )
            etree.SubElement(group_el, f"{{{AKN_NS}}}num").text = p.number
            if p.heading:
                etree.SubElement(group_el, f"{{{AKN_NS}}}heading").text = p.heading
            group_stack.append((p.element_type, group_el))
            amdact_el = None
            item_idx = 0
            current_clause = None
            current_subclause = None
            current_para = None
            current_content = None
            continue

        if _is_amended_act_heading(p):
            parent = group_stack[-1][1] if group_stack else hcontainer
            amdact_idx += 1
            eid = _unique(f"{parent.get('eId', schedule_eid)}__amdact-{amdact_idx}")
            amdact_el = etree.SubElement(
                parent, f"{{{AKN_NS}}}hcontainer", name="amendedAct", eId=eid
            )
            etree.SubElement(amdact_el, f"{{{AKN_NS}}}heading").text = p.text.strip()
            item_idx = 0
            current_clause = None
            current_subclause = None
            current_para = None
            current_content = None
            continue

        if p.element_type == ElementType.BODY and p.text:
            text = p.text.strip()

            m = _APP_CLAUSE_RE.match(text)
            if m:
                clause_idx += 1
                clause_count += 1
                num_str = m.group(1)
                heading_str = (m.group(2) or "").strip()
                # Clause eIds are deliberately NOT run through `_unique`: B4 is a
                # structural fix, not B2's identifier-uniquifier, so any residual
                # clause collision must stay visible in the eId diff.
                eid = f"{_container_eid()}__clause-{clause_idx}"
                current_clause = etree.SubElement(
                    _container(), f"{{{AKN_NS}}}hcontainer", name="clause", eId=eid
                )
                etree.SubElement(current_clause, f"{{{AKN_NS}}}num").text = num_str
                if heading_str:
                    etree.SubElement(current_clause, f"{{{AKN_NS}}}heading").text = heading_str
                current_subclause = None
                current_para = None
                current_content = None
                continue

            m = _SUBCLAUSE_RE.match(text)
            if m:
                num_str = m.group(1)
                content_text = m.group(2).strip()
                parent = current_clause if current_clause is not None else _container()
                parent_eid = parent.get("eId", schedule_eid)
                eid = f"{parent_eid}__subclause-{num_str.replace('.', '-')}"
                current_subclause = etree.SubElement(
                    parent, f"{{{AKN_NS}}}hcontainer", name="subclause", eId=eid
                )
                etree.SubElement(current_subclause, f"{{{AKN_NS}}}num").text = num_str
                current_para = None
                current_content = None
                if content_text:
                    current_content = etree.SubElement(current_subclause, f"{{{AKN_NS}}}content")
                    etree.SubElement(current_content, f"{{{AKN_NS}}}p").text = content_text
                continue

            m = _CLAUSE_RE.match(text)
            if m:
                num_str = m.group(1)
                heading_str = m.group(2).strip()

                # Guard: skip clause fabrication if this looks like a date-leading line
                # ("30 June 2000 rate, ..." or "June 2000 rate" heading)
                if _DATE_PREFIX_RE.match(heading_str) or _DATE_PATTERN_RE.match(text):
                    # Fall through to plain body text handling
                    # (reset clause state so prose goes to schedule content, not current clause)
                    current_clause = None
                    current_subclause = None
                    current_para = None
                    current_content = None
                else:
                    clause_idx += 1
                    clause_count += 1
                    eid = f"{_container_eid()}__clause-{num_str}"
                    current_clause = etree.SubElement(
                        _container(), f"{{{AKN_NS}}}hcontainer", name="clause", eId=eid
                    )
                    etree.SubElement(current_clause, f"{{{AKN_NS}}}num").text = num_str
                    etree.SubElement(current_clause, f"{{{AKN_NS}}}heading").text = heading_str
                    current_subclause = None
                    current_para = None
                    current_content = None
                    continue

            # Plain body text
            parent = current_subclause if current_subclause is not None else (current_clause if current_clause is not None else _container())
            content_el = _content_for(parent)
            _p_el = etree.SubElement(content_el, f"{{{AKN_NS}}}p")
            _emit_p_inline(_p_el, p)

        elif p.element_type == ElementType.PARAGRAPH:
            parent = current_subclause if current_subclause is not None else (current_clause if current_clause is not None else _container())
            parent_eid = parent.get("eId", schedule_eid)
            eid = f"{parent_eid}__para-{p.number}"
            current_para = etree.SubElement(parent, f"{{{AKN_NS}}}paragraph", eId=eid)
            etree.SubElement(current_para, f"{{{AKN_NS}}}num").text = p.number
            if p.text:
                content_el = etree.SubElement(current_para, f"{{{AKN_NS}}}content")
                _p_el = etree.SubElement(content_el, f"{{{AKN_NS}}}p")
                _emit_p_inline(_p_el, p)
            current_content = None

        elif p.element_type == ElementType.SECTION and p.number:
            # SECTION-typed paragraphs inside a schedule (e.g. TG Regs Essential Principles).
            # Dotted numbers (7.1, 7.2) are subclauses; plain numbers (7, 8) are top-level clauses.
            num_str = p.number
            heading_str = p.heading or ""
            if "." in num_str:
                parent = current_clause if current_clause is not None else _container()
                parent_eid = parent.get("eId", schedule_eid)
                eid = f"{parent_eid}__subclause-{num_str.replace('.', '-')}"
                current_subclause = etree.SubElement(
                    parent, f"{{{AKN_NS}}}hcontainer", name="subclause", eId=eid
                )
                etree.SubElement(current_subclause, f"{{{AKN_NS}}}num").text = num_str
                if heading_str:
                    etree.SubElement(current_subclause, f"{{{AKN_NS}}}heading").text = heading_str
                current_para = None
                current_content = None
            else:
                clause_idx += 1
                clause_count += 1
                eid = f"{_container_eid()}__clause-{num_str}"
                current_clause = etree.SubElement(
                    _container(), f"{{{AKN_NS}}}hcontainer", name="clause", eId=eid
                )
                etree.SubElement(current_clause, f"{{{AKN_NS}}}num").text = num_str
                if heading_str:
                    etree.SubElement(current_clause, f"{{{AKN_NS}}}heading").text = heading_str
                current_subclause = None
                current_para = None
                current_content = None

        elif p.element_type == ElementType.SUBSECTION and p.number:
            # Numbered subclauses (1, 2, 3) within a schedule clause or dotted subclause.
            # Always sibling under the nearest dotted subclause or top-level clause — never
            # nested inside a previous numbered subclause.
            num_str = p.number
            parent = current_subclause if current_subclause is not None else (
                current_clause if current_clause is not None else _container()
            )
            parent_eid = parent.get("eId", schedule_eid)
            eid = f"{parent_eid}__subclause-{num_str}"
            sub_el = etree.SubElement(
                parent, f"{{{AKN_NS}}}hcontainer", name="subclause", eId=eid
            )
            etree.SubElement(sub_el, f"{{{AKN_NS}}}num").text = num_str
            if p.text:
                content_el = etree.SubElement(sub_el, f"{{{AKN_NS}}}content")
                _p_el = etree.SubElement(content_el, f"{{{AKN_NS}}}p")
                _emit_p_inline(_p_el, p)
            # Do NOT update current_subclause — numbered subclauses are siblings, not a new nesting level
            current_para = None
            current_content = None

        elif p.element_type == ElementType.SUBPARAGRAPH:
            if current_para is not None:
                parent = current_para
            elif current_subclause is not None:
                parent = current_subclause
            elif current_clause is not None:
                parent = current_clause
            else:
                parent = _container()
            parent_eid = parent.get("eId", schedule_eid)
            eid = f"{parent_eid}__subpara-{p.number}"
            subpara_el = etree.SubElement(parent, f"{{{AKN_NS}}}subparagraph", eId=eid)
            etree.SubElement(subpara_el, f"{{{AKN_NS}}}num").text = p.number
            if p.text:
                content_el = etree.SubElement(subpara_el, f"{{{AKN_NS}}}content")
                _p_el = etree.SubElement(content_el, f"{{{AKN_NS}}}p")
                _emit_p_inline(_p_el, p)
            current_content = None

        elif p.element_type == ElementType.TABLE:
            # Schedule rate/classification/repeal tables (Word <w:tbl>). Mirrors the
            # body-path TABLE handler, emitted directly under the nearest clause
            # context. Header-row position is inconsistent across schedule tables
            # (multi-row banners, blank spacer rows), so no row is promoted to
            # <th> — every row is a <td>, avoiding a false header signal.
            parent = current_subclause if current_subclause is not None else (
                current_clause if current_clause is not None else _container()
            )
            table_el = etree.SubElement(parent, f"{{{AKN_NS}}}table")
            for row in p.table_rows:
                tr_el = etree.SubElement(table_el, f"{{{AKN_NS}}}tr")
                for cell in row:
                    etree.SubElement(tr_el, f"{{{AKN_NS}}}td").text = cell
            current_para = None
            # Reset so any prose after the table opens a fresh <content> that
            # sits AFTER the <table> in document order (matches body builder).
            current_content = None

        elif p.text:
            # NOTE/EXAMPLE/PENALTY inside schedule — emit as plain content
            parent = current_clause if current_clause is not None else _container()
            content_el = _content_for(parent)
            _p_el = etree.SubElement(content_el, f"{{{AKN_NS}}}p")
            _emit_p_inline(_p_el, p)

    return clause_count


def _count_schedule_clauses(schedule_groups: list[list[ParsedParagraph]]) -> int:
    """Count top-level clause hcontainers across all schedule groups (for ParseReport).

    Runs the same B4 segmentation the builder runs, so amendment-instruction
    items, quoted replacement provisions and TOC lines are excluded — this is the
    count of genuine schedule clauses, not of everything that starts with a digit.
    """
    count = 0
    for group in schedule_groups:
        for entry in _preprocess_schedule_group(group[1:]):  # skip schedule heading
            if isinstance(entry, _ScheduleItem):
                continue
            p = entry
            if p.element_type == ElementType.BODY and p.text:
                text = p.text.strip()
                if _APP_CLAUSE_RE.match(text):
                    count += 1
                elif not _SUBCLAUSE_RE.match(text):
                    m = _CLAUSE_RE.match(text)
                    if m and not (
                        _DATE_PREFIX_RE.match(m.group(2).strip())
                        or _DATE_PATTERN_RE.match(text)
                    ):
                        count += 1
            elif p.element_type == ElementType.SECTION and p.number and "." not in p.number:
                count += 1
    return count


def _build_attachments(
    schedule_groups: list[list[ParsedParagraph]],
) -> tuple[etree._Element | None, int]:
    """Build attachments element. Returns (attachments_el | None, total_clause_count)."""
    if not schedule_groups:
        return None, 0
    total_clauses = 0
    attachments_el = etree.Element(f"{{{AKN_NS}}}attachments")
    for idx, group in enumerate(schedule_groups, start=1):
        attachment_el = etree.SubElement(attachments_el, f"{{{AKN_NS}}}attachment")
        schedule_eid = f"schedule-{idx}"
        hcontainer = etree.SubElement(
            attachment_el,
            f"{{{AKN_NS}}}hcontainer",
            name="schedule",
            eId=schedule_eid,
        )
        if group:
            heading_text = group[0].text
            m = _SCHEDULE_RE.match(heading_text)
            if m and m.group(1):
                etree.SubElement(hcontainer, f"{{{AKN_NS}}}num").text = m.group(1)
            heading_val = heading_text[m.end():].lstrip("—–- ") if m else heading_text
            h_el = etree.SubElement(hcontainer, f"{{{AKN_NS}}}heading")
            h_el.text = heading_val or heading_text
        clauses = _build_schedule_content(hcontainer, schedule_eid, group[1:] if group else [])
        total_clauses += clauses
    return attachments_el, total_clauses


def inject_lifecycle(root: etree._Element, meta: ActMetadata, events: list[AmendmentEvent]) -> None:
    """Insert <lifecycle> into <meta> after <identification>."""
    ns = {"akn": AKN_NS}
    meta_el = root.find(".//akn:meta", ns)
    identification_el = meta_el.find(f"{{{AKN_NS}}}identification")
    insert_idx = list(meta_el).index(identification_el) + 1

    lifecycle_el = etree.Element(f"{{{AKN_NS}}}lifecycle")
    lifecycle_el.set("source", "#parliament")

    # Creation event (always present)
    creation = etree.SubElement(lifecycle_el, f"{{{AKN_NS}}}eventRef")
    creation.set("date", f"{meta.year}-01-01")
    creation.set("type", "generation")
    creation.set("eId", "evt-creation")
    creation.set("source", f"#{meta.safe_name}")

    # Amendment events (one per unique amending Act, ordered by act_year/act_number)
    seen: set[tuple[int, int]] = set()
    amd_idx = 0
    for event in sorted(events, key=lambda e: (e.act_year, e.act_number)):
        key = (event.act_number, event.act_year)
        if key in seen:
            continue
        seen.add(key)
        amd_idx += 1
        amd_uri = f"/akn/au/act/{event.act_year}/{event.act_number}"
        evt = etree.SubElement(lifecycle_el, f"{{{AKN_NS}}}eventRef")
        evt.set("type", "amendment")
        evt.set("eId", f"evt-amd-{amd_idx}")
        evt.set("source", amd_uri)

    meta_el.insert(insert_idx, lifecycle_el)


def inject_temporal_data(root: etree._Element, events: list[AmendmentEvent]) -> None:
    """Insert <temporalData> into <meta> after <lifecycle>."""
    ns = {"akn": AKN_NS}
    meta_el = root.find(".//akn:meta", ns)
    lifecycle_el = meta_el.find(f"{{{AKN_NS}}}lifecycle")
    if lifecycle_el is None:
        return
    insert_idx = list(meta_el).index(lifecycle_el) + 1

    td_el = etree.Element(f"{{{AKN_NS}}}temporalData")
    td_el.set("source", "#parliament")

    tg_el = etree.SubElement(td_el, f"{{{AKN_NS}}}temporalGroup")
    tg_el.set("eId", "tg-1")

    # Minimal: open-ended interval from creation to present
    ti_el = etree.SubElement(tg_el, f"{{{AKN_NS}}}timeInterval")
    ti_el.set("start", "#evt-creation")
    # No end attribute = open-ended (current version)

    meta_el.insert(insert_idx, td_el)


def _collect_eids(root: etree._Element) -> set[str]:
    eids: set[str] = set()
    for el in root.iter():
        eid = el.get("eId")
        if eid:
            eids.add(eid)
    return eids


_SECTION_PROVISION = re.compile(
    r'^s\.?\s*(?P<num>\w[\w.]*)',
    re.IGNORECASE,
)


def _resolve_provision_eid(provision: str, known_eids: set[str]) -> str | None:
    """Attempt to resolve a provision string like 's 6' to an AKN eId like 'sec-6'."""
    m = _SECTION_PROVISION.match(provision)
    if m:
        candidate = f"sec-{m.group('num')}"
        if candidate in known_eids:
            return candidate
        # Try case variants
        candidate_lower = candidate.lower()
        for eid in known_eids:
            if eid.lower() == candidate_lower:
                return eid
    return None


def inject_passive_mods(
    root: etree._Element,
    events: list[AmendmentEvent],
    report: ParseReport | None = None,
) -> None:
    """Insert <analysis><passiveModifications> into <meta>."""
    ns = {"akn": AKN_NS}
    meta_el = root.find(".//akn:meta", ns)
    known_eids = _collect_eids(root)

    # Build a map: (act_number, act_year) → evt-amd-N eId from <lifecycle>
    lifecycle_el = meta_el.find(f"{{{AKN_NS}}}lifecycle")
    evt_map: dict[tuple[int, int], str] = {}
    if lifecycle_el is not None:
        for evt in lifecycle_el:
            eid = evt.get("eId", "")
            if eid.startswith("evt-amd-"):
                src = evt.get("source", "")
                # source = "/akn/au/act/YEAR/NUMBER"
                parts = src.rstrip("/").rsplit("/", 2)
                if len(parts) == 3:
                    try:
                        year, num = int(parts[-2]), int(parts[-1])
                        evt_map[(num, year)] = eid
                    except ValueError:
                        pass

    analysis_el = etree.Element(f"{{{AKN_NS}}}analysis")
    analysis_el.set("source", "#lex-au")
    passive_el = etree.SubElement(analysis_el, f"{{{AKN_NS}}}passiveModifications")

    mod_idx = 0
    resolved = 0
    unresolved = 0

    _EFFECT_TO_TYPE = {
        "am": "substitution",
        "ad": "insertion",
        "rep": "repeal",
        "rs": "substitution",
    }

    for event in events:
        if not event.applied:
            continue
        dest_eid = _resolve_provision_eid(event.provision, known_eids)
        evt_eid = evt_map.get((event.act_number, event.act_year))

        if dest_eid is None or evt_eid is None:
            unresolved += 1
            continue

        mod_idx += 1
        mod_type = _EFFECT_TO_TYPE.get(event.effect, "amendment")
        mod_el = etree.SubElement(passive_el, f"{{{AKN_NS}}}textualMod")
        mod_el.set("type", mod_type)
        mod_el.set("eId", f"mod-{mod_idx}")
        etree.SubElement(mod_el, f"{{{AKN_NS}}}source").set("href", f"#{evt_eid}")
        etree.SubElement(mod_el, f"{{{AKN_NS}}}destination").set("href", f"#{dest_eid}")
        resolved += 1

    if report:
        report.mods_resolved = resolved
        report.mods_unresolved = unresolved

    if mod_idx > 0:
        td_el = meta_el.find(f"{{{AKN_NS}}}temporalData")
        # Insert <analysis> before <temporalData> per AKN 3.0 XSD
        insert_idx = list(meta_el).index(td_el) if td_el is not None else len(list(meta_el))
        meta_el.insert(insert_idx, analysis_el)


class AknBuilder:
    def __init__(
        self, meta: ActMetadata, images_out: Path = Path("corpus/images")
    ) -> None:
        self._meta = meta
        self._images_out = Path(images_out)
        self._paragraphs: list[ParsedParagraph] = []
        self._quoted_structures_found: int = 0
        self._quoted_structures_unhandled: int = 0
        self._figures_found: int = 0
        self._figures_raster: int = 0
        self._figures_converted: int = 0
        self._figures_placeholder: int = 0

    def add(self, paragraph: ParsedParagraph) -> None:
        if paragraph.element_type != ElementType.SKIP:
            self._paragraphs.append(paragraph)

    def build(self) -> tuple[etree._Element, ValidationResult]:
        # build() is public and may run before build_with_report() (which calls
        # it): reset the figure counters so a second pass does not double-count
        # and trip the spec-mandated lockstep assert below.
        self._figures_found = 0
        self._figures_raster = 0
        self._figures_converted = 0
        self._figures_placeholder = 0

        preface_paras, body_paras, schedule_groups = _split_stream(self._paragraphs)

        root = self._make_skeleton()
        ns = {"akn": AKN_NS}
        act_el = root.find(".//akn:act", ns)
        body = root.find(".//akn:body", ns)

        # Insert <preface> and optionally <preamble> before <body>
        preface_el, preamble_el = _build_preface(preface_paras, self._meta)
        body_index = list(act_el).index(body)
        if preface_el is not None:
            act_el.insert(body_index, preface_el)
            body_index += 1
        if preamble_el is not None:
            act_el.insert(body_index, preamble_el)

        # Stack entries: (element_type, num, lxml_element)
        stack: list[tuple[ElementType, str, etree._Element]] = []
        current_content: etree._Element | None = None

        # Figure image blobs collected in the body loop, one inner list per
        # FIGURE paragraph, in global document order across every volume.
        # Kept lockstep with self._figures_found and with fig_img_els so the
        # once-per-Act materialise_figures pass below can write a real src.
        fig_blobs: list[list[tuple[str, bytes]]] = []
        fig_img_els: list[etree._Element] = []

        # State for blockList accumulation
        _blocklist_el: etree._Element | None = None
        _blocklist_level: int = -1
        _blocklist_count: int = 0

        def _flush_blocklist(reset_count: bool = False) -> None:
            nonlocal _blocklist_el, _blocklist_level, _blocklist_count
            _blocklist_el = None
            _blocklist_level = -1
            if reset_count:
                _blocklist_count = 0

        def _current_parent(for_type: ElementType) -> tuple[str, etree._Element]:
            """Pop stack until a valid parent exists for for_type; return (eid_prefix, parent_elem)."""
            target_depth = _DEPTH.get(for_type, 99)
            while stack and _DEPTH.get(stack[-1][0], -1) >= target_depth:
                stack.pop()
            prefix = "__".join(make_eid(et.value, num) for et, num, _ in stack) if stack else ""
            parent = stack[-1][2] if stack else body
            return prefix, parent

        # Preprocess body_paras: detect single-provision quoted structures
        processed_body, qs_found, qs_unhandled = _preprocess_quoted_structures(body_paras)
        self._quoted_structures_found += qs_found
        self._quoted_structures_unhandled += qs_unhandled

        for item in processed_body:
            # Handle quoted structure sentinels
            if isinstance(item, _QuotedSpan):
                _flush_blocklist()
                current_content = None
                parent_elem = stack[-1][2] if stack else body
                qs_el = etree.SubElement(
                    parent_elem,
                    f"{{{AKN_NS}}}quotedStructure",
                )
                qs_el.set("startQuote", "“")
                qs_el.set("endQuote", "”")
                qs_el.set("from", "#")
                qs_el.set("to", "#")
                # Build inner content via sub-AknBuilder
                sub = AknBuilder(self._meta, self._images_out)
                for ip in item.inner_paras:
                    sub.add(ip)
                sub_root, _ = sub.build()
                sub_ns = {"akn": AKN_NS}
                sub_body = sub_root.find(".//akn:body", sub_ns)
                if sub_body is not None:
                    for child in list(sub_body):
                        sub_body.remove(child)
                        qs_el.append(child)
                continue

            p = item
            p = _resolve_para_ambiguity(p, stack)
            if p.element_type in _AKN_TAG:
                _flush_blocklist(reset_count=True)
                current_content = None
                prefix, parent = _current_parent(p.element_type)
                leaf_eid = make_eid(p.element_type.value, p.number)
                full_eid = f"{prefix}__{leaf_eid}" if prefix else leaf_eid
                if p.element_type == ElementType.LEVEL4:
                    elem = etree.SubElement(
                        parent, f"{{{AKN_NS}}}hcontainer",
                        name="level4", eId=full_eid,
                    )
                else:
                    tag = _AKN_TAG[p.element_type]
                    elem = etree.SubElement(parent, f"{{{AKN_NS}}}{tag}", eId=full_eid)
                num_el = etree.SubElement(elem, f"{{{AKN_NS}}}num")
                num_el.text = p.number
                if p.heading:
                    h_el = etree.SubElement(elem, f"{{{AKN_NS}}}heading")
                    h_el.text = p.heading
                stack.append((p.element_type, p.number, elem))
                if p.element_type in {ElementType.SUBSECTION, ElementType.PARAGRAPH, ElementType.SUBPARAGRAPH, ElementType.LEVEL4} and p.text:
                    content_el = etree.SubElement(elem, f"{{{AKN_NS}}}content")
                    p_el = etree.SubElement(content_el, f"{{{AKN_NS}}}p")
                    _emit_p_inline(p_el, p)

            elif p.element_type == ElementType.LIST_ITEM:
                level = int(p.number) if p.number.isdigit() else 0
                parent_elem = stack[-1][2] if stack else body
                # Build a full eId prefix from the stack for the section context
                section_eid_prefix = "__".join(
                    make_eid(et.value, num) for et, num, _ in stack
                ) if stack else ""
                if _blocklist_el is None or level != _blocklist_level:
                    _flush_blocklist()
                    _blocklist_count += 1
                    _blocklist_level = level
                    bl_eid = f"{section_eid_prefix}__list-{_blocklist_count}" if section_eid_prefix else f"list-{_blocklist_count}"
                    _blocklist_el = etree.SubElement(parent_elem, f"{{{AKN_NS}}}blockList")
                    _blocklist_el.set("eId", bl_eid)
                item_idx = len(list(_blocklist_el)) + 1
                item_eid = f"{_blocklist_el.get('eId')}__item-{item_idx}"
                item_el = etree.SubElement(_blocklist_el, f"{{{AKN_NS}}}item")
                item_el.set("eId", item_eid)
                num_m = re.match(r'^(\([^)]+\))\s+(.*)', p.text, re.DOTALL)
                if num_m:
                    etree.SubElement(item_el, f"{{{AKN_NS}}}num").text = num_m.group(1)
                    p_el = etree.SubElement(item_el, f"{{{AKN_NS}}}p")
                    p_el.text = num_m.group(2)
                else:
                    p_el = etree.SubElement(item_el, f"{{{AKN_NS}}}p")
                    p_el.text = p.text
                current_content = None

            elif p.element_type == ElementType.BODY and p.text:
                _flush_blocklist()
                # Attach body text to the current section's <content>
                parent_elem = stack[-1][2] if stack else body
                if current_content is None:
                    current_content = etree.SubElement(parent_elem, f"{{{AKN_NS}}}content")
                p_el = etree.SubElement(current_content, f"{{{AKN_NS}}}p")
                _emit_p_inline(p_el, p)

            # NOTE / EXAMPLE / PENALTY / LIST_ITEM below are duplicated, on
            # purpose, by `_build_quoted_content` — the schedule path needs the
            # same shapes but every eId it mints must stay `schedule-*`-rooted,
            # so it cannot share this loop without reaching the body eId
            # generator. The copy has ALREADY DIVERGED: it resets
            # `current_content` at the end of these three branches, which these
            # do not (the P1 note's §6 `current_content` non-reset finding, whose
            # body-path half is still open). Keep the two in sync for any fix of
            # that class — a change here almost always needs the mirror change in
            # `_build_quoted_content`, and vice versa.
            elif p.element_type == ElementType.NOTE:
                _flush_blocklist()
                parent_elem = stack[-1][2] if stack else body
                note_el = etree.SubElement(
                    parent_elem, f"{{{AKN_NS}}}authorialNote",
                    placement="end",
                )
                content_el = etree.SubElement(note_el, f"{{{AKN_NS}}}content")
                _p = etree.SubElement(content_el, f"{{{AKN_NS}}}p")
                _emit_p_inline(_p, p)

            elif p.element_type == ElementType.EXAMPLE:
                _flush_blocklist()
                parent_elem = stack[-1][2] if stack else body
                ex_el = etree.SubElement(
                    parent_elem, f"{{{AKN_NS}}}hcontainer", name="example"
                )
                content_el = etree.SubElement(ex_el, f"{{{AKN_NS}}}content")
                _p = etree.SubElement(content_el, f"{{{AKN_NS}}}p")
                _emit_p_inline(_p, p)

            elif p.element_type == ElementType.PENALTY:
                _flush_blocklist()
                parent_elem = stack[-1][2] if stack else body
                pen_el = etree.SubElement(
                    parent_elem, f"{{{AKN_NS}}}hcontainer", name="penalty"
                )
                content_el = etree.SubElement(pen_el, f"{{{AKN_NS}}}content")
                _p = etree.SubElement(content_el, f"{{{AKN_NS}}}p")
                _emit_p_inline(_p, p)

            elif p.element_type == ElementType.TABLE:
                _flush_blocklist()
                parent_elem = stack[-1][2] if stack else body
                table_el = etree.SubElement(parent_elem, f"{{{AKN_NS}}}table")
                if p.table_rows:
                    header_row, *data_rows = p.table_rows
                    tr_el = etree.SubElement(table_el, f"{{{AKN_NS}}}tr")
                    for cell in header_row:
                        etree.SubElement(tr_el, f"{{{AKN_NS}}}th").text = cell
                    for row in data_rows:
                        tr_el = etree.SubElement(table_el, f"{{{AKN_NS}}}tr")
                        for cell in row:
                            etree.SubElement(tr_el, f"{{{AKN_NS}}}td").text = cell
                current_content = None

            elif p.element_type == ElementType.FIGURE:
                _flush_blocklist()
                parent_elem = stack[-1][2] if stack else body
                self._figures_found += 1
                fig_blobs.append(list(p.image_blobs))
                fig_el = etree.SubElement(parent_elem, f"{{{AKN_NS}}}figure")
                # Provisional placeholder src; overwritten below from the
                # FigureResult unless this FIGURE carried no resolvable image.
                img_src = f"corpus/images/{self._meta.safe_name}-fig-{self._figures_found}.png"
                img_el = etree.SubElement(fig_el, f"{{{AKN_NS}}}img", src=img_src, alt="")
                fig_img_els.append(img_el)
                current_content = None
                # A FIGURE must never swallow its own paragraph's text. The
                # reader splits a mixed text+image <w:p> and clears this field,
                # so in the corpus path p.text is empty here and nothing extra
                # is emitted. This is the boundary guard for any other producer
                # of a FIGURE (a hand-built stream, a future reader): emit the
                # text as a sibling <p> rather than drop an operative provision.
                # It loses the eId the split would have preserved -- that is the
                # point of preferring the split.
                if p.text and p.text.strip():
                    text_el = etree.SubElement(parent_elem, f"{{{AKN_NS}}}p")
                    _emit_p_inline(text_el, p)

        # Materialise figure image blobs once per Act (over every volume's
        # FIGURE paragraphs concatenated in document order) and write the real
        # src + pixel dimensions back into the <img> elements emitted above.
        # The assert is spec-mandated (design §A2 "Wiring"): a desync between
        # the blob list and the figure counter must raise, not slip through.
        assert len(fig_blobs) == self._figures_found == len(fig_img_els)
        fig_results = (
            materialise_figures(
                self._meta.safe_name,
                self._meta.safe_name,
                fig_blobs,
                self._images_out,
            )
            if fig_blobs
            else []
        )
        for idx, img_el in enumerate(fig_img_els):
            # _figure_blobs caps capture at one blob per FIGURE paragraph, so
            # every row holds at most one image. Two Acts (excise-tariff-act-1921,
            # corporate-law-economic-reform-program-act-1999) do carry two inline
            # <a:blip> in a single FIGURE <w:p>; the second is a byte-identical
            # duplicate of the next figure and is dropped in the reader.
            row = fig_results[idx] if idx < len(fig_results) else []
            if row:
                fr = row[0]
                img_el.set("src", fr.src)
                if fr.width is not None:
                    img_el.set("width", str(fr.width))
                if fr.height is not None:
                    img_el.set("height", str(fr.height))
                kind = fr.kind
            else:
                kind = "placeholder"  # no resolvable image; keep provisional src
            if kind == "raster":
                self._figures_raster += 1
            elif kind == "converted":
                self._figures_converted += 1
            else:
                self._figures_placeholder += 1

        # Append <attachments> after <body>
        attachments_el, _ = _build_attachments(schedule_groups)
        if attachments_el is not None:
            act_el.append(attachments_el)

        result = validate_akn(root, self._meta)

        # Assign sequential eIds to <authorialNote> elements
        for idx, note_el in enumerate(root.iter(f"{{{AKN_NS}}}authorialNote"), start=1):
            note_el.set("eId", f"note-{idx}")
            note_el.set("marker", str(idx))

        return root, result

    def build_with_report(
        self,
        corpus_index: dict,
        last_volume_path: Path | None = None,
    ) -> tuple[etree._Element, ParseReport]:
        """Run all build phases and return (xml_root, ParseReport)."""
        preface_paras, body_paras, schedule_groups = _split_stream(self._paragraphs)

        report = ParseReport(
            act_name=self._meta.name,
            preface_paras=len(preface_paras),
            schedules_found=len(schedule_groups),
            schedule_names=[grp[0].text for grp in schedule_groups if grp],
        )

        # Count with reclassification applied (mirrors what build() actually emits)
        _count_stack: list[tuple[ElementType, str, bool]] = []  # (type, num, had_text)
        for p in body_paras:
            # Mirror _resolve_para_ambiguity logic without lxml elements
            p_type = p.element_type
            if (p_type == ElementType.PARAGRAPH
                    and set(p.number.lower()).issubset(_ROMAN_CHARS)
                    and _count_stack
                    and _count_stack[-1][0] == ElementType.PARAGRAPH
                    and not _count_stack[-1][2]):  # open para has no text = container
                p_type = ElementType.SUBPARAGRAPH

            # Pop stack to correct depth
            target_depth = _DEPTH.get(p_type, 99)
            while _count_stack and _DEPTH.get(_count_stack[-1][0], -1) >= target_depth:
                _count_stack.pop()

            if p_type == ElementType.SUBSECTION:
                report.subsections_parsed += 1
            elif p_type == ElementType.PARAGRAPH:
                report.paragraphs_parsed += 1
            elif p_type == ElementType.SUBPARAGRAPH:
                report.subparagraphs_parsed += 1
            elif p_type == ElementType.NOTE:
                report.notes_found += 1
            elif p_type == ElementType.EXAMPLE:
                report.examples_found += 1
            elif p_type == ElementType.PENALTY:
                report.penalties_found += 1
            elif p_type == ElementType.LEVEL4:
                report.level4_found += 1
            elif p_type == ElementType.TABLE:
                report.tables_found += 1

            if p_type in {ElementType.SUBSECTION, ElementType.PARAGRAPH, ElementType.SUBPARAGRAPH}:
                if p.raw_style not in {"Body Text", "List Paragraph"}:
                    report.style_fallbacks += 1
                _count_stack.append((p_type, p.number, bool(p.text)))
            else:
                _count_stack = []

        report.schedule_clauses_found = _count_schedule_clauses(schedule_groups)

        root, _validation = self.build()

        # Capture quoted structure counts set during build()
        report.quoted_structures_found = self._quoted_structures_found
        report.quoted_structures_unhandled = self._quoted_structures_unhandled
        report.figures_found = self._figures_found
        report.figures_raster = self._figures_raster
        report.figures_converted = self._figures_converted
        report.figures_placeholder = self._figures_placeholder

        # Count <p> elements with inline formatting children
        _INLINE_TAGS = {
            f"{{{AKN_NS}}}b", f"{{{AKN_NS}}}i",
            f"{{{AKN_NS}}}sup", f"{{{AKN_NS}}}sub",
        }
        report.inline_formatted = sum(
            1 for p_el in root.iter(f"{{{AKN_NS}}}p")
            if any(c.tag in _INLINE_TAGS for c in p_el)
        )

        # 1. Inject <term>/<def> FIRST (requires raw p.text — must precede inject_refs)
        term_registry, terms_found = inject_terms(root)
        report.terms_found = terms_found
        # Duplicate detection: count eIds that appeared more than once (last-write-wins in registry)
        # Surface via ParseReport for corpus validation.
        report.duplicate_terms = terms_found - len(term_registry)

        # 1b. Inject list-form definitions (X means: + block list)
        list_defs_count = inject_list_defs(root, term_registry)
        report.list_defs_found = list_defs_count

        # 1c. Inject <ref> links for asterisk-prefixed term usages (OPC DD 1.6).
        # Must precede inject_quantities/inject_dates/inject_roles/inject_refs --
        # same skip-if-already-has-children hazard those passes share with each other.
        asterisk_resolved, asterisk_unresolved = inject_asterisk_refs(root, term_registry)
        report.asterisk_resolved = asterisk_resolved
        report.asterisk_unresolved = asterisk_unresolved

        # 2. Inject <quantity> markup for penalty units, imprisonment, deadlines
        # Must run BEFORE inject_refs: once inject_refs writes <ref> children into a <p>,
        # inject_quantities sees len(list(p_el)) > 0 and skips that paragraph.
        quantities_found = inject_quantities(root)
        report.quantities_found = quantities_found

        # 2b. Inject <date> calendar date markup
        dates_found = inject_dates(root)
        report.dates_found = dates_found

        # 3. Inject <role> markup for known Commonwealth roles
        # Same ordering constraint as inject_quantities — must precede inject_refs.
        roles_found = inject_roles(root)
        report.roles_found = roles_found

        # 4. Inject <ref> links (also processes <def> text produced by inject_terms)
        resolved, unresolved, range_resolved, range_unresolved = inject_refs(root, corpus_index)
        report.refs_resolved = resolved
        report.refs_unresolved = unresolved
        report.range_refs_resolved = range_resolved
        report.range_refs_unresolved = range_unresolved

        # 5. Inject <noteRef> for [note N] markers in body text
        note_refs = inject_note_refs(root)
        report.note_refs_injected = note_refs

        # 4b. Complete truncated list-form <def>s (colon-terminated definiens
        # with orphaned list content in sibling <paragraph>/<blockList>
        # elements). MUST run last -- see complete_list_definitions' docstring.
        list_defs_completed = complete_list_definitions(root)
        report.list_defs_completed = list_defs_completed

        # 6. Populate <references> with TLCTerm entries
        # TLCTerm href uses /ontology/term/au/ (not /ontology/concept/au/ — that is for TLCConcept)
        if term_registry:
            ns = {"akn": AKN_NS}
            refs_el = root.find(".//akn:references", ns)
            if refs_el is not None:
                for eid, show_as in sorted(term_registry.items()):
                    tlc = etree.SubElement(refs_el, f"{{{AKN_NS}}}TLCTerm")
                    tlc.set("eId", eid)
                    tlc.set("href", f"/ontology/term/au/{eid}")
                    tlc.set("showAs", show_as)

        # 7. Parse endnotes and inject amendment history metadata
        if last_volume_path is not None:
            endnote_result = parse_endnotes(DocxDocument(str(last_volume_path)))
            report.amendment_events_parsed = len(endnote_result.amendment_events)
            if endnote_result.amendment_events:
                inject_lifecycle(root, self._meta, endnote_result.amendment_events)
                inject_temporal_data(root, endnote_result.amendment_events)
                inject_passive_mods(root, endnote_result.amendment_events, report=report)

        return root, report

    def _make_skeleton(self) -> etree._Element:
        meta = self._meta
        today = date.today().isoformat()
        expr_date = meta.effective_date.isoformat()
        work_uri = meta.frbr_work_uri
        expr_uri = meta.frbr_expression_uri

        root = AKN.akomaNtoso(
            AKN.act(
                AKN.meta(
                    AKN.identification(
                        AKN.FRBRWork(
                            AKN.FRBRthis(value=f"{work_uri}/!main"),
                            AKN.FRBRuri(value=work_uri),
                            AKN.FRBRdate(date=f"{meta.year}-01-01", name="Generation"),
                            AKN.FRBRauthor(href="#parliament"),
                            AKN.FRBRcountry(value="au"),
                            AKN.FRBRsubtype(value="act"),
                            AKN.FRBRnumber(value=str(meta.number)),
                            AKN.FRBRname(value=meta.safe_name),
                            AKN.FRBRprescriptive(value="true"),
                            AKN.FRBRauthoritative(value="true"),
                        ),
                        AKN.FRBRExpression(
                            AKN.FRBRthis(value=f"{expr_uri}/!main"),
                            AKN.FRBRuri(value=expr_uri),
                            AKN.FRBRdate(date=expr_date, name="Generation"),
                            AKN.FRBRauthor(href="#parliament"),
                            AKN.FRBRlanguage(language="eng"),
                        ),
                        AKN.FRBRManifestation(
                            AKN.FRBRthis(value=f"{expr_uri}/!main.akn"),
                            AKN.FRBRuri(value=f"{expr_uri}/!main.akn"),
                            AKN.FRBRdate(date=today, name="Generation"),
                            AKN.FRBRauthor(href="#lex-au"),
                        ),
                        source="#lex-au",
                    ),
                    AKN.references(
                        AKN.TLCOrganization(
                            eId="parliament",
                            href="/ontology/organization/au/parliament",
                            showAs="Parliament of Australia",
                        ),
                        AKN.TLCOrganization(
                            eId="lex-au",
                            href="https://github.com/cchew/lex-au",
                            showAs="lex-au",
                        ),
                        source="#lex-au",
                    ),
                ),
                AKN.body(),
                name="act",
            )
        )

        if self._meta.subject_keywords:
            ns = {"akn": AKN_NS}
            meta_el = root.find(".//akn:meta", ns)
            refs_el = meta_el.find(f"{{{AKN_NS}}}references")
            refs_index = list(meta_el).index(refs_el) if refs_el is not None else len(list(meta_el))
            classification_el = etree.Element(f"{{{AKN_NS}}}classification")
            classification_el.set("source", "#legislation-gov-au")
            for kw in self._meta.subject_keywords:
                kw_el = etree.SubElement(classification_el, f"{{{AKN_NS}}}keyword")
                kw_el.set("value", kw.lower().replace(" ", "-"))
                kw_el.set("showAs", kw)
                kw_el.set("dictionary", "#legislation-gov-au")
            meta_el.insert(refs_index, classification_el)

        return root
