from __future__ import annotations

import copy
import re
from dataclasses import dataclass
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
#
# NOTE: the {1,60}? length cap applied to this class everywhere it's used is
# now doing double duty -- it suppresses false positives on body text AND
# bounds regex backtracking cost across the 541-file corpus (this class
# includes \s, and the connector separator is also \s+, so whitespace is
# matchable by both the definiendum group and the separator). Don't widen
# the cap (e.g. to {1,120}) without weighing both effects.
_DEFINIENDUM_CHARS = r"A-Za-z0-9\s\-\(\)\*"

# List-form definition: "X means:" (definition body in following block elements).
# Group 1 captures the definiendum itself, bounded by the same character class +
# length cap as _DEF_PATTERNS (deliberately excludes comma, so it stops at one).
# Group 2 optionally captures a qualifier clause from the first comma onward,
# unbounded -- real qualifier-style list definienda can be long (confirmed real
# case, ITAA 1936: "the relevant holding company or holding companies, in
# relation to another company in relation to a year of income of that other
# company, means:" -- the true term is the 51-char part before the first comma;
# capping the *whole* span at 60 chars, tried first, wrongly rejected this).
#
# This pattern predates and shares no code with _DEF_PATTERNS/_DEFINIENDUM_CHARS,
# and its original unrestricted `.+?` on the whole span let narrative prose
# through too (e.g. a leading "(2A)" subsection number, or an "In this
# Division..." scoping clause) -- confirmed real instances, both in Corporations
# Act 2001, found 2026-07-13 alongside the _process_p narrative-FP guards.
# Anchoring group 1 to start with a letter rejects the leading-number case; the
# length cap on group 1 (comma-free Acts have no group 2 to hand off to) plus
# _is_narrative_false_positive (applied at the call site, same as _process_p)
# rejects the scoping-clause case.
_LIST_DEF_COLON_RE = re.compile(
    rf'^([A-Za-z][{_DEFINIENDUM_CHARS}]{{1,60}}?)(?:,.*?)?\s+means\s*:$',
    re.IGNORECASE | re.DOTALL,
)

_CONTENT_TAG   = f"{AKN_TAG}content"
_INTRO_TAG     = f"{AKN_TAG}intro"
_PARA_TAG      = f"{AKN_TAG}paragraph"
_BLOCKLIST_TAG = f"{AKN_TAG}blockList"
_DEF_TAG       = f"{AKN_TAG}def"

_DEF_PATTERNS = [
    # "X" means/includes Y  — quoted definiendum
    re.compile(r'^"(?P<term>[^"]+)"\s+(?P<connector>means|includes?)\s+(?P<definiens>.*)', re.DOTALL | re.IGNORECASE),
    # "X" has the meaning given by / has the same meaning as
    re.compile(r'^"(?P<term>[^"]+)"\s+(?P<connector>has the (?:same )?meaning (?:given by|as))\s+(?P<definiens>.*)', re.DOTALL | re.IGNORECASE),
    # X, in relation to Y, means/includes Z — relational definition (DD 1.5 form).
    # `qualifier` captures the WHOLE ", in relation to Y," clause verbatim
    # (comma-to-comma, original casing/spacing intact) so the caller can
    # splice it back into the rebuilt <term>/<def> as plain text unchanged --
    # previously unnamed/uncaptured entirely, so the clause vanished on
    # injection (wp_word_drop Bug 2, Task 1 triage 2026-09-08: confirmed real
    # content-meaning change in 4 independent Acts, turning a
    # context-qualified definition unconditional). Capturing the full clause,
    # rather than just Y and reconstructing the wrapper text around it in
    # _inject, avoids hardcoding "in relation to"'s casing/spacing and
    # matching the source exactly regardless (caught in code review,
    # 2026-09-16 — near-nil real-world impact given OPC drafting
    # conventions, but free to get right).
    re.compile(
        rf'^(?P<term>[A-Za-z][{_DEFINIENDUM_CHARS}]{{1,60}}?)(?P<qualifier>,\s+in relation to\s+[^,]{{1,60}},)\s+(?P<connector>means|includes?)\s+(?P<definiens>.*)',
        re.DOTALL | re.IGNORECASE
    ),
    # X means/includes Y — unquoted definiendum (italicised in DOCX -> plain text)
    re.compile(rf'^(?P<term>[A-Za-z][{_DEFINIENDUM_CHARS}]{{1,60}}?)\s+(?P<connector>means|includes?)\s+(?P<definiens>.*)', re.DOTALL | re.IGNORECASE),
    # X has the meaning given by / has the same meaning as — unquoted form
    re.compile(rf'^(?P<term>[A-Za-z][{_DEFINIENDUM_CHARS}]{{1,60}}?)\s+(?P<connector>has the (?:same )?meaning (?:given by|as))\s+(?P<definiens>.*)', re.DOTALL | re.IGNORECASE),
]


