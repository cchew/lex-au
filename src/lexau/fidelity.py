from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from xml.etree import ElementTree as ET

from lxml import etree

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
_WS = re.compile(r"\s+")
_TOKEN = re.compile(r"\w+")
_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

_REORDER_MIN_OVERLAP = 0.98   # same token multiset => reorder
_MINOR_MIN_OVERLAP = 0.90     # near-identical => punctuation/artifact noise


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
    4. Overlap >= ``_REORDER_MIN_OVERLAP`` => ``reorder``.
    5. Overlap >= ``_MINOR_MIN_OVERLAP`` => ``minor`` (punctuation/artefact noise).
    6. Otherwise (low overlap, no subset relationship) => ``drop_text``: garbled,
       substituted or wholesale-rewritten text, surfaced rather than buried in
       ``minor``.
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
    if ov >= _REORDER_MIN_OVERLAP:
        return "reorder"
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
            divs.append(Divergence(kind, (i1, i2), (j1, j2), dtext, atext))
    return divs
