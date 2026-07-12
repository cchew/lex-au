from __future__ import annotations

import re
from lxml import etree

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
AKN_TAG = f"{{{AKN_NS}}}"

_P_TAG       = f"{AKN_TAG}p"
_HEADING_TAG = f"{AKN_TAG}heading"
_SECTION_TAG = f"{AKN_TAG}section"

# Sections whose heading contains these words are definition sections.
_DEF_HEADING_RE = re.compile(r'\b(definitions?|interpretations?|meaning\s+of|dictionary|defined\s+terms)\b', re.IGNORECASE)

# Definition patterns (applied to p.text only — not mixed content).
# Group 1: definiendum (the term being defined, without surrounding quotes)
# Group 2: connector word ("means" / "includes" / etc.)
# Group 3: definiens (the definition body)
#
# Quoted patterns first (more reliable — match exactly). Unquoted patterns last
# (broader — require 2-60 char definiendum to suppress false positives on body text).
# In real AU Acts (Privacy Act s.6, Fair Work Act s.12), terms are italicised in DOCX
# and become plain text after parsing — so unquoted forms are the dominant real-world case.
_STOP_DEFINIENDUM = re.compile(
    r'^(this\s+act|this\s+part|this\s+division|these\s+regulations?|this\s+schedule)\s+(means|includes?)',
    re.IGNORECASE
)

# A candidate connector match ("means"/"includes") immediately preceded by
# "does not" is a false positive -- the non-greedy definiendum group swallowed
# "does not" into itself (e.g. "Act does not include X" -> definiendum="Act
# does not", connector="include"). Checked against the text *before the
# matched connector only* -- a legitimate "...but does not include..."
# exclusion clause appearing later, inside the definiens (group 3, after the
# connector), is untouched by this check and continues to extract correctly.
_FALSE_CONNECTOR_TAIL_RE = re.compile(r'does\s+not\s*$', re.IGNORECASE)

# Narrative-prose false-positive guards. The broadened character class and
# widened length cap above (needed for real parenthetical/asterisk-marked
# definienda) also let ordinary narrative prose -- "includes"/"may include"
# used as an ordinary verb, not a definitional connector -- get captured as a
# fake definiendum. Confirmed against the live corpus 2026-07-13 across 4
# large Acts (1,721 real terms sampled): ~35 false positives, one root cause
# in each of four shapes, covered by the four checks below. All four are
# checked against the *captured* definiendum (`show_as`), not the whole
# paragraph, so a rejection can never suppress unrelated valid content
# elsewhere in the same paragraph.
_EMBEDDED_CONNECTOR_RE = re.compile(r'\b(means|includes?)\b', re.IGNORECASE)
_EMBEDDED_RELATIVE_RE = re.compile(r'\((who|which|that)\b', re.IGNORECASE)
_STOP_OPENER_RE = re.compile(
    r'^(a\s+reference|some\s+provisions|in\s+this\s+(division|chapter|part)|'
    r'before\s+the|there\s+is|for\s+the\s+purposes\s+of)\b',
    re.IGNORECASE
)
_DANGLING_FUNCTION_WORDS = {
    'and', 'or', 'but', 'by', 'to', 'of', 'in', 'on', 'at', 'for', 'with', 'from', 'as',
    'that', 'which', 'who', 'whom', 'whose', 'can', 'may', 'must', 'shall', 'will',
    'through', 'the', 'a', 'an', 'is', 'are', 'be', 'been', 'not', 'than', 'so',
}


def _is_narrative_false_positive(show_as: str) -> str | None:
    """Return a reason string if `show_as` looks like narrative prose, not a
    genuine definiendum; None if it's an acceptable candidate.

    Checks, in order: an embedded connector word (a real definiendum is a
    noun phrase, never containing its own "means"/"includes"); an embedded
    parenthetical relative clause (real OPC parenthetical glosses are
    appositive noun/abbreviation phrases, e.g. "OBU (offshore banking
    unit)", never relative clauses); a known non-term opening phrase; and a
    dangling function-word ending on multi-word candidates only -- single-word
    candidates are exempt because real single-word terms in this corpus
    ("will", "and", "for") would otherwise be rejected.
    """
    if _EMBEDDED_CONNECTOR_RE.search(show_as):
        return 'embedded-connector'
    if _EMBEDDED_RELATIVE_RE.search(show_as):
        return 'embedded-relative'
    if _STOP_OPENER_RE.match(show_as):
        return 'stop-opener'
    tokens = show_as.split()
    if len(tokens) >= 2:
        last_tok = tokens[-1].strip('()[]{}.,;:').lower()
        if last_tok.isalpha() and last_tok in _DANGLING_FUNCTION_WORDS:
            return f'dangling:{last_tok}'
    return None