# Extended definition grammar (opt-in via ParserProfile.extended_definitions). State and territory
# drafting adds three shapes the Commonwealth patterns do not cover:
#   * qualifiers other than "in relation to": "X, for Part 6A, means ...", "X, for a government contract, means\u2014"
#   * more "meaning" forms: "has the meaning given in section 5", "has the meaning in section 5"
#   * signposts instead of definitions: "X see section 18.", "X, for Part 6A\u2014see section 59D(2)."
# A lead-in with nothing after the connector but a colon or dash ("X means:", "X means\u2014") is kept as
# a <def> holding just that mark, so complete_list_definitions can fold the list items in.
_EXT_QUAL = r"(?P<qual>\s*,\s+(?:in relation to|for|of|in|when|if)\s+[^,\u2014\u2013:]{1,120}?,?)?"
_EXT_CONN_FULL = (
    r"(?P<conn>means|includes?"
    r"|has\s+(?:the|a)\s+(?:same\s+)?meaning(?:\s+(?:given\s+by|given\s+in|affected\s+by|as\s+in|in|as))?"
    r"|see(?:\s+also)?|[\u2014\u2013,-]\s*see(?:\s+also)?)(?![A-Za-z])"
)
# Without a leading formatted run there is no reliable term boundary, so the plain-text fallback
# only trusts the explicit connectors (and the dash form of a signpost).
_EXT_CONN_PLAIN = (
    r"(?P<conn>means|includes?|has\s+the\s+(?:same\s+)?meaning(?:\s+(?:given\s+by|given\s+in|as\s+in|in|as))?"
    r"|[\u2014\u2013-]\s*see(?:\s+also)?)(?![A-Za-z])"
)
_EXT_QUAL_MULTI = (
    r"(?P<qual>\s*,\s+(?:in relation to|for|of|in|when|if|about|to|under|by)\s+[^\u2014\u2013:]{1,160}?)?"
)
_EXT_TAIL_RE = re.compile(
    rf"^{_EXT_QUAL_MULTI}\s*,?\s*{_EXT_CONN_FULL}\s*(?P<rest>.*)$", re.DOTALL | re.IGNORECASE
)
# A formatted term followed (after optional qualifiers) by only a dash or colon: a list lead-in with no connector.
_EXT_TAIL_BARE_RE = re.compile(rf"^{_EXT_QUAL_MULTI}\s*(?P<rest>[\u2014\u2013:])$", re.DOTALL)
_EXT_PLAIN_RE = re.compile(
    rf"^(?P<term>[A-Za-z][{_DEFINIENDUM_CHARS}]{{1,100}}?){_EXT_QUAL}\s*{_EXT_CONN_PLAIN}\s*(?P<rest>.*)$",
    re.DOTALL | re.IGNORECASE,
)
# Signpost terms can contain a comma ("collects, personal information\u2014see section 15"); the explicit
# dash-see connector is what makes the wider term class safe.
_EXT_PLAIN_SEE_RE = re.compile(
    r"^(?P<term>[A-Za-z][^\u2014\u2013:;]{1,170}?)\s*(?P<conn>[\u2014\u2013-]\s*see(?:\s+also)?)(?![A-Za-z])\s*(?P<rest>.*)$",
    re.DOTALL | re.IGNORECASE,
)
# A lead-in with no connector: "australian law\u2014", "subcontractor, in relation to a government contract\u2014"
# followed by list items. Only trusted when list items actually follow (checked by the caller) and the
# term does not open like ordinary prose.
_EXT_BARE_LEAD_IN_RE = re.compile(
    rf"^(?P<term>[A-Za-z][{_DEFINIENDUM_CHARS}]{{1,100}}?){_EXT_QUAL}\s*(?P<rest>[\u2014\u2013:])$",
    re.DOTALL | re.IGNORECASE,
)
_PROSE_OPENER_RE = re.compile(
    r"^(in\s+this|for\s+(?:this|the|a|an|each|any|example|instance|subsection|section|paragraph|part|division|schedule)|the\s+following|"
    r"subject\s+to|despite|if|where|a\s+person|an\s+entity|nothing|this|these|that|to|note|example|however|"
    r"unless|until|when|while)\b",
    re.IGNORECASE,
)
# A definiendum is a noun phrase; a finite verb means the candidate is a sentence ("a TPP code may do ...").
_SENTENCE_VERB_RE = re.compile(r"\b(may|must|shall|will|is|are|does|do|can|cannot)\b", re.IGNORECASE)
_LEAD_IN_MARKS = ":\u2014\u2013"


def _term_eid(show_as: str) -> str:
    """Derive TLCTerm eId from showAs text: lowercase, kebab-case, strip punctuation."""
    slug = re.sub(r'[^a-z0-9]+', '-', show_as.lower()).strip('-')
    return f"term-{slug}"


def _is_definition_section(section_el: etree._Element, def_heading_re: re.Pattern[str] | None = None) -> bool:
    pattern = def_heading_re or _DEF_HEADING_RE
    for heading in section_el.findall(f"{AKN_TAG}heading"):
        if pattern.search("".join(heading.itertext())):
            return True
    return False


# Simple "X means Y" / "X includes Y" shape only -- the structural fast path below
# doesn't attempt the quoted or relational ("X, in relation to Y, means Z") forms;
# those still go through _DEF_PATTERNS.
_STRUCTURAL_TAIL_RE = re.compile(r'^\s+(means|includes?)\s+(.*)', re.DOTALL | re.IGNORECASE)


def _leading_formatted_run_text(p_el: etree._Element) -> str | None:
    """Return the text of p_el's leading <i> (or <b><i>) run, if that's the only
    formatting shape present at the start. None otherwise.
    """
    children = list(p_el)
    if not children:
        return None
    first = children[0]
    if first.tag == f"{AKN_TAG}i":
        return (first.text or "").strip() or None
    if first.tag == f"{AKN_TAG}b" and len(first) == 1 and first[0].tag == f"{AKN_TAG}i":
        return (first[0].text or "").strip() or None
    return None


def _try_structural_match(
    p_el: etree._Element, stripped: str
) -> tuple[str, str, str, bool] | None:
    """Anchor the definiendum to p_el's leading italic/bold-italic run instead of
    guessing its extent via regex over the flattened text.

    Real OPC dictionary entries italicise exactly the definiendum. The AKN
    inline-formatting pass (v0.6.0) already isolates that run as a distinct <i>
    (or <b><i>) child before this pass runs, so when it's present it's a strictly
    more reliable boundary than _DEF_PATTERNS's regex guess. Confirmed real case
    (Corporations Act 2001): <b><i>lawyer</i></b> means a duly qualified legal
    practitioner and, in relation to a person, means such a practitioner acting
    for the person. -- _DEF_PATTERNS's relational pattern greedily captures
    "lawyer means a duly qualified legal practitioner and" as the definiendum
    (the clause itself contains "means"); anchoring to the italic run instead
    captures exactly "lawyer", with connector/definiens re-derived from
    immediately after that boundary (not reused from the mismatched regex match --
    reusing them would silently truncate the definiens, since they'd correspond to
    the wrong "means" in the sentence).

    Requires the connector immediately after the run (only whitespace between),
    which also naturally excludes exclusion clauses like "<i>lease</i> does not
    include ..." (confirmed real case, same Act) without a separate guard --
    "does not" breaks the immediate-adjacency requirement.

    Only handles the plain "X means Y" / "X includes Y" shape. Quoted and
    relational ("X, in relation to Y, means Z") forms still go through
    _DEF_PATTERNS, whether or not a leading run is present.
    """
    run_text = _leading_formatted_run_text(p_el)
    if not run_text or not stripped.startswith(run_text):
        return None
    rest = stripped[len(run_text):]
    m = _STRUCTURAL_TAIL_RE.match(rest)
    if not m:
        return None
    connector = m.group(1).strip()
    definiens = m.group(2).strip()
    return run_text, connector, definiens, False


def _try_extended_match(p_el: etree._Element, stripped: str) -> tuple[str, str, str] | None:
    """Extended grammar: (term, verbatim tail, definiens) or None.

    Prefers the leading formatted run as the term boundary (exact, no length cap). Falls back
    to a plain-text pattern restricted to explicit connectors, so a stray "see" in prose is never
    read as a definition.
    """
    run_text = _leading_formatted_run_text(p_el)
    if run_text and stripped.startswith(run_text):  # exact boundary from the source formatting
        rest = stripped[len(run_text):]
        em = _EXT_TAIL_RE.match(rest)
        if em and em.group("rest").strip():
            return run_text, rest[: em.start("rest")], em.group("rest").strip()
        bare = _EXT_TAIL_BARE_RE.match(rest)
        if bare and _has_following_list(p_el, allow_nested=True):
            return run_text, rest[: bare.start("rest")], bare.group("rest")
    pm = _EXT_PLAIN_RE.match(stripped)
    if pm and pm.group("rest").strip() and not _FALSE_CONNECTOR_TAIL_RE.search(stripped[: pm.start("conn")]):
        term = pm.group("term").strip()
        return term, stripped[pm.end("term"): pm.start("rest")], pm.group("rest").strip()
    sm = _EXT_PLAIN_SEE_RE.match(stripped)
    if (
        sm
        and sm.group("rest").strip()
        and not _PROSE_OPENER_RE.match(stripped)
        and not _SENTENCE_VERB_RE.search(sm.group("term"))
        and len(sm.group("term").split()) <= 25
    ):
        return sm.group("term").strip(), stripped[sm.end("term"): sm.start("rest")], sm.group("rest").strip()
    bm = _EXT_BARE_LEAD_IN_RE.match(stripped)
    if (
        bm
        and not _PROSE_OPENER_RE.match(stripped)
        and not _SENTENCE_VERB_RE.search(bm.group("term"))
        and _has_following_list(p_el)
    ):
        return bm.group("term").strip(), stripped[bm.end("term"):bm.start("rest")], bm.group("rest")
    return None


