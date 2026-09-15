from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from xml.etree import ElementTree as ET

from lxml import etree

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"\w+")
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

_MINOR_MIN_OVERLAP = 0.90     # near-identical => punctuation/artefact noise

_WP_MIN_TOKENS = 4  # \w-token minimum on either side; below -> wp_skipped
_WP_TOKEN = re.compile(r"\w+|[^\w\s]")
_WP_WORD = re.compile(r"\w+")

# §7: paragraph count (on either side) above which an unequal-length replace
# block skips pairwise best-match alignment and falls back to one whole-block
# classification. Alignment cost is O(min(n, m) * n * m); at the cap that is a
# few tens of thousands of comparisons per block, trivial, but a pathological
# block (a whole schedule netted into one replace opcode) must not blow up
# audit runtime across ~3,076 Acts.
_WP_ALIGN_MAX_PARAS = 40


@dataclass
class WithinParaResult:
    kind: str
    docx_word_tokens: int
    akn_word_tokens: int
    dropped: list[str]
    inserted: list[str]


def _wp_diff_words(dw: list[str], aw: list[str]) -> tuple[list[str], list[str]]:
    """\\w tokens on one side and not the other -- original case, document order.

    Matching is casefolded so "Minister"/"minister" is not reported as a diff.
    """
    sm = SequenceMatcher(
        a=[t.casefold() for t in dw], b=[t.casefold() for t in aw], autojunk=False
    )
    dropped: list[str] = []
    inserted: list[str] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("delete", "replace"):
            dropped.extend(dw[i1:i2])
        if tag in ("insert", "replace"):
            inserted.extend(aw[j1:j2])
    return dropped, inserted


def within_para_classify(dtext: str, atext: str) -> WithinParaResult:
    from collections import Counter

    dt = _WP_TOKEN.findall(dtext)
    at = _WP_TOKEN.findall(atext)
    dw = [t for t in dt if _WP_WORD.fullmatch(t)]
    aw = [t for t in at if _WP_WORD.fullmatch(t)]
    n_dw, n_aw = len(dw), len(aw)

    if n_dw < _WP_MIN_TOKENS or n_aw < _WP_MIN_TOKENS:
        return WithinParaResult("wp_skipped", n_dw, n_aw, [], [])

    if [t.casefold() for t in dt] == [t.casefold() for t in at]:
        return WithinParaResult("wp_clean", n_dw, n_aw, [], [])

    cd = Counter(t.casefold() for t in dw)
    ca = Counter(t.casefold() for t in aw)
    dropped, inserted = _wp_diff_words(dw, aw)

    if cd == ca:
        # identical \w multiset: either only punctuation/whitespace tokens
        # differ, or the \w tokens are in a different order.
        if [t.casefold() for t in dw] == [t.casefold() for t in aw]:
            return WithinParaResult("wp_punct", n_dw, n_aw, [], [])
        return WithinParaResult("wp_word_reorder", n_dw, n_aw, [], [])

    if all(ca[t] <= cd[t] for t in ca) and sum(ca.values()) < sum(cd.values()):
        return WithinParaResult("wp_word_drop", n_dw, n_aw, dropped, [])
    if all(cd[t] <= ca[t] for t in cd) and sum(cd.values()) < sum(ca.values()):
        return WithinParaResult("wp_word_insert", n_dw, n_aw, [], inserted)
    return WithinParaResult("wp_garble", n_dw, n_aw, dropped, inserted)


def _wp_para_overlap(a: str, b: str) -> float:
    """Casefolded \\w-token overlap coefficient, for best-match pairing.

    Same tokeniser and casefold convention as ``_wp_diff_words`` /
    ``within_para_classify`` (``_WP_WORD``, ``.casefold()``), kept separate
    from ``_overlap`` above (which lowercases via ``_TOKEN``) so the
    within-paragraph layer's notion of "similar" stays internally consistent.
    """
    from collections import Counter

    ta = [t.casefold() for t in _WP_WORD.findall(a)]
    tb = [t.casefold() for t in _WP_WORD.findall(b)]
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    ca, cb = Counter(ta), Counter(tb)
    inter = sum((ca & cb).values())
    return inter / max(len(ta), len(tb))


