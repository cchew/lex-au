from lxml import etree
from lexau.datelinks import inject_dates

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


def _get_p(root: etree._Element) -> etree._Element:
    return root.find(f".//{AKN_TAG}p")


def test_dmy_full():
    """'1 July 1995' → <date date="1995-07-01">1 July 1995</date>"""
    root = _make_root_with_p("This Act commences on 1 July 1995.")
    count = inject_dates(root)
    assert count == 1
    p = _get_p(root)
    date_el = p.find(f"{AKN_TAG}date")
    assert date_el is not None
    assert date_el.get("date") == "1995-07-01"
    assert date_el.text == "1 July 1995"


def test_dmy_leading_zero():
    """'01 January 2020' → <date date="2020-01-01">"""
    root = _make_root_with_p("Effective from 01 January 2020.")
    count = inject_dates(root)
    assert count == 1
    p = _get_p(root)
    date_el = p.find(f"{AKN_TAG}date")
    assert date_el is not None
    assert date_el.get("date") == "2020-01-01"
    assert date_el.text == "01 January 2020"


def test_slash_date():
    """'01/07/1995' → <date date="1995-07-01"> (AU convention DD/MM/YYYY)"""
    root = _make_root_with_p("This took effect from 01/07/1995.")
    count = inject_dates(root)
    assert count == 1
    p = _get_p(root)
    date_el = p.find(f"{AKN_TAG}date")
    assert date_el is not None
    assert date_el.get("date") == "1995-07-01"
    assert date_el.text == "01/07/1995"


def test_commencement_day():
    """'the commencement day' → <date> with no date attribute"""
    root = _make_root_with_p("On the commencement day, the officer must notify.")
    count = inject_dates(root)
    assert count == 1
    p = _get_p(root)
    date_el = p.find(f"{AKN_TAG}date")
    assert date_el is not None
    assert date_el.get("date") is None
    assert date_el.text == "the commencement day"


def test_no_relative():
    """'within 14 weeks' must NOT be matched"""
    root = _make_root_with_p("A person must lodge within 14 weeks after the event.")
    count = inject_dates(root)
    assert count == 0
    p = _get_p(root)
    assert p.find(f"{AKN_TAG}date") is None
    assert p.text == "A person must lodge within 14 weeks after the event."


def test_multiple_dates():
    """'from 1 July 1995 to 30 June 2000' → two <date> elements"""
    root = _make_root_with_p("This applies from 1 July 1995 to 30 June 2000.")
    count = inject_dates(root)
    assert count == 2
    p = _get_p(root)
    dates = p.findall(f"{AKN_TAG}date")
    assert len(dates) == 2
    assert dates[0].get("date") == "1995-07-01"
    assert dates[1].get("date") == "2000-06-30"


def test_no_double_wrap():
    """p_el with existing child elements is skipped entirely"""
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section", eId="sec-1")
    content = etree.SubElement(sec, f"{AKN_TAG}content")
    p = etree.SubElement(content, f"{AKN_TAG}p")
    # p already has a child <ref> element — simulate post-inject_refs state
    ref_el = etree.SubElement(p, f"{AKN_TAG}ref")
    ref_el.text = "some act"
    p.text = "On 1 July 1995, "

    count = inject_dates(root)
    assert count == 0
    # p structure must be unchanged
    assert len(list(p)) == 1
    assert p.find(f"{AKN_TAG}date") is None
