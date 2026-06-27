from __future__ import annotations

import re
from lxml import etree

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
AKN_TAG = f"{{{AKN_NS}}}"

_P_TAG = f"{AKN_TAG}p"
_DEF_TAG = f"{AKN_TAG}def"
_HEADING_TAG = f"{AKN_TAG}heading"
_NUM_TAG = f"{AKN_TAG}num"

_SKIP_PARENT_TAGS = {_HEADING_TAG, _NUM_TAG}

# Range reference pattern: "sections 7 to 12", "Parts II to IV", "ss 3 to 8"
# The keyword prefix (sections/parts/divisions) already excludes date ranges like
# "from 1 July to 30 June" which do not begin with a legislation structural keyword.
_RANGE_RE = re.compile(
    r'\b(sections?|ss\.?|parts?|divisions?)\s+'
    r'(\w+)\s+to\s+(\w+)',
    re.IGNORECASE,
)

# Prefix map: keyword (lower) → AKN eId prefix
_RANGE_PREFIX: dict[str, str] = {
    "section": "sec",
    "sections": "sec",
    "ss": "sec",
    "ss.": "sec",
    "part": "part",
    "parts": "part",
    "division": "dvs",
    "divisions": "dvs",
}

_PATTERNS = [
    # 3-level inline: s 6(1)(a) → #sec-6__subsec-1__para-a  [most specific first]
    (re.compile(r'\bs\s*(\d+[A-Z]?)\((\d+[A-Z]?)\)\(([a-z]+)\)'), "sec_subsec_para"),
    # 2-level: s 16(2) → #sec-16__subsec-2
    (re.compile(r'\bs\s*(\d+[A-Z]?)\((\d+[A-Z]?)\)'), "sec_subsec"),
    # 1-level: section 16 or s 16
    (re.compile(r'\b(?:section|s)\s+(\d+[A-Z]?)'), "sec"),
    # Part/Division intra-Act (not followed by "of the <Act>")
    (re.compile(r'\b(Part|Division)\s+([\dIVXA-Z]+[A-Z]?)(?!\s+of\s+the)'), "part_div"),
    # Definitional refs: "within the meaning of section/subsection N" or "as defined in section N"
    (
        re.compile(
            r'\b(?:within the meaning of|as defined in)\s+'
            r'(?:section|subsection|s)\s+(\d+[A-Z]?)(?:\((\d+[A-Z]?)\))?'
        ),
        "def_ref",
    ),
    # Subsidiary legislation: "the X Regulation/Instrument/Order/Rules YYYY"
    (
        re.compile(r'\bthe\s+([A-Z][A-Za-z ]+?(?:Regulation|Instrument|Order|Rules?)\s+\d{4})'),
        "subsidiary",
    ),
    # Cross-Act: "the Privacy Act 1988"
    (re.compile(r'\bthe\s+([A-Z][A-Za-z ]+?Act\s+\d{4})'), "act"),
]


def _quoted_ranges(text: str) -> list[tuple[int, int]]:
    """Return list of (start, end) ranges for text inside double-quoted strings."""
    ranges: list[tuple[int, int]] = []
    i = 0
    while i < len(text):
        if text[i] == '"':
            j = text.find('"', i + 1)
            if j == -1:
                break
            ranges.append((i, j + 1))
            i = j + 1
        else:
            i += 1
    return ranges


def _in_quoted_range(start: int, end: int, quoted: list[tuple[int, int]]) -> bool:
    """Return True if the match span [start, end) falls entirely within a quoted range."""
    for q_start, q_end in quoted:
        if q_start <= start and end <= q_end:
            return True
    return False


def _collect_matches(
    text: str,
    quoted_ranges: list[tuple[int, int]],
) -> list[tuple[int, int, re.Match, str]]:
    """Collect all non-overlapping, non-quoted matches sorted by start position."""
    candidates: list[tuple[int, int, re.Match, str]] = []
    for pattern, kind in _PATTERNS:
        for m in pattern.finditer(text):
            if not _in_quoted_range(m.start(), m.end(), quoted_ranges):
                candidates.append((m.start(), m.end(), m, kind))

    # Sort by start position
    candidates.sort(key=lambda x: x[0])

    # Remove overlapping matches (keep earliest / leftmost)
    result: list[tuple[int, int, re.Match, str]] = []
    last_end = -1
    for start, end, m, kind in candidates:
        if start >= last_end:
            result.append((start, end, m, kind))
            last_end = end

    return result


def _make_ref(
    match: re.Match,
    kind: str,
    corpus_index: dict,
    resolved: list[int],
    unresolved: list[int],
) -> etree._Element:
    """Create a <ref> element for the given match."""
    ref_el = etree.Element(f"{AKN_TAG}ref")
    ref_el.text = match.group(0)

    if kind == "sec_subsec_para":
        ref_el.set("href", f"#sec-{match.group(1)}__subsec-{match.group(2)}__para-{match.group(3)}")
        resolved[0] += 1
    elif kind == "sec_subsec":
        ref_el.set("href", f"#sec-{match.group(1)}__subsec-{match.group(2)}")
        resolved[0] += 1
    elif kind == "sec":
        ref_el.set("href", f"#sec-{match.group(1)}")
        resolved[0] += 1
    elif kind == "part_div":
        prefix = "part" if match.group(1) == "Part" else "dvs"
        ref_el.set("href", f"#{prefix}-{match.group(2)}")
        resolved[0] += 1
    elif kind == "def_ref":
        sec_num = match.group(1)
        subsec_num = match.group(2)
        if subsec_num:
            ref_el.set("href", f"#sec-{sec_num}__subsec-{subsec_num}")
        else:
            ref_el.set("href", f"#sec-{sec_num}")
        resolved[0] += 1
    elif kind == "subsidiary":
        leg_name = match.group(1).strip()
        if leg_name in corpus_index:
            ref_el.set("href", corpus_index[leg_name]["frbr_uri"])
            resolved[0] += 1
        else:
            ref_el.set("class", "unresolved")
            unresolved[0] += 1
    elif kind == "act":
        act_name = match.group(1).strip()
        if act_name in corpus_index:
            ref_el.set("href", corpus_index[act_name]["frbr_uri"])
            resolved[0] += 1
        else:
            ref_el.set("class", "unresolved")
            unresolved[0] += 1

    return ref_el


