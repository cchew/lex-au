from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree
from cobalt import Act as CobaltAct

from lexau.models import ActMetadata


@dataclass
class ValidationResult:
    passed: bool
    errors: list[str] = field(default_factory=list)


def validate_akn(xml: etree._Element, meta: ActMetadata) -> ValidationResult:
    errors: list[str] = []

    try:
        xml_bytes = etree.tostring(xml, pretty_print=False, xml_declaration=True, encoding="UTF-8")
        doc = CobaltAct(xml_bytes)
    except Exception as exc:
        return ValidationResult(passed=False, errors=[f"cobalt parse failed: {exc}"])

    try:
        actual = doc.expression_frbr_uri().expression_uri()
        expected = meta.frbr_expression_uri
        if actual != expected:
            errors.append(f"FRBR URI mismatch: got {actual!r}, expected {expected!r}")
    except Exception as exc:
        errors.append(f"expression_frbr_uri() failed: {exc}")

    if doc.work_date is None:
        errors.append("FRBRWork/FRBRdate missing or unparseable")

    if doc.expression_date is None:
        errors.append("FRBRExpression/FRBRdate missing or unparseable")

    return ValidationResult(passed=len(errors) == 0, errors=errors)