def _align_replace_block(docx_sub: list[str], akn_sub: list[str]) -> list[WithinParaResult]:
    """Best-match align an unequal-length ``replace`` block, then classify.

    ``docx_sub``/``akn_sub`` are the paragraphs spanned by one difflib
    ``replace`` opcode where the two sides have different paragraph counts
    (``compare()`` already handles the equal-length case positionally). No
    paragraph in ``docx_sub`` string-equals any paragraph in ``akn_sub`` --
    if one did, the outer ``SequenceMatcher`` would have carved it out as its
    own ``equal`` opcode -- so alignment here has to be similarity-based, not
    exact-match.

    Method: score every (docx paragraph, akn paragraph) pair by casefolded
    \\w-token overlap (``_wp_para_overlap``), then greedily take the
    highest-scoring remaining pair, remove both sides, and repeat. This
    always produces exactly ``min(len(docx_sub), len(akn_sub))`` pairs --
    each round removes one row and one column, so the loop only stops when
    one side is exhausted -- leaving the excess paragraphs on the longer side
    unmatched, even when every score is 0 (a genuine wholesale rewrite: nothing
    matches well, but the forced pairs still classify, typically ``wp_garble``,
    rather than being silently dropped). Ties are broken deterministically by
    the lowest (docx index, akn index) pair, so the result is stable across
    runs for the same input.

    Unmatched docx paragraphs report ``wp_word_drop``, unmatched akn
    paragraphs ``wp_word_insert``, in both cases with the *whole* paragraph as
    the token list (there is no counterpart to diff against).

    Above ``_WP_ALIGN_MAX_PARAS`` paragraphs on either side, pairwise scoring
    is skipped (cost is quadratic-ish in block size) and the whole block is
    classified as one joined-string comparison, tagged ``wp_block_skipped`` --
    a marker distinct from ``wp_skipped`` (too few \\w tokens to compare)
    so the two "no fine-grained answer" reasons aren't conflated downstream.
    """
    n_d, n_a = len(docx_sub), len(akn_sub)

    if n_d > _WP_ALIGN_MAX_PARAS or n_a > _WP_ALIGN_MAX_PARAS:
        base = within_para_classify(" ".join(docx_sub), " ".join(akn_sub))
        return [
            WithinParaResult(
                "wp_block_skipped",
                base.docx_word_tokens,
                base.akn_word_tokens,
                base.dropped,
                base.inserted,
            )
        ]

    scores = [[_wp_para_overlap(d, a) for a in akn_sub] for d in docx_sub]
    rd, ra = set(range(n_d)), set(range(n_a))
    pairs: list[tuple[int, int]] = []
    while rd and ra:
        best_score = -1.0
        best_i = best_j = -1
        for i in sorted(rd):
            for j in sorted(ra):
                if scores[i][j] > best_score:
                    best_score, best_i, best_j = scores[i][j], i, j
        pairs.append((best_i, best_j))
        rd.discard(best_i)
        ra.discard(best_j)
    pairs.sort()

    results = [within_para_classify(docx_sub[i], akn_sub[j]) for i, j in pairs]
    for i in sorted(rd):
        toks = _WP_WORD.findall(docx_sub[i])
        results.append(WithinParaResult("wp_word_drop", len(toks), 0, toks, []))
    for j in sorted(ra):
        toks = _WP_WORD.findall(akn_sub[j])
        results.append(WithinParaResult("wp_word_insert", 0, len(toks), [], toks))
    return results


def normalise(s: str) -> str:
    return _WS.sub(" ", s).strip()


def _tokens(s: str) -> list[str]:
    return _TOKEN.findall(s.lower())


