import json
import subprocess
import sys
from pathlib import Path

from lxml import etree

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"


def _write_act_xml(xml_dir: Path, name: str, has_section: bool) -> None:
    body = f'<akn:section eId="sec_1"/>' if has_section else ""
    xml_dir.joinpath(f"{name}.xml").write_text(
        f'<akn:akomaNtoso xmlns:akn="{AKN_NS}"><akn:act>'
        f'<akn:meta><akn:identification/></akn:meta>'
        f'<akn:body>{body}</akn:body>'
        f'</akn:act></akn:akomaNtoso>'
    )


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
