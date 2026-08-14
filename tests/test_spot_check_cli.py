import json
import subprocess
import sys
from pathlib import Path

from lxml import etree

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"


def _write_act_xml(xml_dir: Path, name: str, has_section: bool, extra_body: str = "") -> None:
    body = (f'<akn:section eId="sec_1"/>' if has_section else "") + extra_body
    frbr_work = (
        '<akn:FRBRWork>'
        '<akn:FRBRdate date="2020-01-01" name="generation"/>'
        '<akn:FRBRcountry value="au"/>'
        '<akn:FRBRsubtype value="act"/>'
        '<akn:FRBRnumber value="1"/>'
        '</akn:FRBRWork>'
    )
    xml_dir.joinpath(f"{name}.xml").write_text(
        f'<akn:akomaNtoso xmlns:akn="{AKN_NS}"><akn:act>'
        f'<akn:meta><akn:identification>{frbr_work}</akn:identification></akn:meta>'
        f'<akn:body>{body}</akn:body>'
        f'</akn:act></akn:akomaNtoso>'
    )


def _write_report(reports_dir: Path, name: str, version: str = "v0.5.0", **fields) -> None:
    reports_dir.mkdir(parents=True, exist_ok=True)
    reports_dir.joinpath(f"{name}-{version}.json").write_text(json.dumps(fields))


def test_dump_empty_body_writes_sorted_slugs(tmp_path: Path):
    corpus_dir = tmp_path / "corpus"
    xml_dir = corpus_dir / "xml"
    xml_dir.mkdir(parents=True)
    _write_act_xml(xml_dir, "zzz-empty-act", has_section=False)
    _write_act_xml(xml_dir, "aaa-empty-act", has_section=False)
    _write_act_xml(xml_dir, "has-sections-act", has_section=True)

    out_path = tmp_path / "empty-body.txt"
    result = subprocess.run(
        [sys.executable, "scripts/spot_check.py",
         "--corpus-dir", str(corpus_dir),
         "--dump-empty-body", str(out_path)],
        capture_output=True, text=True,
    )

    assert out_path.exists()
    lines = out_path.read_text().splitlines()
    assert lines == ["aaa-empty-act", "zzz-empty-act"]
    assert "has-sections-act" not in lines


def test_only_source_format_filters_to_matching_acts(tmp_path: Path):
    corpus_dir = tmp_path / "corpus"
    xml_dir = corpus_dir / "xml"
    xml_dir.mkdir(parents=True)
    _write_act_xml(xml_dir, "doc-converted-act", has_section=True)
    _write_act_xml(xml_dir, "docx-native-act", has_section=True)
    (corpus_dir / "index.json").write_text(json.dumps({
        "acts": {
            "doc-converted-act": {"source_format": "doc-converted"},
            "docx-native-act": {},
        }
    }))

    result = subprocess.run(
        [sys.executable, "scripts/spot_check.py",
         "--corpus-dir", str(corpus_dir),
         "--only-source-format", "doc-converted"],
        capture_output=True, text=True,
    )

    assert "doc-converted-act" in result.stdout
    assert "docx-native-act" not in result.stdout
    assert "Checking 1 Acts" in result.stdout


def test_report_conditional_checks_skip_when_content_absent_by_design(tmp_path: Path):
    # An Act whose report says zero subsections/dates/amendment events were
    # parsed should NOT be required to have <subsection>/<date>/<lifecycle>
    # elements -- absence is correct, not a defect.
    corpus_dir = tmp_path / "corpus"
    xml_dir = corpus_dir / "xml"
    xml_dir.mkdir(parents=True)
    _write_act_xml(xml_dir, "sparse-act", has_section=True)
    _write_report(
        corpus_dir / "reports", "sparse-act",
        subsections_parsed=0, dates_found=0, amendment_events_parsed=0, volumes_fetched=1,
    )

    result = subprocess.run(
        [sys.executable, "scripts/spot_check.py", "--corpus-dir", str(corpus_dir)],
        capture_output=True, text=True,
    )

    assert result.returncode == 0
    assert "FAIL" not in result.stdout


def test_report_conditional_checks_fail_when_content_expected_but_missing(tmp_path: Path):
    # An Act whose report says subsections WERE parsed but the XML has none
    # is a real regression and should still fail.
    corpus_dir = tmp_path / "corpus"
    xml_dir = corpus_dir / "xml"
    xml_dir.mkdir(parents=True)
    _write_act_xml(xml_dir, "regressed-act", has_section=True)
    _write_report(
        corpus_dir / "reports", "regressed-act",
        subsections_parsed=3, dates_found=0, amendment_events_parsed=0, volumes_fetched=1,
    )

    result = subprocess.run(
        [sys.executable, "scripts/spot_check.py", "--corpus-dir", str(corpus_dir)],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "Subsections present given subsections_parsed>0 in report" in result.stdout


def test_report_lookup_is_version_agnostic(tmp_path: Path):
    # Report filenames carry a version suffix that bumps with the builder;
    # a report under a different version string must still be found.
    corpus_dir = tmp_path / "corpus"
    xml_dir = corpus_dir / "xml"
    xml_dir.mkdir(parents=True)
    _write_act_xml(xml_dir, "future-act", has_section=True)
    _write_report(
        corpus_dir / "reports", "future-act", version="v9.9.9",
        subsections_parsed=0, dates_found=0, amendment_events_parsed=0, volumes_fetched=1,
    )

    result = subprocess.run(
        [sys.executable, "scripts/spot_check.py", "--corpus-dir", str(corpus_dir)],
        capture_output=True, text=True,
    )

    assert "(no report)" not in result.stdout
    assert "vols=1" in result.stdout


def test_baseline_empty_body_excludes_known_limitation_from_failure(tmp_path: Path):
    corpus_dir = tmp_path / "corpus"
    xml_dir = corpus_dir / "xml"
    xml_dir.mkdir(parents=True)
    _write_act_xml(xml_dir, "known-limitation-act", has_section=False)
    _write_act_xml(xml_dir, "unexpected-empty-act", has_section=False)
    baseline = tmp_path / "baseline.txt"
    baseline.write_text("known-limitation-act\n")

    result = subprocess.run(
        [sys.executable, "scripts/spot_check.py", "--corpus-dir", str(corpus_dir),
         "--baseline-empty-body", str(baseline)],
        capture_output=True, text=True,
    )

    assert result.returncode == 1
    assert "known-limitation-act" in result.stdout
    stdout_lines = result.stdout.splitlines()
    known_line_idx = next(i for i, l in enumerate(stdout_lines) if "known-limitation-act" in l)
    unexpected_line_idx = next(i for i, l in enumerate(stdout_lines) if "unexpected-empty-act" in l)
    assert "OK" in stdout_lines[known_line_idx]
    assert "FAIL" in stdout_lines[unexpected_line_idx]
    assert "At least one section with eId" in stdout_lines[unexpected_line_idx + 1]