# Character class for an unquoted definiendum. Real OPC definienda routinely
# contain parenthetical glosses ("ABN (Australian Business Number)") and
# asterisk-marked cross-referenced terms ("*entity") -- confirmed against the
# live corpus 2026-07-12 (A New Tax System (Australian Business Number) Act
# 1999 s.41). Digits included for definienda like "Part 4A". No enclosing
# brackets here -- each usage site wraps this in [...] so Task 4's relational
# pattern can reuse it verbatim.
_DEFINIENDUM_CHARS = r"A-Za-z0-9\s\-\(\)\*"

# List-form definition: "X means:" (definition body in following block elements)
# Captures everything before the trailing "means:" as the definiendum.
_LIST_DEF_COLON_RE = re.compile(r'^(.+?)\s+means\s*:$', re.IGNORECASE)

_CONTENT_TAG   = f"{AKN_TAG}content"
_INTRO_TAG     = f"{AKN_TAG}intro"
_PARA_TAG      = f"{AKN_TAG}paragraph"
_BLOCKLIST_TAG = f"{AKN_TAG}blockList"

_DEF_PATTERNS = [
    # "X" means/includes Y  — quoted definiendum
    re.compile(r'^"([^"]+)"\s+(means|includes?)\s+(.*)', re.DOTALL | re.IGNORECASE),
    # "X" has the meaning given by / has the same meaning as
    re.compile(r'^"([^"]+)"\s+(has the (?:same )?meaning (?:given by|as))\s+(.*)', re.DOTALL | re.IGNORECASE),
    # X, in relation to Y, means/includes Z — relational definition (DD 1.5 form)
    re.compile(
        rf'^([A-Za-z][{_DEFINIENDUM_CHARS}]{{1,60}}?),\s+in relation to\s+[^,]{{1,60}},\s+(means|includes?)\s+(.*)',
        re.DOTALL | re.IGNORECASE
    ),
    # X means/includes Y — unquoted definiendum (italicised in DOCX -> plain text)
    re.compile(rf'^([A-Za-z][{_DEFINIENDUM_CHARS}]{{1,60}}?)\s+(means|includes?)\s+(.*)', re.DOTALL | re.IGNORECASE),
    # X has the meaning given by / has the same meaning as — unquoted form
    re.compile(rf'^([A-Za-z][{_DEFINIENDUM_CHARS}]{{1,60}}?)\s+(has the (?:same )?meaning (?:given by|as))\s+(.*)', re.DOTALL | re.IGNORECASE),
]


def _term_eid(show_as: str) -> str:
    """Derive TLCTerm eId from showAs text: lowercase, kebab-case, strip punctuation."""
    slug = re.sub(r'[^a-z0-9]+', '-', show_as.lower()).strip('-')
    return f"term-{slug}"


def _is_definition_section(section_el: etree._Element) -> bool:
    for heading in section_el.findall(f"{AKN_TAG}heading"):
        if _DEF_HEADING_RE.search("".join(heading.itertext())):
            return True
    return False