# "In this Act, X means ..." outside a definitions section: Act-wide scope, so the definition is an
# ordinary Act-wide term. The phrase stays in the text as the paragraph's plain-text prefix.
_SCOPE_ACT_RE = re.compile(
    r"^\s*(?:In|For)\s+(?:the\s+purposes\s+of\s+)?this\s+Act\s*,\s*(?:(?:an?|the)\s+)?", re.IGNORECASE
)


# "In this Act, a reference to X includes ..." is a rule of construction, not a definition.
_CONSTRUCTION_RE = re.compile(r"^(?:an?\s+|the\s+)?(?:references?|expressions?|words?)\s+(?:to|in)\b", re.IGNORECASE)

# Chapeau wording the scope-phrase pass must never read as a term: "In this Act, except where otherwise
# clearly intended:", "For the purposes of this Act, the following tables define:".
_CHAPEAU_TEXT_TERM_RE = re.compile(r"^(?:except|unless|the\s+following|following)\b", re.IGNORECASE)
# Definitions sections for the scope-phrase pass. "Meaning of X" sections are left out on purpose: there
# "In this Act, X means" is the definition itself and inject_terms does not tag it.
_SCOPE_PHRASE_DEF_HEADING_RE = re.compile(r"\b(definitions?|interpretations?|dictionary|defined\s+terms)\b", re.IGNORECASE)


def _in_quoted_structure(p_el: etree._Element) -> bool:
    """True inside an amendment's quoted replacement text, which belongs to another Act.

    Either a <quotedStructure> ancestor, or a paragraph that closes a quotation it never opened
    (an inserted definition whose opening quote sits in the instruction paragraph above).
    """
    if any(a.tag == f"{AKN_TAG}quotedStructure" for a in p_el.iterancestors()):
        return True
    text = "".join(p_el.itertext()).strip()
    return text.endswith(("\u201d", "\u201d.", "\u201d;", "\u201d,")) and "\u201c" not in text


def inject_scope_phrase_terms(root: etree._Element, registry: dict[str, str]) -> int:
    """Tag Act-wide definitions introduced by a scope phrase ("In this Act, personal information means...").

    Anchors on the leading formatted run after the phrase when there is one; otherwise accepts the
    plain-text shape, which the phrase makes reliable. Skips paragraphs already tagged.
    """
    count = 0
    for p_el in root.iter(_P_TAG):
        parent = p_el.getparent()
        if parent is not None and parent.tag in {_HEADING_TAG, f"{AKN_TAG}num"}:
            continue
        if p_el.find(f"{AKN_TAG}term") is not None or _in_quoted_structure(p_el):
            continue
        stripped = "".join(p_el.itertext()).strip()
        m = _SCOPE_ACT_RE.match(stripped)
        if not m:
            continue
        if _in_definitions_unit(p_el, _SCOPE_PHRASE_DEF_HEADING_RE):
            continue
        prefix, remainder = stripped[: m.end()], stripped[m.end():]
        hit: tuple[str, str, str] | None = None

        run = None
        for child in p_el:
            if child.tag == f"{AKN_TAG}b" and len(child) == 1 and child[0].tag == f"{AKN_TAG}i":
                run = (child[0].text or "").strip()
            elif child.tag == f"{AKN_TAG}i":
                run = (child.text or "").strip()
            break
        if run and remainder.startswith(run):
            em = _EXT_TAIL_RE.match(remainder[len(run):])
            if em and em.group("rest").strip():
                hit = (run, remainder[len(run):][: em.start("rest")], em.group("rest").strip())
        if hit is None:
            pm = _EXT_PLAIN_RE.match(remainder)
            if (
                pm
                and pm.group("rest").strip()
                and not _FALSE_CONNECTOR_TAIL_RE.search(remainder[: pm.start("conn")])
                and len(pm.group("term").split()) <= 6
                and not _SENTENCE_VERB_RE.search(pm.group("term"))
            ):
                hit = (pm.group("term").strip(), remainder[pm.end("term"): pm.start("rest")], pm.group("rest").strip())
        if hit is None:
            # "For this Act, personal information\u2014" followed by list items that begin "means ...": the term has
            # no connector of its own, the first list item supplies it. Needs the list to follow.
            bm = _EXT_BARE_LEAD_IN_RE.match(remainder)
            if (
                bm
                and len(bm.group("term").split()) <= 6
                and not _SENTENCE_VERB_RE.search(bm.group("term"))
                and _has_following_list(p_el)
            ):
                hit = (bm.group("term").strip(), remainder[bm.end("term"): bm.start("rest")], bm.group("rest"))
        if (
            hit is None
            or _is_narrative_false_positive(hit[0])
            or _PROSE_OPENER_RE.match(hit[0])
            or _CONSTRUCTION_RE.match(hit[0])
            or _CHAPEAU_TEXT_TERM_RE.match(hit[0])
        ):
            continue
        _inject(p_el, hit[0], "", hit[2], False, registry, tail=hit[1], prefix=prefix)
        count += 1
    return count


# Locally scoped definitions: "In this section/Part/Division/Schedule, X means ..." or a formatted term opening
# a paragraph in an ordinary section. Formatted terms only -- plain text outside a definitions section is
# far too ambiguous (measured 67% precision against 100% for the formatted-term gate).
_SCOPE_LOCAL_RE = re.compile(
    r"^\s*(?:In|For)\s+(?:the\s+purposes\s+of\s+)?this\s+"
    r"(?P<kind>section|subsection|Part|Division|Subdivision|Chapter|Schedule)\s*,\s*(?:(?:an?|the)\s+)?",
    re.IGNORECASE,
)
_SCOPE_KIND_TAG = {
    "section": "section", "subsection": "subsection", "part": "part", "division": "division",
    "subdivision": "subDivision", "chapter": "chapter", "schedule": "hcontainer",
}


def _scope_container(p_el: etree._Element, kind: str | None) -> etree._Element | None:
    """The element a local definition applies to: the one the scope phrase names, else the nearest section."""
    wanted = _SCOPE_KIND_TAG.get((kind or "section").lower(), "section")
    fallback = None
    for anc in p_el.iterancestors():
        local = etree.QName(anc).localname
        if local == wanted and (wanted != "hcontainer" or anc.get("name") == "schedule"):
            return anc if anc.get("eId") else None
        if kind is None and local == "hcontainer" and anc.get("name") == "schedule" and anc.get("eId"):
            fallback = fallback if fallback is not None else anc
    return fallback


