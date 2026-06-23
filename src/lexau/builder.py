from __future__ import annotations

import re
from dataclasses import replace
from datetime import date
from lxml import etree
from lxml.builder import ElementMaker

from lexau.models import ActMetadata
from lexau.parser import ParsedParagraph, ElementType
from lexau.frbr import make_eid
from lexau.validator import validate_akn, ValidationResult

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
    ElementType.SUBPARAGRAPH: 7,
    ElementType.LEVEL4:       8,
}

_ROMAN_CHARS = frozenset("ivxlcdm")

_TOC_HEADING_STYLE = "TOC Heading"
_TOC_ITEM_STYLES = {"TOC 1", "TOC 2", "TOC 3"}
_SCHEDULE_RE = re.compile(r'^Schedule[\xa0 ](\d+|[IVX]+)', re.IGNORECASE)
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
_CLAUSE_RE    = re.compile(r'^(\d+(?:\.\d+)*)\s+([A-Z].*)', re.DOTALL)


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
        (i for i, p in enumerate(rest)
         if p.element_type == ElementType.BODY and _SCHEDULE_RE.match(p.text)),
        len(rest),
    )
    body = rest[:schedule_start]
    schedule_paras = rest[schedule_start:]

    schedules: list[list[ParsedParagraph]] = []
    current: list[ParsedParagraph] = []
    for p in schedule_paras:
        if p.element_type == ElementType.BODY and _SCHEDULE_RE.match(p.text):
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
) -> etree._Element | None:
    if not preface_paras and (meta is None or not meta.long_title):
        return None
    preface_el = etree.Element(f"{{{AKN_NS}}}preface")

    # Emit <longTitle> as first child if available
    if meta and meta.long_title:
        lt_el = etree.SubElement(preface_el, f"{{{AKN_NS}}}longTitle")
        p_el = etree.SubElement(lt_el, f"{{{AKN_NS}}}p")
        p_el.text = meta.long_title

    toc_el: etree._Element | None = None
    for p in preface_paras:
        if p.raw_style == _TOC_HEADING_STYLE:
            toc_el = etree.SubElement(preface_el, f"{{{AKN_NS}}}toc")
        elif p.raw_style in _TOC_ITEM_STYLES:
            parent = toc_el if toc_el is not None else preface_el
            item = etree.SubElement(parent, f"{{{AKN_NS}}}tocItem")
            item.text = p.text
        else:
            p_el = etree.SubElement(preface_el, f"{{{AKN_NS}}}p")
            p_el.text = p.text
    return preface_el


def _build_schedule_content(
    hcontainer: etree._Element,
    schedule_eid: str,
    paragraphs: list[ParsedParagraph],
) -> int:
    """Build clause hierarchy inside a schedule hcontainer. Returns count of top-level clauses."""
    clause_count = 0
    clause_idx = 0
    current_clause: etree._Element | None = None
    current_subclause: etree._Element | None = None
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
                eid = f"{schedule_eid}__clause-{clause_idx}"
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
            etree.SubElement(content_el, f"{{{AKN_NS}}}p").text = text

        elif p.element_type == ElementType.PARAGRAPH:
            parent = current_subclause if current_subclause is not None else (current_clause if current_clause is not None else hcontainer)
            parent_eid = parent.get("eId", schedule_eid)
            eid = f"{parent_eid}__para-{p.number}"
            current_para = etree.SubElement(parent, f"{{{AKN_NS}}}paragraph", eId=eid)
            etree.SubElement(current_para, f"{{{AKN_NS}}}num").text = p.number
            if p.text:
                content_el = etree.SubElement(current_para, f"{{{AKN_NS}}}content")
                etree.SubElement(content_el, f"{{{AKN_NS}}}p").text = p.text

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
                etree.SubElement(content_el, f"{{{AKN_NS}}}p").text = p.text

        elif p.text:
            # TABLE/NOTE/EXAMPLE/PENALTY inside schedule — emit as plain content
            parent = current_clause if current_clause is not None else hcontainer
            content_el = _get_or_create_content(parent)
            etree.SubElement(content_el, f"{{{AKN_NS}}}p").text = p.text

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