def _overlap(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    from collections import Counter
    ca, cb = Counter(ta), Counter(tb)
    inter = sum((ca & cb).values())
    return inter / max(len(ta), len(tb))


def _same_multiset(a: str, b: str) -> bool:
    from collections import Counter
    return Counter(_tokens(a)) == Counter(_tokens(b))


def akn_paragraphs(root: etree._Element) -> list[str]:
    out: list[str] = []
    meta = {f"{{{AKN_NS}}}meta"}
    for el in root.iter():
        if el.tag not in (f"{{{AKN_NS}}}p", f"{{{AKN_NS}}}heading"):
            continue
        anc = el.getparent()
        skip = False
        while anc is not None:
            if anc.tag in meta:
                skip = True
                break
            anc = anc.getparent()
        if skip:
            continue
        text = normalise("".join(el.itertext()))
        if text:
            out.append(text)
    return out


def docx_paragraphs(paths: list[Path]) -> list[str]:
    w_t, w_tab, w_br = f"{_W_NS}t", f"{_W_NS}tab", f"{_W_NS}br"
    w_nbh = f"{_W_NS}noBreakHyphen"
    out: list[str] = []
    for path in paths:
        with zipfile.ZipFile(path) as z:
            doc = ET.fromstring(z.read("word/document.xml"))
        for p in doc.iter(f"{_W_NS}p"):
            parts: list[str] = []
            for node in p.iter():
                if node.tag == w_t:
                    parts.append(node.text or "")
                elif node.tag == w_nbh:
                    # non-breaking hyphen carries no <w:t> text; without this it
                    # is dropped and "non-operative" collapses to "nonoperative",
                    # merging two tokens. AKN keeps the hyphen, so every
                    # hyphenated compound would otherwise read as a divergence.
                    parts.append("-")
                elif node.tag in (w_tab, w_br):
                    # tabs and line breaks are word boundaries; emit a space so
                    # "1.<tab>This" does not collapse to "1.This" and a <br/>
                    # between words does not merge tokens
                    parts.append(" ")
            text = normalise("".join(parts))
            if text:
                out.append(text)
    return out


@dataclass
class Divergence:
    kind: str
    docx_span: tuple[int, int]
    akn_span: tuple[int, int]
    docx_text: str
    akn_text: str
    within_para: list[WithinParaResult] = field(default_factory=list)


def _classify_replace(dtext: str, atext: str) -> str:
    """Classify a difflib `replace` opcode into a divergence kind.

    Order is load-bearing:

    1. Identical lowercased ``\\w+`` token *sequence* => ``minor``. The two sides
       differ only in punctuation or whitespace; nothing was reordered or lost.
       (Deviation from the task-2 brief reference, which labelled every
       same-multiset replace ``reorder`` and so failed
       ``test_compare_minor_divergence_below_reorder_threshold``. Judged correct
       at review; kept.)
    2. Identical token multiset (different sequence) => ``reorder``.
    3. Strict token-subset (every AKN token present in the DOCX with at least the
       same count, and strictly fewer tokens overall) => ``drop_text``. Checked
       ahead of the overlap thresholds so a small real text loss is not scattered
       into ``minor``/``reorder``; ``drop_text`` is the audit's highest-stakes
       category (feeds the Task 4 go/no-go).
    4. Overlap >= ``_MINOR_MIN_OVERLAP`` => ``minor`` (punctuation/artefact noise,
       or one stray enumerator token against an otherwise near-identical line).
    5. Otherwise (low overlap, no subset relationship) => ``drop_text``: garbled,
       substituted or wholesale-rewritten text, surfaced rather than buried in
       ``minor``.

    ``reorder`` is only ever returned from step 2 (exact same token multiset).
    The former "overlap >= 0.98 => reorder" fallback classified as ``reorder``
    when the two sides had *different* multisets and nothing was actually
    transposed -- a single stray enumerator token in ~200 was enough. Every
    corpus-wide residual ``reorder`` arrived that way, so the fallback now routes
    to ``minor`` (real losses are already caught by the step-3 subset check).
    """
    from collections import Counter

    dt, at = _tokens(dtext), _tokens(atext)
    if dt == at:
        return "minor"

    cd, ca = Counter(dt), Counter(at)
    if cd == ca:
        return "reorder"

    if ca and all(ca[t] <= cd[t] for t in ca) and sum(ca.values()) < sum(cd.values()):
        return "drop_text"

    ov = _overlap(dtext, atext)
    if ov >= _MINOR_MIN_OVERLAP:
        return "minor"
    return "drop_text"


def compare(docx_paras: list[str], akn_paras: list[str]) -> list[Divergence]:
    sm = SequenceMatcher(a=docx_paras, b=akn_paras, autojunk=False)
    divs: list[Divergence] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        dtext = " ".join(docx_paras[i1:i2])
        atext = " ".join(akn_paras[j1:j2])
        if tag == "delete":
            divs.append(Divergence("drop_para", (i1, i2), (j1, j2), dtext, ""))
        elif tag == "insert":
            divs.append(Divergence("spurious_para", (i1, i2), (j1, j2), "", atext))
        else:  # replace
            kind = _classify_replace(dtext, atext)
            div = Divergence(kind, (i1, i2), (j1, j2), dtext, atext)
            if i2 - i1 == j2 - j1:
                div.within_para = [
                    within_para_classify(docx_paras[i1 + k], akn_paras[j1 + k])
                    for k in range(i2 - i1)
                ]
            else:
                div.within_para = _align_replace_block(
                    docx_paras[i1:i2], akn_paras[j1:j2]
                )
            divs.append(div)
    return divs
