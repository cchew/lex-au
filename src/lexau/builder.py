from __future__ import annotations

import re
from dataclasses import replace, dataclass
from datetime import date
from pathlib import Path
from lxml import etree
from lxml.builder import ElementMaker

from lexau.models import ActMetadata, ParseReport
from lexau.parser import ParsedParagraph, ElementType, InlineSpan
from lexau.frbr import make_eid
from lexau.validator import validate_akn, ValidationResult
from lexau.reflinks import inject_refs
from lexau.termlinks import inject_terms, inject_list_defs, complete_list_definitions
from lexau.quantlinks import inject_quantities, inject_roles, inject_asterisk_refs
from lexau.datelinks import inject_dates
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
                child = etree.SubElement(outer, f"{{{AKN_NS}}}i")
                child.text = span.text
                prev = outer
            elif span.bold:
                child = etree.SubElement(p_el, f"{{{AKN_NS}}}b")
                child.text = span.text
                prev = child
            elif span.italic:
                child = etree.SubElement(p_el, f"{{{AKN_NS}}}i")
                child.text = span.text
                prev = child
            elif span.superscript:
                child = etree.SubElement(p_el, f"{{{AKN_NS}}}sup")
                child.text = span.text
                prev = child
            else:  # subscript
                child = etree.SubElement(p_el, f"{{{AKN_NS}}}sub")
                child.text = span.text
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
    """Return (preface_paras, body_paras, list_of_schedule_para_groups)."""
    first_structural = next(
        (i for i, p in enumerate(paragraphs) if p.element_type in _STRUCTURAL),
        len(paragraphs),
    )
    preface = paragraphs[:first_structural]
    rest = paragraphs[first_structural:]

    schedule_start = next(
        (i for i, p in enumerate(rest) if _is_schedule_heading(p)),
        len(rest),
    )
    body = rest[:schedule_start]
    schedule_paras = rest[schedule_start:]

    schedules: list[list[ParsedParagraph]] = []
    current: list[ParsedParagraph] = []
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
    """Build clause hierarchy inside a schedule hcontainer. Returns count of top-level clauses."""
    clause_count = 0
    clause_idx = 0
    current_clause: etree._Element | None = None
    current_subclause: etree._Element | None = None  # dotted subclause (e.g. 7.1) from SECTION
    current_para: etree._Element | None = None

    def _get_or_create_content(parent: etree._Element) -> etree._Element:
        for child in parent:
            if child.tag == f"{{{AKN_NS}}}content":
                return child
        return etree.SubElement(parent, f"{{{AKN_NS}}}content")

    for p in paragraphs:
        if p.element_type == ElementType.BODY and p.text:
            text = p.text.strip()

            m = _APP_CLAUSE_RE.match(text)
            if m:
                clause_idx += 1
                clause_count += 1
                num_str = m.group(1)
                heading_str = (m.group(2) or "").strip()
                eid = f"{schedule_eid}__clause-{clause_idx}"
                current_clause = etree.SubElement(
                    hcontainer, f"{{{AKN_NS}}}hcontainer", name="clause", eId=eid
                )
                etree.SubElement(current_clause, f"{{{AKN_NS}}}num").text = num_str
                if heading_str:
                    etree.SubElement(current_clause, f"{{{AKN_NS}}}heading").text = heading_str
                current_subclause = None
                current_para = None
                continue

            m = _SUBCLAUSE_RE.match(text)
            if m:
                num_str = m.group(1)
                content_text = m.group(2).strip()
                parent = current_clause if current_clause is not None else hcontainer
                parent_eid = parent.get("eId", schedule_eid)
                eid = f"{parent_eid}__subclause-{num_str.replace('.', '-')}"
                current_subclause = etree.SubElement(
                    parent, f"{{{AKN_NS}}}hcontainer", name="subclause", eId=eid
                )
                etree.SubElement(current_subclause, f"{{{AKN_NS}}}num").text = num_str
                if content_text:
                    content_el = etree.SubElement(current_subclause, f"{{{AKN_NS}}}content")
                    etree.SubElement(content_el, f"{{{AKN_NS}}}p").text = content_text
                current_para = None
                continue

            m = _CLAUSE_RE.match(text)
            if m:
                clause_idx += 1
                clause_count += 1
                num_str = m.group(1)
                heading_str = m.group(2).strip()
                eid = f"{schedule_eid}__clause-{num_str}"
                current_clause = etree.SubElement(
                    hcontainer, f"{{{AKN_NS}}}hcontainer", name="clause", eId=eid
                )
                etree.SubElement(current_clause, f"{{{AKN_NS}}}num").text = num_str
                etree.SubElement(current_clause, f"{{{AKN_NS}}}heading").text = heading_str
                current_subclause = None
                current_para = None
                continue

            # Plain body text
            parent = current_subclause if current_subclause is not None else (current_clause if current_clause is not None else hcontainer)
            content_el = _get_or_create_content(parent)
            _p_el = etree.SubElement(content_el, f"{{{AKN_NS}}}p")
            _emit_p_inline(_p_el, p)

        elif p.element_type == ElementType.PARAGRAPH:
            parent = current_subclause if current_subclause is not None else (current_clause if current_clause is not None else hcontainer)
            parent_eid = parent.get("eId", schedule_eid)
            eid = f"{parent_eid}__para-{p.number}"
            current_para = etree.SubElement(parent, f"{{{AKN_NS}}}paragraph", eId=eid)
            etree.SubElement(current_para, f"{{{AKN_NS}}}num").text = p.number
            if p.text:
                content_el = etree.SubElement(current_para, f"{{{AKN_NS}}}content")
                _p_el = etree.SubElement(content_el, f"{{{AKN_NS}}}p")
                _emit_p_inline(_p_el, p)

        elif p.element_type == ElementType.SECTION and p.number:
            # SECTION-typed paragraphs inside a schedule (e.g. TG Regs Essential Principles).
            # Dotted numbers (7.1, 7.2) are subclauses; plain numbers (7, 8) are top-level clauses.
            num_str = p.number
            heading_str = p.heading or ""
            if "." in num_str:
                parent = current_clause if current_clause is not None else hcontainer
                parent_eid = parent.get("eId", schedule_eid)
                eid = f"{parent_eid}__subclause-{num_str.replace('.', '-')}"
                current_subclause = etree.SubElement(
                    parent, f"{{{AKN_NS}}}hcontainer", name="subclause", eId=eid
                )
                etree.SubElement(current_subclause, f"{{{AKN_NS}}}num").text = num_str
                if heading_str:
                    etree.SubElement(current_subclause, f"{{{AKN_NS}}}heading").text = heading_str
                current_para = None
            else:
                clause_idx += 1
                clause_count += 1
                eid = f"{schedule_eid}__clause-{num_str}"
                current_clause = etree.SubElement(
                    hcontainer, f"{{{AKN_NS}}}hcontainer", name="clause", eId=eid
                )
                etree.SubElement(current_clause, f"{{{AKN_NS}}}num").text = num_str
                if heading_str:
                    etree.SubElement(current_clause, f"{{{AKN_NS}}}heading").text = heading_str
                current_subclause = None
                current_para = None

        elif p.element_type == ElementType.SUBSECTION and p.number:
            # Numbered subclauses (1, 2, 3) within a schedule clause or dotted subclause.
            # Always sibling under the nearest dotted subclause or top-level clause — never
            # nested inside a previous numbered subclause.
            num_str = p.number
            parent = current_subclause if current_subclause is not None else (
                current_clause if current_clause is not None else hcontainer
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

        elif p.element_type == ElementType.SUBPARAGRAPH:
            if current_para is not None:
                parent = current_para
            elif current_subclause is not None:
                parent = current_subclause
            elif current_clause is not None:
                parent = current_clause
            else:
                parent = hcontainer
            parent_eid = parent.get("eId", schedule_eid)
            eid = f"{parent_eid}__subpara-{p.number}"
            subpara_el = etree.SubElement(parent, f"{{{AKN_NS}}}subparagraph", eId=eid)
            etree.SubElement(subpara_el, f"{{{AKN_NS}}}num").text = p.number
            if p.text:
                content_el = etree.SubElement(subpara_el, f"{{{AKN_NS}}}content")
                _p_el = etree.SubElement(content_el, f"{{{AKN_NS}}}p")
                _emit_p_inline(_p_el, p)

        elif p.text:
            # TABLE/NOTE/EXAMPLE/PENALTY inside schedule — emit as plain content
            parent = current_clause if current_clause is not None else hcontainer
            content_el = _get_or_create_content(parent)
            _p_el = etree.SubElement(content_el, f"{{{AKN_NS}}}p")
            _emit_p_inline(_p_el, p)

    return clause_count


def _count_schedule_clauses(schedule_groups: list[list[ParsedParagraph]]) -> int:
    """Count top-level clause hcontainers across all schedule groups (for ParseReport)."""
    count = 0
    for group in schedule_groups:
        for p in group[1:]:  # skip schedule heading
            if p.element_type == ElementType.BODY and p.text:
                text = p.text.strip()
                if _APP_CLAUSE_RE.match(text):
                    count += 1
                elif not _SUBCLAUSE_RE.match(text) and _CLAUSE_RE.match(text):
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
        insert_idx = list(meta_el).index(td_el) + 1 if td_el is not None else len(list(meta_el))
        meta_el.insert(insert_idx, analysis_el)


class AknBuilder:
    def __init__(self, meta: ActMetadata) -> None:
        self._meta = meta
        self._paragraphs: list[ParsedParagraph] = []
        self._quoted_structures_found: int = 0
        self._quoted_structures_unhandled: int = 0
        self._figures_found: int = 0

    def add(self, paragraph: ParsedParagraph) -> None:
        if paragraph.element_type != ElementType.SKIP:
            self._paragraphs.append(paragraph)

    def build(self) -> tuple[etree._Element, ValidationResult]:
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
                sub = AknBuilder(self._meta)
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
                fig_el = etree.SubElement(parent_elem, f"{{{AKN_NS}}}figure")
                img_src = f"corpus/images/{self._meta.safe_name}-fig-{self._figures_found}.png"
                etree.SubElement(fig_el, f"{{{AKN_NS}}}img", src=img_src, alt="")
                current_content = None

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
