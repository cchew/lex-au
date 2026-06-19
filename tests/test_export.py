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
    corpus.save(privacy_meta, builder.build())
    return tmp_path / "corpus"


def test_export_hf_calls_upload_folder(small_corpus):
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
        mock_api.upload_folder.assert_called_once()
        call_kwargs = mock_api.upload_folder.call_args.kwargs
        assert call_kwargs["repo_id"] == "cchew/lex-au"
        assert call_kwargs["repo_type"] == "dataset"
