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
    out: list[str] = []
    for path in paths:
        with zipfile.ZipFile(path) as z:
            doc = ET.fromstring(z.read("word/document.xml"))
        for p in doc.iter(f"{_W_NS}p"):
            text = normalise("".join(t.text or "" for t in p.iter(f"{_W_NS}t")))
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
            # Deviation from the task-2 brief reference snippet: the brief's
            # `compare()` classified any same-multiset replace as "reorder",
            # which makes brief test
            # `test_compare_minor_divergence_below_reorder_threshold` fail
            # (a punctuation-only rewrite has an identical token multiset but
            # is not a reorder). Guard first on an identical token *sequence*
            # so a pure punctuation/whitespace change is classified "minor".
            # Thresholds and the difflib opcode mapping are unchanged.
            # Flagged for Task 4 review.
            if _tokens(dtext) == _tokens(atext):
                kind = "minor"
            elif _same_multiset(dtext, atext):
                kind = "reorder"
            else:
                ov = _overlap(dtext, atext)
                if ov >= _REORDER_MIN_OVERLAP:
                    kind = "reorder"
                elif ov >= _MINOR_MIN_OVERLAP:
                    kind = "minor"
                elif _tokens(atext) and set(_tokens(atext)) <= set(_tokens(dtext)):
                    kind = "drop_text"
                else:
                    kind = "minor"
            divs.append(Divergence(kind, (i1, i2), (j1, j2), dtext, atext))
    return divs
