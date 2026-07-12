from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Callable

from lxml import etree

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
AKN_TAG = f"{{{AKN_NS}}}"

_P_TAG = f"{AKN_TAG}p"
_HEADING_TAG = f"{AKN_TAG}heading"
_NUM_TAG = f"{AKN_TAG}num"
_REFS_TAG = f"{AKN_TAG}references"
_SKIP_PARENT_TAGS = {_HEADING_TAG, _NUM_TAG}

_QTY_PATTERNS = [
    # Penalty units: plain "60 penalty units" and comma-formatted "2,500 penalty units"
    # Also matches "not more than 60 penalty units" (the \d[\d,]* anchors on the number)
    (re.compile(r'\b(\d[\d,]*)\s+penalty units?\b', re.IGNORECASE), "penaltyUnit", "penalty unit"),
    (re.compile(r'\b(?:(\d+)\s+(?:months?|years?)\s+imprisonment|imprisonment\s+for\s+(\d+)\s+(?:months?|years?))\b', re.IGNORECASE), "custodialSentence", "term of imprisonment"),
    # Deadlines: "within N days/weeks/months" — covers SSA 1991 (13 weeks) and SISA 1993 (28 days)
    (re.compile(r'\bwithin\s+(\d+)\s+(days?|weeks?|months?)\b', re.IGNORECASE), "deadline", "deadline"),
]

_TLC_CONCEPT_HREF = {
    "penaltyUnit":        "/ontology/concept/au/penaltyUnit",
    "custodialSentence":  "/ontology/concept/au/custodialSentence",
    "deadline":           "/ontology/concept/au/deadline",
}

# -- Shared helpers ------------------------------------------------------------

def _deoverlap(
    candidates: list[tuple[int, int, re.Match, str, str]],
) -> list[tuple[int, int, re.Match, str, str]]:
    """Sort candidates by start position and remove overlapping matches (keep earliest)."""
    candidates.sort(key=lambda x: x[0])
    result: list[tuple[int, int, re.Match, str, str]] = []
    last_end = -1
    for item in candidates:
        if item[0] >= last_end:
            result.append(item)
            last_end = item[1]
    return result


def _rebuild_p_with_inline(
    p_el: etree._Element,
    text: str,
    filtered: list[tuple[int, int, re.Match, str, str]],
    make_element: "Callable[[str, str, re.Match], etree._Element]",
) -> int:
    """Rebuild p_el text, inserting inline elements at each match position. Returns len(filtered)."""
    p_el.text = None
    prev_el: etree._Element | None = None
    cursor = 0
    for start, end, m, arg1, arg2 in filtered:
        pre = text[cursor:start]
        inline_el = make_element(arg1, arg2, m)
        if prev_el is None:
            p_el.text = pre or None
        else:
            prev_el.tail = pre or None
        p_el.append(inline_el)
        prev_el = inline_el
        cursor = end
    if prev_el is not None:
        prev_el.tail = text[cursor:] or None
    return len(filtered)

# ------------------------------------------------------------------------------


def _process_p(p_el: etree._Element, seen_concepts: set[str]) -> int:
    """Inject <quantity> elements into a single <p>. Returns count injected.

    seen_concepts is mutated in place -- intentional shared-state pattern used by inject_quantities.
    """
    text = p_el.text
    if not text or len(list(p_el)) > 0:
        return 0

    candidates = [
        (m.start(), m.end(), m, concept_id, show_as)
        for pattern, concept_id, show_as in _QTY_PATTERNS
        for m in pattern.finditer(text)
    ]
    if not candidates:
        return 0
    filtered = _deoverlap(candidates)

    def make_qty(concept_id: str, show_as: str, m: re.Match) -> etree._Element:
        seen_concepts.add(concept_id)  # mutation -- caller (inject_quantities) owns seen_concepts
        el = etree.Element(f"{AKN_TAG}quantity")
        el.set("refersTo", f"#{concept_id}")
        el.text = m.group(0)
        return el

    return _rebuild_p_with_inline(p_el, text, filtered, make_qty)


def inject_quantities(root: etree._Element) -> int:
    """Walk all <p> elements; inject <quantity> markup; register TLCConcept in <references>.

    Returns total count of <quantity> elements injected.
    """
    total = 0
    seen_concepts: set[str] = set()

    for p_el in root.iter(_P_TAG):
        parent = p_el.getparent()
        if parent is not None and parent.tag in _SKIP_PARENT_TAGS:
            continue
        total += _process_p(p_el, seen_concepts)

    if seen_concepts:
        refs_el = root.find(f".//{_REFS_TAG}")
        if refs_el is not None:
            existing_eids = {el.get("eId") for el in refs_el}
            show_as_map = {c: s for _, c, s in _QTY_PATTERNS}
            for concept_id in sorted(seen_concepts):
                if concept_id not in existing_eids:
                    tlc = etree.SubElement(refs_el, f"{AKN_TAG}TLCConcept")
                    tlc.set("eId", concept_id)
                    tlc.set("href", _TLC_CONCEPT_HREF[concept_id])
                    tlc.set("showAs", show_as_map.get(concept_id, concept_id))

    return total


