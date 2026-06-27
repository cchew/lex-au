from __future__ import annotations
import re
from lxml import etree

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"

_MONTHS = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}

# "1 July 1995" or "01 July 1995"
_DMY = re.compile(
    r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|'
    r'September|October|November|December)\s+(\d{4})\b',
    re.IGNORECASE,
)

# "01/07/1995" — AU convention DD/MM/YYYY
_SLASH = re.compile(r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b')

# Dateless commencement references
_COMMENCEMENT = re.compile(
    r'\b(the day this Act commences|the commencement day|the day of commencement)\b',
    re.IGNORECASE,
)


def inject_dates(root: etree._Element) -> int:
    """Inject <date> elements into all <p> elements. Returns count injected."""
    count = 0
    for p_el in root.iter(f"{{{AKN_NS}}}p"):
        if len(list(p_el)) > 0:
            continue  # skip mixed-content paragraphs (have child elements)
        text = p_el.text
        if not text:
            continue
        count += _inject_into_p(p_el, text)
    return count


def _inject_into_p(p_el: etree._Element, text: str) -> int:
    """Replace date strings in p_el.text with <date> elements. Returns injected count."""
    # Collect all matches (DMY, slash, commencement) in position order
    matches: list[tuple[int, int, str, str | None]] = []  # (start, end, display, iso_date|None)

    for m in _DMY.finditer(text):
        day = m.group(1).zfill(2)
        month = _MONTHS[m.group(2).lower()]
        year = m.group(3)
        iso = f"{year}-{month}-{day}"
        matches.append((m.start(), m.end(), m.group(0), iso))

    for m in _SLASH.finditer(text):
        day = m.group(1).zfill(2)
        month = m.group(2).zfill(2)
        year = m.group(3)
        iso = f"{year}-{month}-{day}"
        matches.append((m.start(), m.end(), m.group(0), iso))

    for m in _COMMENCEMENT.finditer(text):
        matches.append((m.start(), m.end(), m.group(0), None))

    if not matches:
        return 0

    # Sort by position; resolve overlaps by keeping leftmost
    matches.sort(key=lambda x: x[0])
    filtered: list[tuple[int, int, str, str | None]] = []
    last_end = 0
    for start, end, display, iso in matches:
        if start >= last_end:
            filtered.append((start, end, display, iso))
            last_end = end

    if not filtered:
        return 0

    # Reconstruct p_el content
    p_el.text = None
    prev_el: etree._Element | None = None
    cursor = 0
    for start, end, display, iso in filtered:
        pre = text[cursor:start]
        date_el = etree.SubElement(p_el, f"{{{AKN_NS}}}date")
        date_el.text = display
        if iso:
            date_el.set("date", iso)
        if prev_el is None:
            p_el.text = pre or None
        else:
            prev_el.tail = pre or None
        prev_el = date_el
        cursor = end
    if prev_el is not None:
        prev_el.tail = text[cursor:] or None

    return len(filtered)