# Chapeau: a lead-in paragraph of its own ("In this item:", "In this Act, unless the contrary intention
# appears:") that sets the scope of the definitions listed after it. Commonwealth drafting puts the scope
# here far more often than inline. A target with any other comma clause ("For the purposes of this Act,
# the following tables define:") is still a scope lead-in, just not one we can trust: unrecognised.
_CHAPEAU_RE = re.compile(
    r"^(?:\(\w{1,6}\)\s*|\d{1,3}[A-Z]{0,2}\.\s+)?(?:In|For)\s+(?:the\s+purposes?\s+of\s+)?(?P<target>[^,:—–]{1,80}?)\s*"
    r"(?P<qual>,[^:—–]*)?[:—–]$",
    re.IGNORECASE,
)
# "In applying section 40-290 of the new Act (...) in relation to the asset, assume ...:" -- a conditional
# lead-in too long for _CHAPEAU_RE. Its terms belong to the application it describes, not the section.
_APPLYING_LEAD_RE = re.compile(
    r"^(?:\(\w{1,6}\)\s*|\d{1,3}[A-Z]{0,2}\.\s+)?(?:In|For\s+the\s+purposes?\s+of)\s+applying\b.*[:—–]$",
    re.IGNORECASE,
)
# Unrecognised targets that a Schedule or the instrument itself resolves: "In this Code:" inside the Schedule
# that is the Code, "In these Regulations:" in a regulations instrument.
_CODE_CHAPEAU_RE = re.compile(r"^(?:\(\w{1,6}\)\s*)?In\s+this\s+(Code|Law|scheme)\s*:$", re.IGNORECASE)
_REGS_CHAPEAU_RE = re.compile(
    r"^(?:\(\w{1,6}\)\s*)?In\s+these\s+Regulations\s*(?:,\s*unless\s+the\s+contrary\s+intention\s+appears\s*)?:$",
    re.IGNORECASE,
)
_REGS_NAME_RE = re.compile(r"(?:^|-)regulations?-\d{4}\b", re.IGNORECASE)
# Amending or repealing instruments carry a regulations-style name but are not the regulations themselves.
_AMENDING_NAME_RE = re.compile(r"amend|repeal|revo[ck]", re.IGNORECASE)
_CHAPEAU_QUAL_RE = re.compile(r"^,\s*(?:unless|except)\b", re.IGNORECASE)
_FORMULA_LEAD_RE = re.compile(r"(?:^|\s)where\s*[:—–]$", re.IGNORECASE)
_CHAPEAU_TARGETS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(rx + r"$", re.IGNORECASE), kind)
    for rx, kind in (
        (r"this\s+Act", "act"),
        (r"this\s+section", "section"),
        (r"this\s+regulation", "regulation"),
        (r"this\s+item", "item"),
        (r"this\s+clause", "clause"),
        (r"this\s+Part", "part"),
        (r"this\s+Division", "division"),
        (r"this\s+Subdivision", "subdivision"),
        (r"this\s+Chapter", "chapter"),
        (r"this\s+Schedule", "schedule"),
        (r"this\s+(?:subsection|subitem|subclause|subregulation|paragraph|subparagraph)", "subsection"),
        (r"(?:sub)?(?:sections?|items?|clauses?|regulations?|paragraphs?|subparagraphs?)\s*\(.*", "subsection"),
    )
)
# Ancestor that a chapeau kind names: (element localname, hcontainer @name values).
_CHAPEAU_CONTAINER: dict[str, tuple[str | None, frozenset[str]]] = {
    "section": ("section", frozenset()),
    "regulation": ("section", frozenset()),
    "item": (None, frozenset({"item", "clause"})),
    "clause": (None, frozenset({"item", "clause"})),
    "part": ("part", frozenset({"part"})),
    "division": ("division", frozenset({"division"})),
    "subdivision": ("subDivision", frozenset({"subDivision"})),
    "chapter": ("chapter", frozenset({"chapter"})),
    "schedule": (None, frozenset({"schedule"})),
}
_LIST_ITEM_TAGS = {_PARA_TAG, f"{AKN_TAG}subparagraph", _BLOCKLIST_TAG, f"{AKN_TAG}item"}
_NOTE_OPENER_RE = re.compile(r"^(?:Note|Example)s?\b", re.IGNORECASE)


@dataclass(frozen=True)
class Chapeau:
    kind: str
    raw: str


def _is_hcontainer(el: etree._Element, names: frozenset[str] | set[str]) -> bool:
    return etree.QName(el).localname == "hcontainer" and el.get("name") in names


def _chapeau_host(p_el: etree._Element) -> etree._Element | None:
    """The unit a chapeau search stays inside: the nearest section, Schedule item/clause, or Schedule."""
    for anc in p_el.iterancestors():
        if anc.tag == _SECTION_TAG or _is_hcontainer(anc, {"item", "clause", "schedule"}):
            return anc
    return None


def _in_list_item(p_el: etree._Element, host: etree._Element) -> bool:
    for anc in p_el.iterancestors():
        if anc is host:
            return False
        if anc.tag in _LIST_ITEM_TAGS:
            return True
    return False


def _shares_list_item(prev: etree._Element, p_el: etree._Element, host: etree._Element) -> bool:
    """True when prev's nearest list item also contains p_el."""
    for anc in prev.iterancestors():
        if anc is host:
            return False
        if anc.tag in _LIST_ITEM_TAGS:
            return p_el in anc.iterdescendants()
    return False


def _classify_chapeau(text: str) -> Chapeau | None:
    if _FORMULA_LEAD_RE.search(text):
        return Chapeau("formula", text)
    m = _CHAPEAU_RE.match(text)
    if not m:
        return Chapeau("unrecognised", text) if _APPLYING_LEAD_RE.match(text) else None
    if m.group("qual") and not _CHAPEAU_QUAL_RE.match(m.group("qual")):
        return Chapeau("unrecognised", text)
    target = " ".join(m.group("target").split())
    for rx, kind in _CHAPEAU_TARGETS:
        if rx.match(target):
            return Chapeau(kind, text)
    return Chapeau("unrecognised", text)


def _is_definition_entry(p_el: etree._Element, text: str) -> bool:
    """Another entry of the same definitions list (tagged or not), or a note on one."""
    return (
        p_el.find(f"{AKN_TAG}term") is not None
        or _leading_formatted_run_text(p_el) is not None
        or _NOTE_OPENER_RE.match(text) is not None
        or text[:1].islower()  # tail of the entry above, after its list: "who is approved under Division 4 ..."
        or _looks_like_new_definition(p_el)
    )


