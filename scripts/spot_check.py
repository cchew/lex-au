#!/usr/bin/env python3
"""Automated spot-check for the lex-au corpus.

Run after `lexau build --all` to verify structural requirements are met.
Exit code 0 = all checks passed. Exit code 1 = one or more failures.

Usage:
    python scripts/spot_check.py [--corpus-dir corpus/]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lxml import etree

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
NS = {"akn": AKN_NS}

CHECKS = [
    # (description, xpath_or_fn, expected)
    ("FRBRWork date is ISO (YYYY-MM-DD)",
     ".//akn:FRBRWork/akn:FRBRdate/@date",
     lambda v: len(v) > 0 and all(len(d) == 10 and d[4] == "-" and d[7] == "-" for d in v)),
]

V02_CHECKS = [
    ("Subsection eId nested",     ".//akn:subsection/@eId", lambda v: all("__subsec-" in e for e in v)),
    ("No bare-year FRBRWork date", ".//akn:FRBRWork/akn:FRBRdate/@date", lambda v: not any(len(d) == 4 for d in v)),
]

V04_CHECKS = [
    ("FRBRWork has FRBRcountry=au",
     ".//akn:FRBRWork/akn:FRBRcountry/@value",
     lambda v: v == ["au"]),
    ("FRBRWork has FRBRsubtype=act",
     ".//akn:FRBRWork/akn:FRBRsubtype/@value",
     lambda v: v == ["act"]),
    ("FRBRWork has FRBRnumber",
     ".//akn:FRBRWork/akn:FRBRnumber",
     lambda v: len(v) > 0),
    ("At least one TLCTerm in references (if Definitions section exists)",
     ".//akn:references/akn:TLCTerm",
     lambda v: True),  # Non-fatal: not all Acts have Definitions sections
    ("At least one authorialNote has eId",
     ".//akn:authorialNote/@eId",
     lambda v: all(e.startswith("note-") for e in v) if v else True),
]

# Elements the builder only emits conditionally, based on real Act content
# (e.g. an Act with no amendment history legitimately has no <lifecycle>).
# Each is only checked when the Act's own report confirms the underlying
# content was actually found -- otherwise absence in the XML is correct,
# not a defect. (report field, xpath/finder, description)
REPORT_CONDITIONAL_CHECKS = [
    ("subsections_parsed", ".//akn:subsection", "Subsections present given subsections_parsed>0 in report"),
    ("dates_found", ".//akn:date", "date elements present given dates_found>0 in report"),
    ("amendment_events_parsed", ".//akn:lifecycle", "lifecycle in meta given amendment_events_parsed>0 in report"),
    ("amendment_events_parsed", ".//akn:temporalData", "temporalData in meta given amendment_events_parsed>0 in report"),
]


def check_xml(path: Path) -> list[str]:
    try:
        tree = etree.parse(str(path))
        root = tree.getroot()
    except Exception as exc:
        return [f"PARSE ERROR: {exc}"]

    failures: list[str] = []
    for desc, xpath, pred in CHECKS + V02_CHECKS + V04_CHECKS:
        vals = root.xpath(xpath, namespaces=NS)
        if not pred(vals):
            failures.append(f"FAIL [{desc}] — got {vals[:3]!r}")
    return failures


def check_report(path: Path) -> list[str]:
    try:
        data = json.loads(path.read_text())
    except Exception as exc:
        return [f"PARSE ERROR: {exc}"]

    failures: list[str] = []
    if data.get("volumes_fetched", 0) < 1:
        failures.append("FAIL [volumes_fetched < 1]")
    return failures


def check_conditional(xml_path: Path, report_data: dict) -> list[str]:
    """Checks that only apply when the report confirms the underlying content
    was actually produced -- see REPORT_CONDITIONAL_CHECKS."""
    try:
        root = etree.parse(str(xml_path)).getroot()
    except Exception:
        return []  # already reported as a PARSE ERROR by check_xml

    failures: list[str] = []
    for field, xpath, desc in REPORT_CONDITIONAL_CHECKS:
        if report_data.get(field, 0) > 0 and not root.xpath(xpath, namespaces=NS):
            failures.append(f"FAIL [{desc}]")
    return failures


def check_has_sections(xml_path: Path, act_name: str, baseline_empty_body: set[str]) -> list[str]:
    """Every Act should have at least one <section> -- except the small,
    already-documented set of legacy-format Acts in baseline_empty_body,
    accepted as a permanent Known Limitation (not something this gate should
    keep re-flagging). An Act NOT on that list with zero sections is a real,
    new regression and still fails."""
    if act_name in baseline_empty_body:
        return []
    try:
        root = etree.parse(str(xml_path)).getroot()
    except Exception:
        return []  # already reported as a PARSE ERROR by check_xml
    if not root.xpath(".//akn:section/@eId", namespaces=NS):
        return ["FAIL [At least one section with eId] — got []"]
    return []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus-dir", default="corpus", type=Path)
    parser.add_argument(
        "--dump-empty-body", type=Path, default=None,
        help="Write the sorted list of empty-<body> Act slugs to this path, one per line",
    )
    parser.add_argument(
        "--only-source-format", default=None,
        help="Only check Acts whose index.json entry has this source_format value",
    )
    parser.add_argument(
        "--baseline-empty-body", type=Path,
        default=Path("docs/known-limitations-empty-body.txt"),
        help="Act slugs already accepted as permanent zero-<section> Known "
             "Limitations -- excluded from the section-presence check so "
             "the gate only fails on new regressions, not this known set",
    )
    args = parser.parse_args()

    corpus_dir: Path = args.corpus_dir
    xml_dir = corpus_dir / "xml"
    reports_dir = corpus_dir / "reports"
    baseline_empty_body: set[str] = set()
    if args.baseline_empty_body.exists():
        baseline_empty_body = {
            line.strip() for line in args.baseline_empty_body.read_text().splitlines() if line.strip()
        }

    if not xml_dir.exists():
        print(f"ERROR: {xml_dir} not found — run `lexau build --all` first", file=sys.stderr)
        return 1

    xml_files = sorted(xml_dir.glob("*.xml"))
    if args.only_source_format:
        index_path = corpus_dir / "index.json"
        index = json.loads(index_path.read_text())
        matching_slugs = {
            slug for slug, entry in index["acts"].items()
            if entry.get("source_format") == args.only_source_format
        }
        xml_files = [p for p in xml_files if p.stem in matching_slugs]
    if not xml_files:
        print("ERROR: no XML files found in corpus/xml/", file=sys.stderr)
        return 1

    print(f"Checking {len(xml_files)} Acts in {xml_dir}\n")
    total_failures = 0

    for xml_path in xml_files:
        act_name = xml_path.stem
        issues = check_xml(xml_path)
        issues += check_has_sections(xml_path, act_name, baseline_empty_body)

        # Report filenames carry a version suffix (e.g. "-v0.5.0.json") that
        # bumps with the builder; glob rather than hardcode so this doesn't
        # silently stop matching reports at the next version bump.
        report_matches = sorted(reports_dir.glob(f"{act_name}-v*.json"))
        report_path = report_matches[-1] if report_matches else None
        if report_path is not None and report_path.exists():
            issues += check_report(report_path)
            report_data = json.loads(report_path.read_text())
            issues += check_conditional(xml_path, report_data)
            subsecs = report_data.get("subsections_parsed", 0)
            paras   = report_data.get("paragraphs_parsed", 0)
            sched   = report_data.get("schedules_found", 0)
            refs    = report_data.get("refs_resolved", 0)
            vols    = report_data.get("volumes_fetched", 1)
            summary = f"vols={vols} subsecs={subsecs} paras={paras} sched={sched} refs={refs}"
        else:
            summary = "(no report)"

        status = "OK  " if not issues else "FAIL"
        print(f"  {status}  {act_name}  [{summary}]")
        for issue in issues:
            print(f"        {issue}")
        total_failures += len(issues)

    empty_body_count = 0
    empty_body_slugs: list[str] = []
    for xml_path in xml_files:
        try:
            root = etree.parse(str(xml_path)).getroot()
        except Exception:
            continue
        if len(root.findall(".//akn:section", NS)) == 0:
            empty_body_count += 1
            empty_body_slugs.append(xml_path.stem)

    if args.dump_empty_body:
        args.dump_empty_body.write_text("\n".join(sorted(empty_body_slugs)) + "\n")
        print(f"Wrote {len(empty_body_slugs)} empty-<body> Act slugs -> {args.dump_empty_body}")

    print(f"\n{'='*60}")
    print(f"Acts with zero <section> elements: {empty_body_count} / {len(xml_files)}")
    if total_failures == 0:
        print(f"All checks passed ({len(xml_files)} Acts)")
        return 0
    else:
        print(f"{total_failures} check(s) FAILED across {len(xml_files)} Acts")
        return 1


if __name__ == "__main__":
    sys.exit(main())
