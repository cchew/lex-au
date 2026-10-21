"""Sample newly tagged local / scope-phrase terms into a Markdown review checklist."""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lexau.termlinks import _SCOPE_ACT_RE, _SCOPE_LOCAL_RE  # noqa: E402

AKN = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
_MAX_TEXT = 700


def _text(el: etree._Element) -> str:
    return " ".join("".join(el.itertext()).split())


def _enclosing_heading(el: etree._Element) -> str:
    for anc in el.iterancestors():
        h = anc.find(f"{{{AKN}}}heading")
        if h is not None:
            num = anc.find(f"{{{AKN}}}num")
            label = (_text(num) + " ") if num is not None else ""
            return f"{label}{_text(h)}"
    return ""


def extract_terms(xml_path: Path) -> list[dict]:
    """Every <term> in a file, with scope classification."""
    root = etree.parse(str(xml_path)).getroot()
    out = []
    for term in root.iter(f"{{{AKN}}}term"):
        ref = (term.get("refersTo") or "").lstrip("#")
        p = term.getparent()
        if p is None or not ref:
            continue
        ptext = _text(p)
        if "--" in ref:
            container = ref.split("--", 1)[1]
            m = _SCOPE_LOCAL_RE.match(ptext)
            scope = f"local:{container}"
            has_phrase = m is not None
            kind = "local"
        else:
            container = ""
            has_phrase = _SCOPE_ACT_RE.match(ptext) is not None
            scope = "act-wide (scope phrase)" if has_phrase else "act-wide"
            kind = "act"
        out.append({
            "act": xml_path.stem,
            "ref": ref,
            "term": _text(term).strip('"'),
            "kind": kind,
            "scope": scope,
            "container": container,
            "has_phrase": has_phrase,
            "text": ptext[:_MAX_TEXT],
            "heading": _enclosing_heading(p),
        })
    return out


def new_terms(base_dir: Path, new_dir: Path) -> list[dict]:
    """Terms in new_dir that are local, or Act-wide via scope phrase, and absent from the baseline file."""
    found = []
    for path in sorted(new_dir.glob("*.xml")):
        base = base_dir / path.name
        seen = {(t["ref"], t["text"]) for t in extract_terms(base)} if base.exists() else set()
        for t in extract_terms(path):
            if (t["ref"], t["text"]) in seen:
                continue
            if t["kind"] == "local" or t["has_phrase"]:
                found.append(t)
    return sorted(found, key=lambda t: (t["act"], t["ref"], t["text"]))


def split_strata(terms: list[dict]) -> tuple[list[dict], list[dict]]:
    """(with scope phrase, local terms without a phrase -> default scope = containing section)."""
    phrased = [t for t in terms if t["has_phrase"]]
    unphrased = [t for t in terms if t["kind"] == "local" and not t["has_phrase"]]
    return phrased, unphrased


def sample(items: list[dict], n: int, seed: int) -> list[dict]:
    if n >= len(items):
        return list(items)
    return sorted(random.Random(seed).sample(items, n), key=lambda t: (t["act"], t["ref"], t["text"]))


def render(phrased: list[dict], unphrased: list[dict], n: int, seed: int, total: int) -> str:
    lines = [
        "# Local terms review",
        "",
        f"- Seed: {seed}",
        f"- New local / scope-phrase terms: {total}",
        f"- With scope phrase: {len(phrased)} (sampled {min(n, len(phrased))})",
        f"- Local, no scope phrase (default scope = containing section): {len(unphrased)} "
        f"(sampled {min(n, len(unphrased))})",
        "",
        "Mark per term: (a) genuine definition; (b1) Act-wide term mislabelled local; "
        "(b2) true scope narrower than extracted.",
    ]

    def block(title: str, items: list[dict]) -> None:
        lines.extend(["", f"## {title}", ""])
        for i, t in enumerate(items, 1):
            lines.extend([
                f"### {i}. {t['term']}  ({t['act']})",
                f"- Scope: `{t['scope']}`",
                f"- Section: {t['heading'] or '(none)'}",
                f"- Definition: {t['text']}",
                "- [ ] (a) genuine definition",
                "- [ ] (b1) Act-wide term mislabelled local",
                "- [ ] (b2) true scope narrower than extracted",
                "- Notes:",
                "",
            ])

    block("Stratum 1: terms with a scope phrase", phrased)
    block("Stratum 2: local terms without a scope phrase", unphrased)
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("baseline_xml_dir", type=Path)
    ap.add_argument("flags_on_xml_dir", type=Path)
    ap.add_argument("--n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path("local-terms-review.md"))
    args = ap.parse_args(argv)

    terms = new_terms(args.baseline_xml_dir, args.flags_on_xml_dir)
    phrased, unphrased = split_strata(terms)
    args.out.write_text(
        render(sample(phrased, args.n, args.seed), sample(unphrased, args.n, args.seed), args.n, args.seed, len(terms)),
        encoding="utf-8",
    )
    print(f"new={len(terms)} phrased={len(phrased)} unphrased={len(unphrased)} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
