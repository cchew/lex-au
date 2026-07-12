from lxml import etree
from lexau.quantlinks import inject_quantities, inject_roles, inject_asterisk_refs

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


def test_commissioner_role_injected():
    root = _make_root_with_p("The Commissioner must publish an annual report.")
    count = inject_roles(root)
    assert count == 1
    p = root.find(f".//{AKN_TAG}p")
    role_el = p.find(f"{AKN_TAG}role")
    assert role_el is not None
    assert "commissioner" in role_el.get("refersTo", "")


def test_minister_role_injected():
    root = _make_root_with_p("The Minister may by legislative instrument determine criteria.")
    count = inject_roles(root)
    assert count == 1
    p = root.find(f".//{AKN_TAG}p")
    role_el = p.find(f"{AKN_TAG}role")
    assert role_el is not None


def test_no_known_role_no_injection():
    root = _make_root_with_p("A person must not disclose the information.")
    count = inject_roles(root)
    assert count == 0


def test_tlcrole_registered_in_references():
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    meta_el = etree.SubElement(act, f"{AKN_TAG}meta")
    refs_el = etree.SubElement(meta_el, f"{AKN_TAG}references")
    refs_el.set("source", "#lex-au")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section")
    content = etree.SubElement(sec, f"{AKN_TAG}content")
    p = etree.SubElement(content, f"{AKN_TAG}p")
    p.text = "The Secretary must notify the Commissioner."
    inject_roles(root)
    # Both Secretary and Commissioner should be registered
    tlc_ids = {el.get("eId") for el in refs_el.findall(f"{AKN_TAG}TLCRole")}
    assert "secretary" in tlc_ids
    assert "commissioner" in tlc_ids


def test_asterisk_ref_resolves_known_term():
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    body = etree.SubElement(root, f"{AKN_TAG}body")
    p = etree.SubElement(body, f"{AKN_TAG}p")
    p.text = "The *entity must comply with this section."
    registry = {"term-entity": "entity"}

    resolved, unresolved = inject_asterisk_refs(root, registry)

    assert resolved == 1
    assert unresolved == 0
    ref = p.find(f"{AKN_TAG}ref")
    assert ref is not None
    assert ref.get("href") == "#term-entity"
    assert ref.text == "entity"


def test_asterisk_ref_multi_word_term():
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    body = etree.SubElement(root, f"{AKN_TAG}body")
    p = etree.SubElement(body, f"{AKN_TAG}p")
    p.text = "shown in the *Australian Business Register."
    registry = {"term-australian-business-register": "Australian Business Register"}

    resolved, unresolved = inject_asterisk_refs(root, registry)

    assert resolved == 1
    ref = p.find(f"{AKN_TAG}ref")
    assert ref.get("href") == "#term-australian-business-register"
    assert ref.text == "Australian Business Register"
    assert ref.tail == "."


def test_asterisk_unresolved_when_no_matching_term():
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    body = etree.SubElement(root, f"{AKN_TAG}body")
    p = etree.SubElement(body, f"{AKN_TAG}p")
    p.text = "The *nonexistent must comply."
    registry = {"term-entity": "entity"}  # doesn't match "nonexistent"

    resolved, unresolved = inject_asterisk_refs(root, registry)

    assert resolved == 0
    assert unresolved == 1
    assert p.find(f"{AKN_TAG}ref") is None
    assert p.text == "The *nonexistent must comply."  # left as literal, unchanged


def test_asterisk_ref_empty_registry_no_op():
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    body = etree.SubElement(root, f"{AKN_TAG}body")
    p = etree.SubElement(body, f"{AKN_TAG}p")
    p.text = "The *entity must comply."

    resolved, unresolved = inject_asterisk_refs(root, {})

    assert resolved == 0
    assert unresolved == 0
