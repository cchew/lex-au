from lxml import etree
from lexau.quantlinks import inject_quantities

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
AKN_TAG = f"{{{AKN_NS}}}"


def _make_root_with_p(text: str) -> etree._Element:
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section", eId="sec-1")
    content = etree.SubElement(sec, f"{AKN_TAG}content")
    p = etree.SubElement(content, f"{AKN_TAG}p")
    p.text = text
    return root


def test_penalty_units_injected():
    root = _make_root_with_p("Penalty: 60 penalty units.")
    count = inject_quantities(root)
    assert count == 1
    p = root.find(f".//{AKN_TAG}p")
    qty = p.find(f"{AKN_TAG}quantity")
    assert qty is not None
    assert qty.get("refersTo") == "#penaltyUnit"
    assert "60 penalty unit" in qty.text


def test_penalty_unit_singular():
    root = _make_root_with_p("Penalty: 1 penalty unit.")
    count = inject_quantities(root)
    assert count == 1


def test_imprisonment_injected():
    root = _make_root_with_p("Penalty: imprisonment for 5 years.")
    count = inject_quantities(root)
    assert count == 1
    p = root.find(f".//{AKN_TAG}p")
    qty = p.find(f"{AKN_TAG}quantity")
    assert qty is not None
    assert qty.get("refersTo") == "#custodialSentence"


def test_deadline_days_injected():
    root = _make_root_with_p("A person must notify within 30 days after becoming aware.")
    count = inject_quantities(root)
    assert count == 1
    p = root.find(f".//{AKN_TAG}p")
    qty = p.find(f"{AKN_TAG}quantity")
    assert qty is not None
    assert qty.get("refersTo") == "#deadline"


def test_no_quantity_pattern_no_injection():
    root = _make_root_with_p("The Commissioner must publish the report.")
    count = inject_quantities(root)
    assert count == 0
    p = root.find(f".//{AKN_TAG}p")
    assert p.find(f"{AKN_TAG}quantity") is None


def test_references_populated_with_tlcconcept(monkeypatch):
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    meta_el = etree.SubElement(act, f"{AKN_TAG}meta")
    refs_el = etree.SubElement(meta_el, f"{AKN_TAG}references")
    refs_el.set("source", "#lex-au")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section")
    content = etree.SubElement(sec, f"{AKN_TAG}content")
    p = etree.SubElement(content, f"{AKN_TAG}p")
    p.text = "Penalty: 60 penalty units."
    inject_quantities(root)
    concept = refs_el.find(f"{AKN_TAG}TLCConcept[@eId='penaltyUnit']")
    assert concept is not None
    assert concept.get("showAs") == "penalty unit"


def test_deadline_weeks_injected():
    root = _make_root_with_p("The claimant must notify within 13 weeks of the event.")
    count = inject_quantities(root)
    assert count == 1
    qty = root.find(f".//{AKN_TAG}quantity")
    assert qty is not None
    assert qty.get("refersTo") == "#deadline"
    assert "13 weeks" in qty.text


def test_deadline_months_injected():
    root = _make_root_with_p("The trustee must pay within 3 months.")
    count = inject_quantities(root)
    assert count == 1
    qty = root.find(f".//{AKN_TAG}quantity")
    assert qty.get("refersTo") == "#deadline"
    assert "3 months" in qty.text


def test_comma_formatted_penalty_units():
    root = _make_root_with_p("Penalty: 2,500 penalty units.")
    count = inject_quantities(root)
    assert count == 1
    qty = root.find(f".//{AKN_TAG}quantity")
    assert qty is not None
    assert qty.get("refersTo") == "#penaltyUnit"
    assert "2,500 penalty units" in qty.text


def test_not_more_than_penalty_phrase():
    root = _make_root_with_p("not more than 60 penalty units")
    count = inject_quantities(root)
    assert count == 1
    qty = root.find(f".//{AKN_TAG}quantity")
    assert qty is not None
    assert qty.get("refersTo") == "#penaltyUnit"
