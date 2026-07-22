import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from click.testing import CliRunner
from lexau.cli import cli
from lexau.corpus import Corpus
from lexau.models import ActMetadata
from lexau.builder import AknBuilder
from lexau.parser import ParsedParagraph, ElementType
from datetime import date


@pytest.fixture
def small_corpus(tmp_path, privacy_meta):
    corpus = Corpus(tmp_path / "corpus")
    builder = AknBuilder(privacy_meta)
    builder.add(ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"))
    builder.add(ParsedParagraph(ElementType.BODY, text="This Act is the Privacy Act 1988."))
    xml, _validation = builder.build()
    corpus.save(privacy_meta, xml)
    return tmp_path / "corpus"


def test_export_hf_calls_upload_large_folder(small_corpus):
    runner = CliRunner()
    with patch("lexau.cli.HfApi") as mock_api_cls:
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        result = runner.invoke(cli, [
            "export-hf",
            "--repo", "cchew/lex-au",
            "--corpus-dir", str(small_corpus),
        ])

        assert result.exit_code == 0, result.output
        mock_api.upload_large_folder.assert_called_once()
        call_kwargs = mock_api.upload_large_folder.call_args.kwargs
        assert call_kwargs["repo_id"] == "cchew/lex-au"
        assert call_kwargs["repo_type"] == "dataset"
        assert call_kwargs["ignore_patterns"] == ["docx/**", "doc_spike/**"]
        mock_api.upload_folder.assert_not_called()


def test_export_jsonl_writes_one_row_per_act(small_corpus):
    import json

    runner = CliRunner()
    result = runner.invoke(cli, ["export-jsonl", "--corpus-dir", str(small_corpus)])
    assert result.exit_code == 0, result.output

    out_path = small_corpus / "data" / "train.jsonl"
    assert out_path.exists()
    lines = out_path.read_text().strip().splitlines()
    assert len(lines) == 1  # small_corpus fixture saves exactly one Act (Privacy Act)

    row = json.loads(lines[0])
    assert row["slug"] == "privacy-act-1988"
    assert row["name"] == "Privacy Act 1988"
    assert row["xml_path"] == "xml/privacy-act-1988.xml"
    assert set(row.keys()) == {
        "slug", "name", "title_id", "comp_id", "comp_num",
        "year", "number", "effective_date", "xml_path",
    }


def test_export_jsonl_multiple_acts_sorted_by_slug(small_corpus, tmp_path):
    import json
    from datetime import date
    from lexau.models import ActMetadata

    corpus = Corpus(small_corpus)
    other_meta = ActMetadata(
        name="A New Tax System (Australian Business Number) Act 1999",
        title_id="C2004A00376",
        comp_id="C2020C00104",
        comp_num="10",
        year=1999,
        number=176,
        effective_date=date(2020, 1, 1),
    )
    builder = AknBuilder(other_meta)
    builder.add(ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"))
    xml, _validation = builder.build()
    corpus.save(other_meta, xml)

    runner = CliRunner()
    result = runner.invoke(cli, ["export-jsonl", "--corpus-dir", str(small_corpus)])
    assert result.exit_code == 0, result.output

    lines = (small_corpus / "data" / "train.jsonl").read_text().strip().splitlines()
    assert len(lines) == 2
    slugs = [json.loads(line)["slug"] for line in lines]
    assert slugs == sorted(slugs)  # sorted by slug, deterministic output
