#!/usr/bin/env python3
"""Phase 1 spike: does Phase 0's legacy-template section detection already
make LibreOffice-converted `.doc` Acts parse correctly?

Converts each Act in the Task 1 sample via LibreOffice headless, runs the
resulting .docx through the existing, UNMODIFIED docx_reader.iter_paragraphs
+ AknBuilder pipeline, and measures the non-empty-<body> rate. No new
parsing code is added here -- see
docs/superpowers/specs/2026-07-20-legacy-doc-format-parsing-design.md,
Phase 1: "the point is measuring whether Phase 0's fix already suffices."

Usage:
    python scripts/spike_doc_conversion.py [--corpus-dir corpus] [--sample PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
from docx import Document
from lxml import etree

from lexau.builder import AknBuilder
from lexau.crawler import Crawler
from lexau.docx_reader import iter_paragraphs
from lexau.doc_convert import convert_doc_to_docx

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
NS = {"akn": AKN_NS}

_OLE2_MAGIC = b"\xd0\xcf\x11\xe0"
_ZIP_MAGIC = b"PK"


def _run_one(crawler: Crawler, act_name: str, doc_dir: Path, docx_dir: Path, xml_dir: Path) -> dict:
    row: dict = {"act_name": act_name}
    meta = crawler.fetch_metadata(act_name)
    if meta is None:
        row["error"] = "metadata not found"
        return row

    content = crawler.fetch_volume_bytes(meta, 0)
    if content is None:
        row["error"] = "fetch failed"
        return row

    row["fetched_bytes"] = len(content)
    if content.startswith(_ZIP_MAGIC):
        row["magic"] = "docx"
    elif content.startswith(_OLE2_MAGIC):
        row["magic"] = "doc"
    else:
        row["magic"] = "unknown"
        row["error"] = f"unrecognized format, first 4 bytes: {content[:4]!r}"
        return row

    if row["magic"] == "docx":
        # Population may have shifted since the 2026-07-13/14 log -- this
        # Act is no longer .doc-only. Parse directly, no conversion needed.
        docx_path = docx_dir / f"{meta.safe_name}.docx"
        docx_path.write_bytes(content)
    else:
        doc_path = doc_dir / f"{meta.safe_name}.doc"
        doc_path.write_bytes(content)
        converted = convert_doc_to_docx(doc_path, docx_dir)
        if converted is None:
            row["error"] = "libreoffice conversion failed"
            return row
        docx_path = converted

    doc = Document(str(docx_path))
    builder = AknBuilder(meta)
    for p in iter_paragraphs(doc):
        builder.add(p)
    xml, _report = builder.build_with_report({})

    sections = xml.findall(".//akn:section", NS)
    row["section_count"] = len(sections)
    row["non_empty_body"] = len(sections) > 0

    xml_path = xml_dir / f"{meta.safe_name}.xml"
    xml_path.write_bytes(etree.tostring(xml, pretty_print=True))
    row["xml_path"] = str(xml_path)
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-dir", default="corpus", type=Path)
    ap.add_argument("--sample", default=None, type=Path)
    args = ap.parse_args()

    sample_path = args.sample or (args.corpus_dir / "reports" / "doc-conversion-sample.json")
    sample = json.loads(sample_path.read_text())["sample"]

    work_dir = args.corpus_dir / "doc_spike"
    doc_dir, docx_dir, xml_dir = work_dir / "doc", work_dir / "docx", work_dir / "spike_xml"
    for d in (doc_dir, docx_dir, xml_dir):
        d.mkdir(parents=True, exist_ok=True)

    crawler = Crawler()
    results = []
    for entry in sample:
        print(f"[{entry['category']:<11}] {entry['act_name']}")
        row = _run_one(crawler, entry["act_name"], doc_dir, docx_dir, xml_dir)
        row["category"] = entry["category"]
        row["era"] = entry["era"]
        status = "OK" if row.get("non_empty_body") else f"FAIL ({row.get('error', 'empty body')})"
        print(f"  {status}")
        results.append(row)

    total = len(results)
    non_empty = sum(1 for r in results if r.get("non_empty_body"))
    rate = non_empty / total if total else 0.0

    error_counts: dict[str, int] = {}
    for r in results:
        if "error" in r:
            error_counts[r["error"]] = error_counts.get(r["error"], 0) + 1

    out = {
        "sample_size": total,
        "non_empty_body_count": non_empty,
        "non_empty_body_rate": rate,
        "error_counts": error_counts,
        "results": results,
    }
    out_path = args.corpus_dir / "reports" / "doc-conversion-spike-results.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))

    print(f"\nNon-empty <body> rate: {non_empty}/{total} ({rate:.0%})")
    print(f"Written to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