class AknBuilder:
    def __init__(self, meta: ActMetadata) -> None:
        self._meta = meta
        self._paragraphs: list[ParsedParagraph] = []

    def add(self, paragraph: ParsedParagraph) -> None:
        if paragraph.element_type != ElementType.SKIP:
            self._paragraphs.append(paragraph)

    def build(self) -> tuple[etree._Element, ValidationResult]:
        preface_paras, body_paras, schedule_groups = _split_stream(self._paragraphs)

        root = self._make_skeleton()
        ns = {"akn": AKN_NS}
        act_el = root.find(".//akn:act", ns)
        body = root.find(".//akn:body", ns)

        # Insert <preface> before <body>
        preface_el = _build_preface(preface_paras, self._meta)
        if preface_el is not None:
            body_index = list(act_el).index(body)
            act_el.insert(body_index, preface_el)

        # Stack entries: (element_type, num, lxml_element)
        stack: list[tuple[ElementType, str, etree._Element]] = []
        current_content: etree._Element | None = None

        def _current_parent(for_type: ElementType) -> tuple[str, etree._Element]:
            """Pop stack until a valid parent exists for for_type; return (eid_prefix, parent_elem)."""
            target_depth = _DEPTH.get(for_type, 99)
            while stack and _DEPTH.get(stack[-1][0], -1) >= target_depth:
                stack.pop()
            prefix = "__".join(make_eid(et.value, num) for et, num, _ in stack) if stack else ""
            parent = stack[-1][2] if stack else body
            return prefix, parent

        for p in body_paras:
            p = _resolve_para_ambiguity(p, stack)
            if p.element_type in _AKN_TAG:
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
                current_content = None
                if p.element_type in {ElementType.SUBSECTION, ElementType.PARAGRAPH, ElementType.SUBPARAGRAPH, ElementType.LEVEL4} and p.text:
                    content_el = etree.SubElement(elem, f"{{{AKN_NS}}}content")
                    p_el = etree.SubElement(content_el, f"{{{AKN_NS}}}p")
                    p_el.text = p.text

            elif p.element_type == ElementType.BODY and p.text:
                # Attach body text to the current section's <content>
                parent_elem = stack[-1][2] if stack else body
                if current_content is None:
                    current_content = etree.SubElement(parent_elem, f"{{{AKN_NS}}}content")
                p_el = etree.SubElement(current_content, f"{{{AKN_NS}}}p")
                p_el.text = p.text

            elif p.element_type == ElementType.NOTE:
                parent_elem = stack[-1][2] if stack else body
                note_el = etree.SubElement(
                    parent_elem, f"{{{AKN_NS}}}authorialNote",
                    placement="end", marker="*",
                )
                content_el = etree.SubElement(note_el, f"{{{AKN_NS}}}content")
                etree.SubElement(content_el, f"{{{AKN_NS}}}p").text = p.text

            elif p.element_type == ElementType.EXAMPLE:
                parent_elem = stack[-1][2] if stack else body
                ex_el = etree.SubElement(
                    parent_elem, f"{{{AKN_NS}}}hcontainer", name="example"
                )
                content_el = etree.SubElement(ex_el, f"{{{AKN_NS}}}content")
                etree.SubElement(content_el, f"{{{AKN_NS}}}p").text = p.text

            elif p.element_type == ElementType.PENALTY:
                parent_elem = stack[-1][2] if stack else body
                pen_el = etree.SubElement(
                    parent_elem, f"{{{AKN_NS}}}hcontainer", name="penalty"
                )
                content_el = etree.SubElement(pen_el, f"{{{AKN_NS}}}content")
                etree.SubElement(content_el, f"{{{AKN_NS}}}p").text = p.text

            elif p.element_type == ElementType.TABLE:
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

        # Append <attachments> after <body>
        attachments_el, _ = _build_attachments(schedule_groups)
        if attachments_el is not None:
            act_el.append(attachments_el)

        result = validate_akn(root, self._meta)
        return root, result

    def build_with_report(self, corpus_index: dict) -> tuple[etree._Element, "ParseReport"]:
        """Run all build phases and return (xml_root, ParseReport)."""
        from lexau.reflinks import inject_refs
        from lexau.models import ParseReport

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

        resolved, unresolved = inject_refs(root, corpus_index)
        report.refs_resolved = resolved
        report.refs_unresolved = unresolved

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
        return root