def _process_p(p_el: etree._Element, corpus_index: dict) -> tuple[int, int]:
    """Inject <ref> elements into a single <p> element. Returns (resolved, unresolved)."""
    text = p_el.text or ""
    if not text:
        return 0, 0

    quoted = _quoted_ranges(text)
    matches = _collect_matches(text, quoted)

    if not matches:
        return 0, 0

    resolved = [0]
    unresolved = [0]

    # Clear existing text; we will rebuild content
    p_el.text = None

    prev_ref: etree._Element | None = None
    cursor = 0

    for start, end, m, kind in matches:
        pre_text = text[cursor:start]
        ref_el = _make_ref(m, kind, corpus_index, resolved, unresolved)

        if prev_ref is None:
            p_el.text = pre_text or None
        else:
            prev_ref.tail = pre_text or None

        p_el.append(ref_el)
        prev_ref = ref_el
        cursor = end

    # Remaining suffix
    suffix = text[cursor:]
    if prev_ref is not None:
        prev_ref.tail = suffix or None

    return resolved[0], unresolved[0]


def _process_rref(
    p_el: etree._Element,
    known_eids: set[str],
) -> tuple[int, int]:
    """Inject <rref> elements for range references in a plain-text <p>.

    Only runs on elements with no child elements (plain text paragraphs).
    Returns (range_resolved, range_unresolved).
    """
    # Only process paragraphs that are still plain text (no child elements)
    if len(p_el) > 0:
        return 0, 0

    text = p_el.text or ""
    if not text:
        return 0, 0

    matches = list(_RANGE_RE.finditer(text))
    if not matches:
        return 0, 0

    range_resolved = 0
    range_unresolved = 0

    # Collect non-overlapping matches, process right-to-left to preserve offsets
    # when we manipulate the element tree
    valid_matches: list[tuple[int, int, str, str, str]] = []
    last_start = len(text)
    for m in reversed(matches):
        if m.end() > last_start:
            continue  # overlapping — skip
        keyword = m.group(1).lower().rstrip(".")
        from_tok = m.group(2)
        to_tok = m.group(3)

        prefix = _RANGE_PREFIX.get(keyword, "sec")
        from_eid = f"{prefix}-{from_tok}"
        to_eid = f"{prefix}-{to_tok}"

        if from_eid in known_eids and to_eid in known_eids:
            valid_matches.append((m.start(), m.end(), from_eid, to_eid, m.group(0)))
            last_start = m.start()
            range_resolved += 1
        else:
            range_unresolved += 1

    if not valid_matches:
        return 0, range_unresolved

    # Sort by start position ascending to rebuild element content
    valid_matches.sort(key=lambda x: x[0])

    # Rebuild p_el content with <rref> elements inserted
    original_text = text
    p_el.text = None

    prev_el: etree._Element | None = None
    cursor = 0

    for start, end, from_eid, to_eid, match_text in valid_matches:
        pre_text = original_text[cursor:start]

        if prev_el is None:
            p_el.text = pre_text or None
        else:
            prev_el.tail = pre_text or None

        rref_el = etree.SubElement(p_el, f"{AKN_TAG}rref")
        rref_el.set("from", f"#{from_eid}")
        rref_el.set("upTo", f"#{to_eid}")
        rref_el.text = match_text

        prev_el = rref_el
        cursor = end

    suffix = original_text[cursor:]
    if prev_el is not None:
        prev_el.tail = suffix or None

    return range_resolved, range_unresolved


def inject_refs(root: etree._Element, corpus_index: dict) -> tuple[int, int, int, int]:
    """Walk XML tree and inject <ref> elements into <p> and <def> text nodes.

    Also injects <rref> elements for range references (e.g. "sections 7 to 12").

    Returns (resolved_count, unresolved_count, range_resolved, range_unresolved).
    """
    if root is None:
        return 0, 0, 0, 0

    total_resolved = 0
    total_unresolved = 0
    total_range_resolved = 0
    total_range_unresolved = 0

    # Collect known eIds from the document for rref endpoint resolution
    known_eids: set[str] = set()
    for el in root.iter():
        eid = el.get("eId")
        if eid:
            known_eids.add(eid)

    for elem in root.iter(_P_TAG, _DEF_TAG):
        parent = elem.getparent()
        if parent is not None and parent.tag in _SKIP_PARENT_TAGS:
            continue
        # Run rref injection BEFORE single-ref injection (rref needs plain text)
        rr, ru = _process_rref(elem, known_eids)
        total_range_resolved += rr
        total_range_unresolved += ru
        # Single-ref injection (operates on p_el.text of plain-text paragraphs)
        r, u = _process_p(elem, corpus_index)
        total_resolved += r
        total_unresolved += u

    return total_resolved, total_unresolved, total_range_resolved, total_range_unresolved