def _process_p(
    p_el: etree._Element,
    registry: dict[str, str],
) -> int:
    """Try to inject <term> + <def> into a single <p>. Returns 1 if injected, 0 otherwise.

    Handles both plain-text <p> and mixed-content <p> (e.g. with <i>/<b> children from
    inline formatting). For mixed content, text is reconstructed via itertext(); on match,
    inline children are cleared before rebuilding with <term>/<def>.
    """
    children = list(p_el)
    if children:
        text = "".join(p_el.itertext()).strip()
    else:
        text = p_el.text
    if not text:
        return 0

    if _STOP_DEFINIENDUM.match(text.strip()):
        return 0

    stripped = text.strip()
    for pattern in _DEF_PATTERNS:
        m = pattern.match(stripped)
        if m:
            prefix_before_connector = stripped[:m.start(2)]
            if _FALSE_CONNECTOR_TAIL_RE.search(prefix_before_connector):
                continue  # "does not include/mean" -- not a real definition
            show_as = m.group(1).strip()
            if _is_narrative_false_positive(show_as):
                continue  # narrative prose, not a real definiendum
            connector = m.group(2).strip()
            definiens = m.group(3).strip()
            eid = _term_eid(show_as)
            registry[eid] = show_as

            original = m.group(0)
            quoted = original.startswith('"')

            # Clear element (works for both plain text and mixed content)
            p_el.text = None
            for child in list(p_el):
                p_el.remove(child)

            term_el = etree.SubElement(p_el, f"{AKN_TAG}term")
            term_el.set("refersTo", f"#{eid}")
            term_el.text = f'"{show_as}"' if quoted else show_as
            term_el.tail = f" {connector} "
            def_el = etree.SubElement(p_el, f"{AKN_TAG}def")
            def_el.text = definiens
            return 1

    return 0


def inject_terms(root: etree._Element) -> tuple[dict[str, str], int]:
    """Walk definition sections; inject <term>/<def>; return (registry, count).

    Must be called BEFORE inject_refs so p_el.text is still a raw string.
    """
    registry: dict[str, str] = {}
    count = 0

    for section_el in root.iter(_SECTION_TAG):
        if not _is_definition_section(section_el):
            continue
        for p_el in section_el.iter(_P_TAG):
            parent = p_el.getparent()
            if parent is not None and parent.tag in {_HEADING_TAG, f"{AKN_TAG}num"}:
                continue
            count += _process_p(p_el, registry)

    return registry, count


def inject_list_defs(
    root: etree._Element,
    registry: dict[str, str],
) -> int:
    """Detect 'X means:' list-form definitions and inject <term> + convert <content> to <intro>.

    Processes only definition sections (same gate as inject_terms).
    Mutates registry in place. Returns count of injected terms.
    """
    count = 0

    for section_el in root.iter(_SECTION_TAG):
        if not _is_definition_section(section_el):
            continue

        # Walk all <content> elements inside this section
        for content_el in list(section_el.iter(_CONTENT_TAG)):
            # Must have exactly one <p> child
            p_children = list(content_el)
            if len(p_children) != 1 or p_children[0].tag != _P_TAG:
                continue
            p_el = p_children[0]

            # Get text (handles plain or mixed content from inline formatting)
            if list(p_el):
                text = "".join(p_el.itertext()).strip()
            else:
                text = (p_el.text or "").strip()

            if not text:
                continue
            if _STOP_DEFINIENDUM.match(text):
                continue

            m = _LIST_DEF_COLON_RE.match(text)
            if not m:
                continue

            # Check parent has at least one following <paragraph> or <blockList> sibling
            parent = content_el.getparent()
            if parent is None:
                continue
            siblings = list(parent)
            try:
                idx = siblings.index(content_el)
            except ValueError:
                continue
            following = siblings[idx + 1:]
            if not any(c.tag in {_PARA_TAG, _BLOCKLIST_TAG} for c in following):
                continue

            # Extract definiendum — trim at first comma to strip qualifiers
            raw_definiendum = m.group(1).strip()
            show_as = raw_definiendum.split(",")[0].strip()
            eid = _term_eid(show_as)
            registry[eid] = show_as

            # Rename <content> -> <intro>
            content_el.tag = _INTRO_TAG

            # Rebuild <p>: inject <term> + keep " means:" as tail
            p_el.text = None
            for child in list(p_el):
                p_el.remove(child)
            term_el = etree.SubElement(p_el, f"{AKN_TAG}term")
            term_el.set("refersTo", f"#{eid}")
            term_el.text = show_as
            term_el.tail = " means:"

            count += 1

    return count