def _find_chapeau(p_el: etree._Element) -> Chapeau | None:
    """The lead-in that governs the definition in p_el, or None.

    Walks back through the preceding paragraphs of the same section / Schedule item / clause,
    stepping over list items, other definitions and notes. Ordinary prose ends the walk: the
    chapeau's list is over. A lead-in inside a list item ("(a) a person who:") introduces a
    sub-list, never a scope, so it is stepped over too.
    """
    host = _chapeau_host(p_el)
    if host is None:
        return None
    paras = [p for p in host.iter(_P_TAG) if p.getparent() is not None and p.getparent().tag not in {_HEADING_TAG, f"{AKN_TAG}num"}]
    try:
        idx = paras.index(p_el)
    except ValueError:
        return None
    for prev in reversed(paras[:idx]):
        if _in_list_item(prev, host):
            # A "where:" legend lead-in in the list item that holds the definition governs it.
            if _FORMULA_LEAD_RE.search(" ".join("".join(prev.itertext()).split())) and _shares_list_item(prev, p_el, host):
                return Chapeau("formula", "where:")
            continue
        text = " ".join("".join(prev.itertext()).split())
        if not text:
            continue
        chapeau = _classify_chapeau(text)
        if chapeau is not None:
            return _resolve_named_chapeau(chapeau, p_el) if chapeau.kind == "unrecognised" else chapeau
        if _is_definition_entry(prev, text):
            continue
        return None
    return None


def _resolve_named_chapeau(chapeau: Chapeau, p_el: etree._Element) -> Chapeau:
    """An unrecognised chapeau whose target the document itself identifies, else unchanged.

    "In this Code:" / "In this Law:" / "In this scheme:" inside a Schedule whose heading names that word is
    the Schedule. "In these Regulations:" in a regulations instrument is instrument-wide.
    """
    cm = _CODE_CHAPEAU_RE.match(chapeau.raw)
    if cm:
        schedule = next((a for a in p_el.iterancestors() if _is_hcontainer(a, {"schedule"})), None)
        heading = schedule.find(_HEADING_TAG) if schedule is not None else None
        # The Schedule is the Code only when its heading ends with the word ("National Credit Code").
        if heading is not None and re.search(
            rf"\b{cm.group(1)}[\s.,;:]*$", " ".join("".join(heading.itertext()).split()), re.IGNORECASE
        ):
            return Chapeau("schedule", chapeau.raw)
        return chapeau
    if _REGS_CHAPEAU_RE.match(chapeau.raw):
        name = p_el.getroottree().getroot().find(f".//{AKN_TAG}FRBRWork/{AKN_TAG}FRBRname")
        value = name.get("value") or "" if name is not None else ""
        if _REGS_NAME_RE.search(value) and not _AMENDING_NAME_RE.search(value):
            return Chapeau("act", chapeau.raw)
    return chapeau


def _chapeau_container(p_el: etree._Element, kind: str) -> etree._Element | None:
    """Nearest ancestor of the kind a chapeau names, never climbing out of a Schedule unless it names one.

    "In this section:" inside a Schedule clause is that clause: Code-style Schedules number their
    sections as clauses. Schedule items are not (modification Schedules quote another Act's sections).
    """
    tag, names = _CHAPEAU_CONTAINER[kind]
    for anc in p_el.iterancestors():
        if (tag is not None and etree.QName(anc).localname == tag) or (names and _is_hcontainer(anc, names)):
            return anc if anc.get("eId") else None
        if _is_hcontainer(anc, {"schedule"}):
            if kind == "section":
                unit = _chapeau_host(p_el)
                if unit is not None and _is_hcontainer(unit, {"clause"}) and unit.get("eId"):
                    return unit
            return None
    return None


def _default_container(p_el: etree._Element) -> etree._Element | None:
    """No phrase, no chapeau: the enclosing section; in a Schedule, the enclosing item or clause."""
    for anc in p_el.iterancestors():
        if anc.tag == _SECTION_TAG or _is_hcontainer(anc, {"item", "clause"}):
            return anc if anc.get("eId") else None
        if _is_hcontainer(anc, {"schedule"}):
            return None
    return None


def _in_definitions_unit(p_el: etree._Element, def_heading_re: re.Pattern[str] | None) -> bool:
    """True inside a definitions-headed section or Schedule (e.g. "Schedule 1—Dictionary").

    Schedule items and clauses headed "Definitions" are not checked: inject_terms never processes them
    under the Commonwealth profile, so the local pass is the only one that tags them (EPBC Sch 1 cl 2).
    """
    section = next((a for a in p_el.iterancestors(_SECTION_TAG)), None)
    if section is not None and _is_definition_section(section, def_heading_re):
        return True
    schedule = next((a for a in p_el.iterancestors() if _is_hcontainer(a, {"schedule"})), None)
    return schedule is not None and _is_definition_section(schedule, def_heading_re)


def _in_schedule(p_el: etree._Element) -> bool:
    return any(_is_hcontainer(a, {"schedule"}) for a in p_el.iterancestors())


def _bump(stats: dict[str, int] | None, key: str) -> None:
    if stats is not None:
        stats[key] = stats.get(key, 0) + 1


_CHAPEAU_SKIP_STAT = {
    "subsection": "skipped_subsection_scope",
    "formula": "skipped_formula",
    "unrecognised": "skipped_unrecognised_chapeau",
}