# Known Commonwealth role patterns: display text → eId slug
# Order matters: longer/more specific phrases must come first.
_AU_ROLES: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r'\bthe Privacy Commissioner\b', re.IGNORECASE), "privacy-commissioner", "Privacy Commissioner"),
    (re.compile(r'\bthe Information Commissioner\b', re.IGNORECASE), "information-commissioner", "Information Commissioner"),
    (re.compile(r'\bthe Commissioner of Taxation\b', re.IGNORECASE), "commissioner-of-taxation", "the Commissioner of Taxation"),
    (re.compile(r'\bthe (?:trustee|Trustee)\b', re.IGNORECASE), "trustee", "the trustee"),
    (re.compile(r'\bthe Commissioner\b', re.IGNORECASE), "commissioner", "the Commissioner"),
    (re.compile(r'\bthe Secretary\b', re.IGNORECASE), "secretary", "the Secretary"),
    (re.compile(r'\bthe Minister\b', re.IGNORECASE), "minister", "the Minister"),
    (re.compile(r'\bthe Registrar\b', re.IGNORECASE), "registrar", "the Registrar"),
    (re.compile(r'\bthe CEO\b', re.IGNORECASE), "ceo", "the CEO"),
    (re.compile(r'\bthe Authority\b', re.IGNORECASE), "authority", "the Authority"),
]

_TLC_ROLE_HREF = "/ontology/roles/au/{eid}"


def _process_p_for_roles(p_el: etree._Element, seen_roles: set[tuple[str, str]]) -> int:
    """Inject <role> elements into a single <p>. Returns count injected.

    seen_roles is mutated in place — intentional shared-state pattern used by inject_roles.
    """
    text = p_el.text
    if not text or len(list(p_el)) > 0:
        return 0

    candidates = [
        (m.start(), m.end(), m, eid, show_as)
        for pattern, eid, show_as in _AU_ROLES
        for m in pattern.finditer(text)
    ]
    if not candidates:
        return 0
    filtered = _deoverlap(candidates)

    def make_role(eid: str, show_as: str, m: re.Match) -> etree._Element:
        seen_roles.add((eid, show_as))  # mutation — caller (inject_roles) owns seen_roles
        el = etree.Element(f"{AKN_TAG}role")
        el.set("refersTo", f"#{eid}")
        el.text = m.group(0)
        return el

    return _rebuild_p_with_inline(p_el, text, filtered, make_role)


def inject_roles(root: etree._Element) -> int:
    """Walk all <p> elements; inject <role> markup; register TLCRole in <references>.

    Returns total count of <role> elements injected.
    """
    total = 0
    seen_roles: set[tuple[str, str]] = set()

    for p_el in root.iter(_P_TAG):
        parent = p_el.getparent()
        if parent is not None and parent.tag in _SKIP_PARENT_TAGS:
            continue
        total += _process_p_for_roles(p_el, seen_roles)

    if seen_roles:
        refs_el = root.find(f".//{_REFS_TAG}")
        if refs_el is not None:
            existing_eids = {el.get("eId") for el in refs_el}
            for eid, show_as in sorted(seen_roles):
                if eid not in existing_eids:
                    tlc = etree.SubElement(refs_el, f"{AKN_TAG}TLCRole")
                    tlc.set("eId", eid)
                    tlc.set("href", _TLC_ROLE_HREF.format(eid=eid))
                    tlc.set("showAs", show_as)

    return total


def inject_asterisk_refs(root: etree._Element, registry: dict[str, str]) -> tuple[int, int]:
    """Convert *term usage markers to <ref> links for terms already in the registry.

    OPC drafting convention (Drafting Direction 1.6): an asterisk immediately
    before a word or phrase marks a usage of a term that has its own
    Dictionary entry elsewhere in the Act, footnote-signposted to that entry.
    Resolves against known registry showAs values only (not generic
    asterisk-phrase detection) -- an asterisk by definition marks a usage of
    an *existing* defined term, so matching directly against the finite,
    already-known term set sidesteps ambiguous multi-word phrase-boundary
    detection entirely.

    Must run after inject_terms/inject_list_defs (registry must be fully
    populated) and before inject_quantities/inject_dates/inject_roles/
    inject_refs (same skip-if-already-has-children hazard those four passes
    share with each other and with inject_refs specifically).

    Returns (resolved_count, unresolved_count). Unresolved count is a
    heuristic (any remaining "*" + letter not consumed by a resolved match),
    mirroring the existing mods_unresolved diagnostic-counter convention.
    """
    if not registry:
        return 0, 0

    # Longest showAs first: when two registered terms could both match at the
    # same start position, _deoverlap keeps whichever candidate sorts first
    # at a tied position -- generating longer terms first ensures they win,
    # same precedence rule _AU_ROLES documents above.
    by_length = sorted(registry.items(), key=lambda kv: -len(kv[1]))
    asterisk_patterns = [
        (re.compile(r'\*(' + re.escape(show_as) + r')\b'), eid, show_as)
        for eid, show_as in by_length
    ]
    unresolved_re = re.compile(r'\*[A-Za-z]')

    resolved = 0
    unresolved = 0

    for p_el in root.iter(_P_TAG):
        parent = p_el.getparent()
        if parent is not None and parent.tag in _SKIP_PARENT_TAGS:
            continue
        text = p_el.text
        if not text or len(list(p_el)) > 0 or "*" not in text:
            continue

        candidates = [
            (m.start(), m.end(), m, eid, show_as)
            for pattern, eid, show_as in asterisk_patterns
            for m in pattern.finditer(text)
        ]
        filtered = _deoverlap(candidates) if candidates else []

        if filtered:
            def make_ref(eid: str, show_as: str, m: re.Match) -> etree._Element:
                el = etree.Element(f"{AKN_TAG}ref")
                el.set("href", f"#{eid}")
                el.text = show_as
                return el

            resolved += _rebuild_p_with_inline(p_el, text, filtered, make_ref)
            remaining_text = (p_el.text or "") + "".join(child.tail or "" for child in p_el)
        else:
            remaining_text = text

        unresolved += len(unresolved_re.findall(remaining_text))

    return resolved, unresolved
