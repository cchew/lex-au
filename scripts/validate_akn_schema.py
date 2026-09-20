"""Validate corpus AKN XML against the Akoma Ntoso 3.0 XSD (strict and lenient).

Read-only measurement tool. Not wired into spot_check / validate_akn — that is a
Phase 3 decision informed by this baseline.
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
from lxml import etree

_NS_RE = re.compile(r"\{[^}]*\}")

_COBALT_XSD = Path(sys.prefix) / "lib" / f"python3.{sys.version_info.minor}" / "site-packages" / "cobalt" / "xsd"

def _load_schema(xsd_path: Path) -> etree.XMLSchema:
    return etree.XMLSchema(etree.parse(str(xsd_path)))

def validate_one(xml_path: Path, xsd_path: Path) -> tuple[bool, list[str]]:
    schema = _load_schema(xsd_path)
    doc = etree.parse(str(xml_path))
    if schema.validate(doc):
        return True, []
    return False, [f"{e.line}:{e.type_name}: {e.message}" for e in schema.error_log]

def _signature(msg: str) -> str:
    """Bucket key from a "line:type: message" string.

    AKN validation messages embed the full Akoma Ntoso namespace URI
    (``{http://docs.oasis-open.org/...}``) in every element and attribute name.
    The naive ``split('.')`` bucketing collapses on the first ``.`` inside that
    URI, so every message keys to ``"<type> | Element '{http://docs"``. Strip the
    namespace, then key on ``(constraint type, offending element localname
    [+ attribute], distinguishing clause)`` per the P5 spec's
    "(element localname, constraint) signature".
    """
    _, _, rest = msg.partition(":")
    typ, _, raw_body = rest.partition(":")
    typ = typ.strip()
    body = _NS_RE.sub("", raw_body).strip()

    m = re.match(r"Element '([^']+)'(?:, attribute '([^']+)')?", body)
    if m:
        subject = f"{m.group(1)}@{m.group(2)}" if m.group(2) else m.group(1)
    else:
        subject = body.split(":", 1)[0][:40] or "?"

    if "Missing child element" in body:
        tail = f"missing-child:{_first_expected(body)}"
    elif "is required but missing" in body:
        am = re.search(r"attribute '([^']+)' is required but missing", body)
        tail = f"required-attr:{am.group(1)}" if am else "required-attr"
    elif "Duplicate key-sequence" in body:
        dm = re.search(r"identity-constraint '([^']+)'", body)
        tail = f"dup-key:{dm.group(1)}" if dm else "dup-key"
    elif "No precomputed value available" in body:
        tail = "no-precomputed-value"
    elif "not accepted by the pattern" in body:
        pm = re.search(r"pattern '(.+)'", body)
        tail = f"pattern:{pm.group(1)}" if pm else "pattern"
    elif "This element is not expected" in body:
        exp = _first_expected(body)
        tail = f"not-expected:{exp}" if exp else "not-expected"
    else:
        tail = body.split(".", 1)[0][:60]

    return f"{typ} | {subject} | {tail}"


def _first_expected(body: str) -> str:
    """First element name inside an 'Expected is one of ( ... )' clause, or ''."""
    if "Expected is one of" not in body:
        return ""
    after = body.split("Expected is one of", 1)[1]
    names = re.findall(r"[A-Za-z][\w-]*", after)
    return names[0] if names else ""

def validate_corpus(corpus_xml_dir: Path, xsd_path: Path) -> dict:
    schema = _load_schema(xsd_path)
    total = valid = 0
    by_sig: dict[str, dict] = {}
    for xml in sorted(corpus_xml_dir.glob("*.xml")):
        total += 1
        doc = etree.parse(str(xml))
        if schema.validate(doc):
            valid += 1
            continue
        for e in schema.error_log:
            sig = _signature(f"{e.line}:{e.type_name}: {e.message}")
            slot = by_sig.setdefault(sig, {"count": 0, "sample_file": xml.name, "message": e.message})
            slot["count"] += 1
    return {"total": total, "valid": valid, "invalid": total - valid,
            "by_signature": dict(sorted(by_sig.items(), key=lambda kv: -kv[1]["count"]))}

def load_whitelist(whitelist_path: Path) -> dict:
    """Load the manifest and return its {signature: entry} mapping.

    Tolerates either a bare {signature: entry, ...} mapping or the documented
    {"entries": {...}, ...metadata} shape (docs/xsd-whitelist.json uses the
    latter so it can carry a top-level _comment/generated/etc.).
    """
    data = json.loads(Path(whitelist_path).read_text())
    return data.get("entries", data) if isinstance(data, dict) else {}


def gate(corpus_xml_dir: Path, xsd_path: Path, whitelist_path: Path) -> tuple[bool, list[str]]:
    """Strict-with-whitelist gate.

    Passes iff every violation signature found by validate_corpus() is a key
    in the whitelist manifest AND its observed count does not exceed that
    entry's ``max_entries`` ceiling. Returns (passed, failing_signatures) --
    failing_signatures lists, in validate_corpus's by-count-descending order,
    every signature that is either absent from the manifest (a regression or
    a new defect class) or present but over its ceiling (a regression within
    a known-partial signature).
    """
    whitelist = load_whitelist(whitelist_path)
    result = validate_corpus(Path(corpus_xml_dir), Path(xsd_path))
    failing: list[str] = []
    for sig, info in result["by_signature"].items():
        entry = whitelist.get(sig)
        if entry is None:
            failing.append(sig)
            continue
        ceiling = entry.get("max_entries")
        if ceiling is not None and info["count"] > ceiling:
            failing.append(sig)
    return (len(failing) == 0, failing)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus-dir", type=Path, default=Path("corpus"))
    ap.add_argument("--out", type=Path, default=Path("docs/superpowers/2026-09-07-xsd-baseline.md"))
    args = ap.parse_args()
    xml_dir = args.corpus_dir / "xml"
    strict = validate_corpus(xml_dir, _COBALT_XSD / "akomantoso30.xsd")
    lenient = validate_corpus(xml_dir, _COBALT_XSD / "akomantoso30-lenient.xsd")
    lines = [f"# XSD baseline ({strict['total']} files) — 2026-09-07", ""]
    for name, r in (("strict", strict), ("lenient", lenient)):
        lines.append(f"## {name}: {r['valid']}/{r['total']} valid, {r['invalid']} invalid")
        for sig, s in list(r["by_signature"].items())[:20]:
            lines.append(f"- **{s['count']}x** `{sig}` — e.g. `{s['sample_file']}`  \n  _bug or intended?: TODO_")
        lines.append("")
    args.out.write_text("\n".join(lines))
    print(json.dumps({"strict": {k: strict[k] for k in ("total","valid","invalid")},
                      "lenient": {k: lenient[k] for k in ("total","valid","invalid")}}, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
