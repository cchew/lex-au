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
    ElementType.CHAPTER:     "chapter",
    ElementType.PART:        "part",
    ElementType.DIVISION:    "division",
    ElementType.SUBDIVISION: "subDivision",
    ElementType.SECTION:     "section",
    ElementType.SUBSECTION:  "subsection",
    ElementType.PARAGRAPH:   "paragraph",
    ElementType.SUBPARAGRAPH: "subparagraph",
}

# Hierarchy depth (lower = higher in tree)
_DEPTH = {
    ElementType.CHAPTER:     0,
    ElementType.PART:        1,
    ElementType.DIVISION:    2,
    ElementType.SUBDIVISION: 3,
    ElementType.SECTION:     4,
    ElementType.SUBSECTION:  5,
    ElementType.PARAGRAPH:   6,
    ElementType.SUBPARAGRAPH: 7,
}

_ROMAN_CHARS = frozenset("ivxlcdm")

_TOC_HEADING_STYLE = "TOC Heading"
_TOC_ITEM_STYLES = {"TOC 1", "TOC 2", "TOC 3"}
_SCHEDULE_RE = re.compile(r'^Schedule\xa0(\d+|[IVX]+)', re.IGNORECASE)
_STRUCTURAL = frozenset({
    ElementType.CHAPTER, ElementType.PART, ElementType.DIVISION,
    ElementType.SUBDIVISION, ElementType.SECTION,
})


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


def _build_preface(preface_paras: list[ParsedParagraph]) -> etree._Element | None:
    if not preface_paras:
        return None
    preface_el = etree.Element(f"{{{AKN_NS}}}preface")
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


def _build_attachments(
    schedule_groups: list[list[ParsedParagraph]],
) -> etree._Element | None:
    if not schedule_groups:
        return None
    attachments_el = etree.Element(f"{{{AKN_NS}}}attachments")
    for idx, group in enumerate(schedule_groups, start=1):
        attachment_el = etree.SubElement(attachments_el, f"{{{AKN_NS}}}attachment")
        hcontainer = etree.SubElement(
            attachment_el,
            f"{{{AKN_NS}}}hcontainer",
            name="schedule",
            eId=f"schedule-{idx}",
        )
        if group:
            heading_text = group[0].text
            m = _SCHEDULE_RE.match(heading_text)
            heading_val = heading_text[m.end():].lstrip("—–- ") if m else heading_text
            h_el = etree.SubElement(hcontainer, f"{{{AKN_NS}}}heading")
            h_el.text = heading_val or heading_text
        content_el = etree.SubElement(hcontainer, f"{{{AKN_NS}}}content")
        for p in group[1:]:
            if p.text:
                p_el = etree.SubElement(content_el, f"{{{AKN_NS}}}p")
                p_el.text = p.text
    return attachments_el


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
        preface_el = _build_preface(preface_paras)
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
                tag = _AKN_TAG[p.element_type]
                elem = etree.SubElement(parent, f"{{{AKN_NS}}}{tag}", eId=full_eid)
                num_el = etree.SubElement(elem, f"{{{AKN_NS}}}num")
                num_el.text = p.number
                if p.heading:
                    h_el = etree.SubElement(elem, f"{{{AKN_NS}}}heading")
                    h_el.text = p.heading
                stack.append((p.element_type, p.number, elem))
                current_content = None
                if p.element_type in {ElementType.SUBSECTION, ElementType.PARAGRAPH, ElementType.SUBPARAGRAPH} and p.text:
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

        # Append <attachments> after <body>
        attachments_el = _build_attachments(schedule_groups)
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

        for p in body_paras:
            if p.element_type == ElementType.SUBSECTION:
                report.subsections_parsed += 1
            elif p.element_type == ElementType.PARAGRAPH:
                report.paragraphs_parsed += 1
            elif p.element_type == ElementType.SUBPARAGRAPH:
                report.subparagraphs_parsed += 1
            if p.element_type in {ElementType.SUBSECTION, ElementType.PARAGRAPH, ElementType.SUBPARAGRAPH}:
                if p.raw_style not in {"Body Text", "List Paragraph"}:
                    report.style_fallbacks += 1

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
