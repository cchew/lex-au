from __future__ import annotations

import sys
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
}

# Hierarchy depth (lower = higher in tree)
_DEPTH = {
    ElementType.CHAPTER:     0,
    ElementType.PART:        1,
    ElementType.DIVISION:    2,
    ElementType.SUBDIVISION: 3,
    ElementType.SECTION:     4,
}


class AknBuilder:
    def __init__(self, meta: ActMetadata) -> None:
        self._meta = meta
        self._paragraphs: list[ParsedParagraph] = []

    def add(self, paragraph: ParsedParagraph) -> None:
        if paragraph.element_type != ElementType.SKIP:
            self._paragraphs.append(paragraph)

    def build(self) -> tuple[etree._Element, ValidationResult]:
        root = self._make_skeleton()
        ns = {"akn": AKN_NS}
        body = root.find(".//akn:body", ns)

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

        for p in self._paragraphs:
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

            elif p.element_type == ElementType.BODY and p.text:
                # Attach body text to the current section's <content>
                parent_elem = stack[-1][2] if stack else body
                if current_content is None:
                    current_content = etree.SubElement(parent_elem, f"{{{AKN_NS}}}content")
                p_el = etree.SubElement(current_content, f"{{{AKN_NS}}}p")
                p_el.text = p.text

        result = validate_akn(root, self._meta)
        if not result.passed:
            for err in result.errors:
                print(f"[validation] {self._meta.safe_name}: {err}", file=sys.stderr)
        return root, result

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
                            AKN.FRBRdate(date=str(meta.year), name="Generation"),
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