def inject_local_terms(
    root: etree._Element,
    registry: dict[str, str],
    def_heading_re: re.Pattern[str] | None = None,
    stats: dict[str, int] | None = None,
) -> int:
    """Tag locally scoped definitions outside definitions sections; returns the count tagged.

    Scope comes from, in order: an inline phrase ("In this Part, X means"), the chapeau the term is
    listed under ("In this item:"), then the enclosing section (Schedule: item or clause). Fail closed:
    a subsection/formula/unrecognised chapeau, or a Schedule term with no item or clause, is not tagged.
    """
    count = 0
    for p_el in root.iter(_P_TAG):
        parent = p_el.getparent()
        if parent is not None and parent.tag in {_HEADING_TAG, f"{AKN_TAG}num"}:
            continue
        if p_el.find(f"{AKN_TAG}term") is not None or _in_quoted_structure(p_el):
            continue
        stripped = "".join(p_el.itertext()).strip()
        if not stripped:
            continue
        m = _SCOPE_LOCAL_RE.match(stripped)
        kind = m.group("kind") if m else None
        prefix = stripped[: m.end()] if m else ""
        remainder = stripped[len(prefix):]

        # the leading formatted run must start right after the (optional) phrase
        run = None
        for child in p_el:
            if child.tag == f"{AKN_TAG}b" and len(child) == 1 and child[0].tag == f"{AKN_TAG}i":
                run = (child[0].text or "").strip()
            elif child.tag == f"{AKN_TAG}i":
                run = (child.text or "").strip()
            break
        if not run or not remainder.startswith(run):
            continue
        if not m and (p_el.text or "").strip():
            continue  # something other than the term opens the paragraph
        after = remainder[len(run):]
        hit = None
        em = _EXT_TAIL_RE.match(after)
        if em and em.group("rest").strip():
            hit = (after[: em.start("rest")], em.group("rest").strip())
        else:
            bare = _EXT_TAIL_BARE_RE.match(after)
            if bare and _has_following_list(p_el, allow_nested=True):
                hit = (after[: bare.start("rest")], bare.group("rest"))
        if hit is None:
            continue
        if (
            _is_narrative_false_positive(run)
            or _PROSE_OPENER_RE.match(run)
            or _CONSTRUCTION_RE.match(run)
            or _SENTENCE_VERB_RE.search(run)
            or len(run) > 170
        ):
            continue
        if m:
            container = _scope_container(p_el, kind)
            if container is None:
                continue
            if _is_definition_section(container, def_heading_re):
                continue  # an ordinary definitions section is handled by inject_terms
            eid = f"{_term_eid(run)}--{container.get('eId')}"
        else:
            if _in_definitions_unit(p_el, def_heading_re):
                continue  # a definitions section or Dictionary Schedule: inject_terms territory
            chapeau = _find_chapeau(p_el)
            if chapeau is not None and chapeau.kind in _CHAPEAU_SKIP_STAT:
                _bump(stats, _CHAPEAU_SKIP_STAT[chapeau.kind])
                continue
            if chapeau is not None and chapeau.kind == "act":
                eid = _term_eid(run)
                _bump(stats, "act_wide_via_chapeau")
            else:
                container = _chapeau_container(p_el, chapeau.kind) if chapeau else _default_container(p_el)
                if container is None:
                    if chapeau is not None:
                        _bump(stats, "skipped_chapeau_container_missing")
                    elif _in_schedule(p_el):
                        _bump(stats, "skipped_no_scope_in_schedule")
                    continue
                eid = f"{_term_eid(run)}--{container.get('eId')}"
        _inject(p_el, run, "", hit[1], False, registry, tail=hit[0], prefix=prefix, eid=eid)
        count += 1
    return count


def _has_following_list(p_el: etree._Element, allow_nested: bool = False) -> bool:
    """True when p_el is the last <p> of its <content> and list items (<paragraph>/<blockList>) follow
    that content, at that level or any enclosing one, up to the section."""
    content = p_el.getparent()
    if content is None or content.tag != _CONTENT_TAG or content[-1] is not p_el:
        return False
    # A lead-in inside a list item ("(a) personal information about:") introduces a sub-list,
    # not a definition; only section- or subsection-level lead-ins qualify.
    holder = content.getparent()
    if holder is None or (
        not allow_nested and holder.tag not in {_SECTION_TAG, f"{AKN_TAG}subsection", f"{AKN_TAG}hcontainer"}
    ):
        return False
    node = content
    while node is not None and node.tag != _SECTION_TAG:
        parent = node.getparent()
        if parent is None:
            return False
        sibs = list(parent)
        if any(c.tag in {_PARA_TAG, _BLOCKLIST_TAG} for c in sibs[sibs.index(node) + 1:]):
            return True
        node = parent
    return False


def _inject(
    p_el: etree._Element,
    show_as: str,
    connector: str,
    definiens: str,
    quoted: bool,
    registry: dict[str, str],
    qualifier: str | None = None,
    tail: str | None = None,
    prefix: str | None = None,
    eid: str | None = None,
) -> None:
    eid = eid or _term_eid(show_as)
    registry[eid] = show_as

    p_el.text = prefix or None
    for child in list(p_el):
        p_el.remove(child)

    term_el = etree.SubElement(p_el, f"{AKN_TAG}term")
    term_el.set("refersTo", f"#{eid}")
    term_el.text = f'"{show_as}"' if quoted else show_as
    if tail is not None:
        # Extended grammar: carry the exact source text between term and definiens
        # (" means ", ", for Part 6A\u2014see ", " see ") so nothing is reworded.
        term_el.tail = tail
    elif qualifier:
        # Relational definition ("X, in relation to Y, means Z") -- carry the
        # verbatim ", in relation to Y," clause forward as plain text so the
        # rebuilt <term>/<def> reads exactly the way the source DOCX did
        # (see _DEF_PATTERNS' Group 3 comment -- `qualifier` is the whole
        # clause, comma-to-comma, not reconstructed from a fixed template).
        # Kept out of <term> itself: Y qualifies the definiens, not the
        # definiendum, and folding it in would also change term_eid/the
        # registry key for what is otherwise the same defined term.
        term_el.tail = f"{qualifier} {connector} "
    else:
        term_el.tail = f" {connector} "
    def_el = etree.SubElement(p_el, f"{AKN_TAG}def")
    def_el.text = definiens


def _process_p(
    p_el: etree._Element,
    registry: dict[str, str],
    extended: bool = False,
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

    if extended:
        ext = _try_extended_match(p_el, stripped) if p_el.find(f"{AKN_TAG}term") is None else None
        if ext is not None and (len(ext[0]) <= 170) and not _is_narrative_false_positive(ext[0]) and not _PROSE_OPENER_RE.match(ext[0]):
            # Only the shapes the default grammar cannot express reach here first; plain
            # "X means Y" still prefers the default path below so its output is unchanged.
            if not _plain_default_shape(stripped, ext):
                _inject(p_el, ext[0], "", ext[2], False, registry, tail=ext[1])
                return 1

    structural = _try_structural_match(p_el, stripped)
    if structural is not None:
        show_as, connector, definiens, quoted = structural
        if not _is_narrative_false_positive(show_as):
            _inject(p_el, show_as, connector, definiens, quoted, registry)
            return 1
        # Falls through to the general pattern list below on the rare chance the
        # structural candidate itself looks like narrative prose -- keeps this
        # path no more permissive than the existing one, though no known real
        # case hits this branch.

    for pattern in _DEF_PATTERNS:
        m = pattern.match(stripped)
        if m:
            prefix_before_connector = stripped[:m.start('connector')]
            if _FALSE_CONNECTOR_TAIL_RE.search(prefix_before_connector):
                continue  # "does not include/mean" -- not a real definition
            show_as = m.group('term').strip()
            if _is_narrative_false_positive(show_as):
                continue  # narrative prose, not a real definiendum
            if extended and _PROSE_OPENER_RE.match(show_as):
                continue  # "Note State includes ...", "For example, ..." -- explanatory text, not a definition
            qualifier = m.groupdict().get('qualifier') or None
            connector = m.group('connector').strip()
            definiens = m.group('definiens').strip()
            original = m.group(0)
            quoted = original.startswith('"')
            _inject(p_el, show_as, connector, definiens, quoted, registry, qualifier)
            return 1

    return 0


def _plain_default_shape(stripped: str, ext: tuple[str, str, str]) -> bool:
    """True when the default grammar already handles this definition (so keep its exact output):
    a single space, then means/includes, then a space and body (no lead-in mark, no qualifier,
    no signpost, no 'given in')."""
    term, tail, definiens = ext
    return bool(re.fullmatch(r"\s+(means|includes?)\s+", tail, re.IGNORECASE)) and definiens[:1] not in _LEAD_IN_MARKS


_DICTIONARY_UNIT_NAMES = frozenset({"part", "division", "subDivision", "chapter"})
# "Definitions for this Part, Parts 42, 66, 145 and 147 ..." (CASR Dictionary Part 3).
_LIMITED_DICTIONARY_HEADING_RE = re.compile(
    r"\bfor\s+(?:this|these)\s+(?:Parts?|Divisions?|Subdivisions?|Subparts?|Chapters?)\b", re.IGNORECASE
)
# "In this Part, Parts 42, ...:" limits the unit; "In this Act:" / "In these Regulations:" does not.
_DICTIONARY_CHAPEAU_RE = re.compile(r"^(?:In|For(?:\s+the\s+purposes\s+of)?)\s+(?:this|these)\s+(\w+)", re.IGNORECASE)
_ACT_WIDE_CHAPEAU_WORDS = frozenset({"act", "regulations", "regulation", "code", "instrument", "ordinance", "rules", "law"})


def _is_dictionary_schedule(h: etree._Element) -> bool:
    """A Schedule headed exactly "Dictionary" (numbered or not) that is not an amending Schedule."""
    if h.get("name") != "schedule":
        return False
    heading = h.find(f"{AKN_TAG}heading")
    if heading is None or "".join(heading.itertext()).strip() != "Dictionary":
        return False
    if next(h.iter(f"{AKN_TAG}quotedStructure"), None) is not None:
        return False
    return not any(c.get("name") == "item" for c in h.iter(f"{AKN_TAG}hcontainer"))


def _nearest_dictionary_unit(p_el: etree._Element, stop: etree._Element) -> etree._Element:
    for anc in p_el.iterancestors():
        if anc is stop or (anc.tag == f"{AKN_TAG}hcontainer" and anc.get("name") in _DICTIONARY_UNIT_NAMES):
            return anc
    return stop


def _dictionary_unit_limited(unit: etree._Element) -> bool:
    """True if a Dictionary (or one of its Parts) says it applies to less than the whole Act."""
    heading = unit.find(f"{AKN_TAG}heading")
    if heading is not None and _LIMITED_DICTIONARY_HEADING_RE.search("".join(heading.itertext())):
        return True
    seen = 0
    for p_el in unit.iter(_P_TAG):
        parent = p_el.getparent()
        if parent is not None and parent.tag in {_HEADING_TAG, f"{AKN_TAG}num"}:
            continue
        if _nearest_dictionary_unit(p_el, unit) is not unit:
            continue  # a child Part's chapeau speaks for that Part only
        m = _DICTIONARY_CHAPEAU_RE.match("".join(p_el.itertext()).strip())
        if m:
            return m.group(1).lower() not in _ACT_WIDE_CHAPEAU_WORDS
        seen += 1
        if seen >= 3:
            break
    return False


def _limited_dictionary_units(schedule: etree._Element) -> set[etree._Element]:
    units = [schedule] + [h for h in schedule.iter(f"{AKN_TAG}hcontainer") if h.get("name") in _DICTIONARY_UNIT_NAMES]
    return {u for u in units if _dictionary_unit_limited(u)}


def _in_limited_unit(p_el: etree._Element, limited: set[etree._Element]) -> bool:
    return bool(limited) and any(a in limited for a in p_el.iterancestors())


def _definition_containers(
    root: etree._Element, include_schedules: bool, dictionary_schedules: bool = False
) -> list[tuple[etree._Element, set[etree._Element]]]:
    """(container, units inside it whose paragraphs must be skipped) for each definitions candidate."""
    containers: list[tuple[etree._Element, set[etree._Element]]] = [(s, set()) for s in root.iter(_SECTION_TAG)]
    schedules = [h for h in root.iter(f"{AKN_TAG}hcontainer") if h.get("name") == "schedule"]
    if include_schedules:
        containers += [(h, set()) for h in schedules]
    elif dictionary_schedules:
        containers += [(h, _limited_dictionary_units(h)) for h in schedules if _is_dictionary_schedule(h)]
    return containers


def inject_terms(
    root: etree._Element,
    def_heading_re: re.Pattern[str] | None = None,
    include_schedules: bool = False,
    extended: bool = False,
    dictionary_schedules: bool = False,
) -> tuple[dict[str, str], int]:
    """Walk definition sections; inject <term>/<def>; return (registry, count).

    Must be called BEFORE inject_refs so p_el.text is still a raw string.
    dictionary_schedules: also walk Schedules headed exactly "Dictionary" (see _is_dictionary_schedule).
    """
    registry: dict[str, str] = {}
    count = 0

    for section_el, limited in _definition_containers(root, include_schedules, dictionary_schedules):
        if not _is_definition_section(section_el, def_heading_re):
            continue
        for p_el in section_el.iter(_P_TAG):
            parent = p_el.getparent()
            if parent is not None and parent.tag in {_HEADING_TAG, f"{AKN_TAG}num"}:
                continue
            if _in_limited_unit(p_el, limited):
                continue
            count += _process_p(p_el, registry, extended)

    return registry, count


def inject_list_defs(
    root: etree._Element,
    registry: dict[str, str],
    def_heading_re: re.Pattern[str] | None = None,
    include_schedules: bool = False,
    extended: bool = False,
    dictionary_schedules: bool = False,
) -> int:
    """Detect 'X means:' list-form definitions and inject <term> + convert <content> to <intro>.

    Processes only definition sections (same gate as inject_terms).
    Mutates registry in place. Returns count of injected terms.
    """
    count = 0

    for section_el, limited in _definition_containers(root, include_schedules, dictionary_schedules):
        if not _is_definition_section(section_el, def_heading_re):
            continue

        # Walk all <content> elements inside this section
        for content_el in list(section_el.iter(_CONTENT_TAG)):
            # Must have exactly one <p> child
            p_children = list(content_el)
            if len(p_children) != 1 or p_children[0].tag != _P_TAG:
                continue
            p_el = p_children[0]
            if _in_limited_unit(p_el, limited):
                continue
            if extended and p_el.find(f"{AKN_TAG}term") is not None:
                continue  # already tagged by the extended grammar; complete_list_definitions folds it

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

            # Group 1 already excludes commas (any qualifier clause is the separate,
            # unbounded, discarded group 2 -- see _LIST_DEF_COLON_RE).
            show_as = m.group(1).strip()
            if _is_narrative_false_positive(show_as):
                continue  # narrative prose, not a real definiendum -- same guard as _process_p
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


def _find_qualifying_anchor(def_el: etree._Element) -> etree._Element | None:
    """Walk up from def_el's <p>'s <content> parent until a level is found
    whose immediate following siblings include a <paragraph> or <blockList>.

    Real corpus definitions nest at different depths -- some colon-terminated
    <def>s have their orphaned list content as direct siblings of their own
    <content> (level 0), others need one more level up to the enclosing
    <paragraph>'s siblings (level 1, the majority shape in the corpus --
    confirmed 2,649 of 3,136 real cases). The walk is not capped at level 1;
    it continues until it hits the enclosing <section> boundary.

    Returns the qualifying ancestor element (the node to walk forward from),
    or None if no such level exists.
    """
    p_el = def_el.getparent()
    if p_el is None or p_el.tag != _P_TAG:
        return None
    node = p_el.getparent()
    if node is None or node.tag != _CONTENT_TAG:
        return None
    while node is not None and node.tag != _SECTION_TAG:
        parent = node.getparent()
        if parent is None:
            return None
        siblings = list(parent)
        idx = siblings.index(node)
        following = siblings[idx + 1:]
        if any(c.tag in {_PARA_TAG, _BLOCKLIST_TAG} for c in following):
            return node
        node = parent
    return None


def _append_list_item_content(def_el: etree._Element, p_el: etree._Element) -> None:
    """Append one list item's rendered content (mixed text + inline markup)
    to def_el, deep-copying any child elements (<ref>, <i>, etc.) so already-
    applied markup from upstream passes survives.

    No synthetic numbering ("(a) ") is added -- real corpus list items already
    carry their own trailing punctuation ("; or", "; and", ".") and some (not
    all) embed their own inline numbering, so a <num>-derived prefix risks
    doubling it. A single space separates each item from what precedes it.
    """
    children = list(def_el)
    if children:
        last = children[-1]
        last.tail = (last.tail or "") + " " + (p_el.text or "")
    else:
        def_el.text = (def_el.text or "") + " " + (p_el.text or "")
    for child in p_el:
        def_el.append(copy.deepcopy(child))


def _looks_like_new_definition(item_p: etree._Element) -> bool:
    """True if item_p's own text matches a definition-start pattern, even
    though it hasn't been tagged with <term> yet.

    Real corpus gap, confirmed 2026-07-14 against bankruptcy-act-1966.xml:
    inject_list_defs requires exactly one <p> child per <content> before it
    will convert anything. When a definition's lead-in shares its <content>
    with an unrelated preceding sentence -- confirmed real case, 'relative,
    in relation to a person, means:' sits in the same <content> as 'For the
    purposes of paragraph (c)...' -- inject_list_defs skips it entirely, and
    it's never tagged. _collect_and_append_list_content's <term refersTo>
    check alone can't see this as a boundary, so this function re-applies
    inject_terms/inject_list_defs's own patterns and false-positive guards
    here, purely as a stop signal -- nothing gets tagged by this check, nor
    does it fix the underlying inject_list_defs gap (out of scope here; see
    the plan's Global Constraints).
    """
    text = "".join(item_p.itertext()).strip()

    list_def_match = _LIST_DEF_COLON_RE.match(text)
    if list_def_match and not _is_narrative_false_positive(list_def_match.group(1).strip()):
        return True

    for pattern in _DEF_PATTERNS:
        m = pattern.match(text)
        if not m:
            continue
        prefix_before_connector = text[:m.start('connector')]
        if _FALSE_CONNECTOR_TAIL_RE.search(prefix_before_connector):
            continue
        if _is_narrative_false_positive(m.group('term').strip()):
            continue
        return True

    return False


def _collect_and_append_list_content(
    def_el: etree._Element, anchor_el: etree._Element, nested: bool = False
) -> bool:
    """Walk anchor_el's following <paragraph>/<blockList> siblings in document
    order, appending each <content>'s <p> children (there can be more than
    one per <content> -- see the multi-<p> shape below) to def_el via
    _append_list_item_content, until a <p> is found that's either already
    tagged with <term refersTo> (the common case -- reliable because this
    function runs after inject_terms/inject_list_defs have swept the whole
    document, see complete_list_definitions' docstring in Task 3) OR looks
    like an untagged definition start per _looks_like_new_definition (the
    fallback for definitions inject_list_defs's own gate missed -- see that
    function's docstring).

    Iterates content_el.findall(_P_TAG), not .find() -- a single <content>
    can hold more than one <p> (confirmed real shape: bankruptcy-act-1966.xml's
    'relative' lead-in shares a <content> with an unrelated preceding
    sentence). Using .find() would silently see only the first <p> and miss
    a boundary sitting in the second.

    Returns True if any content was appended.
    """
    parent = anchor_el.getparent()
    siblings = list(parent)
    idx = siblings.index(anchor_el)
    appended = False
    for sib in siblings[idx + 1:]:
        if sib.tag not in {_PARA_TAG, _BLOCKLIST_TAG}:
            break
        stop = False
        # nested: also take the (i), (ii) items under each (a), which sit in <content> elements of
        # nested <paragraph>/<subparagraph> children (default keeps the Commonwealth behaviour).
        contents = list(sib.iter(_CONTENT_TAG)) if nested else sib.findall(_CONTENT_TAG)
        for content_el in contents:
            for item_p in content_el.findall(_P_TAG):
                if item_p.find(f"{AKN_TAG}term") is not None or _looks_like_new_definition(item_p):
                    stop = True
                    break
                _append_list_item_content(def_el, item_p)
                appended = True
            if stop:
                break
        if stop:
            break
    return appended


def complete_list_definitions(root: etree._Element, lead_ins: str = ":", nested: bool = False) -> int:
    """Find colon-terminated <def> elements and fold in their orphaned list
    content from following AKN siblings.

    Must run as the LAST step in builder.py's injection pipeline -- after
    inject_asterisk_refs, inject_quantities, inject_dates, inject_roles,
    inject_refs, and inject_note_refs. Two reasons, both load-bearing:

    1. Those five passes skip any element that already has child nodes (how
       each detects "not yet processed" -- see quantlinks.py/reflinks.py).
       Running this pass last means the list-item content it copies into
       <def> already carries whatever markup those passes added; running it
       first would give <def> children before those passes see it, and they'd
       silently skip it.
    2. _collect_and_append_list_content's term-boundary stop condition checks
       for <term refersTo> on the *next* definition. That's only reliable for
       definitions inject_terms/inject_list_defs actually tagged, which is
       true once they've swept the whole document, but NOT true mid-sweep (a
       list-form definition immediately following another list-form
       definition would not yet be tagged if this ran inline during that
       same sweep). Some real definitions are never tagged at all, for a
       separate reason unrelated to pipeline position -- confirmed real case,
       bankruptcy-act-1966.xml's "relative" sits in a <content> alongside an
       unrelated sentence, and inject_list_defs's "exactly one <p> per
       <content>" gate skips it regardless of when anything runs.
       _looks_like_new_definition (Task 2) is the fallback for that case --
       it doesn't depend on pipeline position at all, only on the untagged
       text itself looking like a definition start.

    Returns count of <def> elements completed.
    """
    count = 0
    for def_el in list(root.iter(_DEF_TAG)):
        text = "".join(def_el.itertext()).strip()
        if not text.endswith(tuple(lead_ins)):
            continue
        anchor = _find_qualifying_anchor(def_el)
        if anchor is None:
            continue
        if _collect_and_append_list_content(def_el, anchor, nested):
            count += 1
    return count
