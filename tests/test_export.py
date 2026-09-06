import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from click.testing import CliRunner
from lexau.cli import cli
from lexau.corpus import Corpus
from lexau.models import ActMetadata
from lexau.builder import AknBuilder
from lexau.parser import ParsedParagraph, ElementType
from datetime import date, datetime, timedelta, timezone


def _write_sync_stamp(corpus_dir: Path, *, repo="cchew/lex-au", age=timedelta(minutes=5)):
    restored_at = datetime.now(timezone.utc) - age
    (corpus_dir / ".hf-sync-stamp.json").write_text(
        json.dumps(
            {
                "repo": repo,
                "repo_type": "dataset",
                "restored_at": restored_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "remote_sha": "0" * 40,
            }
        )
    )


@pytest.fixture
def small_corpus(tmp_path, privacy_meta):
    corpus = Corpus(tmp_path / "corpus")
    builder = AknBuilder(privacy_meta)
    builder.add(ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"))
    builder.add(ParsedParagraph(ElementType.BODY, text="This Act is the Privacy Act 1988."))
    xml, _validation = builder.build()
    corpus.save(privacy_meta, xml)
    # A fresh sync stamp is the normal state after restore_corpus_from_hf.py:
    # export-hf trusts a corpus in this state to drive remote deletions.
    _write_sync_stamp(tmp_path / "corpus")
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
        assert call_kwargs["ignore_patterns"] == ["docx/**", "doc_spike/**", ".hf-sync-stamp.json"]
        mock_api.upload_folder.assert_not_called()


def test_export_hf_deletes_remote_file_absent_locally(small_corpus):
    runner = CliRunner()
    with patch("lexau.cli.HfApi") as mock_api_cls:
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_api.list_repo_files.return_value = [
            "index.json",
            "xml/privacy-act-1988.xml",
            "xml/health-insurance-commission-act-1973.xml",  # orphan: no longer local
        ]

        result = runner.invoke(cli, [
            "export-hf",
            "--repo", "cchew/lex-au",
            "--corpus-dir", str(small_corpus),
        ])

        assert result.exit_code == 0, result.output
        mock_api.delete_files.assert_called_once()
        call_kwargs = mock_api.delete_files.call_args.kwargs
        assert call_kwargs["repo_id"] == "cchew/lex-au"
        assert call_kwargs["repo_type"] == "dataset"
        assert call_kwargs["delete_patterns"] == ["xml/health-insurance-commission-act-1973.xml"]
        assert "Deleted orphaned remote files:" in result.output
        assert "xml/health-insurance-commission-act-1973.xml" in result.output


def test_export_hf_leaves_remote_file_present_locally_alone(small_corpus):
    runner = CliRunner()
    with patch("lexau.cli.HfApi") as mock_api_cls:
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_api.list_repo_files.return_value = [
            "index.json",
            "xml/privacy-act-1988.xml",
        ]

        result = runner.invoke(cli, [
            "export-hf",
            "--repo", "cchew/lex-au",
            "--corpus-dir", str(small_corpus),
        ])

        assert result.exit_code == 0, result.output
        mock_api.delete_files.assert_not_called()
        assert "No orphaned remote files to delete." in result.output


def test_export_hf_never_deletes_readme(small_corpus):
    runner = CliRunner()
    with patch("lexau.cli.HfApi") as mock_api_cls:
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        # README.md is uploaded separately from --readme, never present under
        # corpus_dir, so a naive local-vs-remote diff would flag it.
        mock_api.list_repo_files.return_value = [
            "index.json",
            "xml/privacy-act-1988.xml",
            "README.md",
        ]

        result = runner.invoke(cli, [
            "export-hf",
            "--repo", "cchew/lex-au",
            "--corpus-dir", str(small_corpus),
        ])

        assert result.exit_code == 0, result.output
        mock_api.delete_files.assert_not_called()
        assert "No orphaned remote files to delete." in result.output


def test_export_hf_never_deletes_ignore_pattern_paths(small_corpus):
    # A docx/** path that's genuinely absent locally (and would never have
    # been uploaded even if present, since export_hf ignore_patterns it) --
    # the reconcile step must not treat this as an orphan.
    runner = CliRunner()
    with patch("lexau.cli.HfApi") as mock_api_cls:
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_api.list_repo_files.return_value = [
            "index.json",
            "xml/privacy-act-1988.xml",
            "docx/some-old-act-c1-vol0.docx",
            "doc_spike/scratch.docx",
        ]

        result = runner.invoke(cli, [
            "export-hf",
            "--repo", "cchew/lex-au",
            "--corpus-dir", str(small_corpus),
        ])

        assert result.exit_code == 0, result.output
        mock_api.delete_files.assert_not_called()
        assert "No orphaned remote files to delete." in result.output


def _run_export_with_orphan(corpus_dir, extra_args=()):
    runner = CliRunner()
    with patch("lexau.cli.HfApi") as mock_api_cls:
        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_api.list_repo_files.return_value = [
            "index.json",
            "xml/privacy-act-1988.xml",
            "xml/health-insurance-commission-act-1973.xml",  # orphan
        ]
        result = runner.invoke(cli, [
            "export-hf",
            "--repo", "cchew/lex-au",
            "--corpus-dir", str(corpus_dir),
            *extra_args,
        ])
    return result, mock_api


def test_export_hf_skips_reconcile_when_sync_stamp_missing(small_corpus):
    (small_corpus / ".hf-sync-stamp.json").unlink()

    result, mock_api = _run_export_with_orphan(small_corpus)

    assert result.exit_code == 0, result.output
    mock_api.upload_large_folder.assert_called_once()  # additions still happen
    mock_api.delete_files.assert_not_called()  # but nothing is deleted
    assert "skipping remote-deletion reconcile" in result.output
    assert "not found" in result.output


def test_export_hf_skips_reconcile_when_sync_stamp_stale(small_corpus):
    _write_sync_stamp(small_corpus, age=timedelta(days=3))

    result, mock_api = _run_export_with_orphan(small_corpus)

    assert result.exit_code == 0, result.output
    mock_api.delete_files.assert_not_called()
    assert "skipping remote-deletion reconcile" in result.output
    assert "old (limit 24h)" in result.output


def test_export_hf_skips_reconcile_when_sync_stamp_is_for_another_repo(small_corpus):
    _write_sync_stamp(small_corpus, repo="someone/other-dataset")

    result, mock_api = _run_export_with_orphan(small_corpus)

    assert result.exit_code == 0, result.output
    mock_api.delete_files.assert_not_called()
    assert "written for repo" in result.output


def test_export_hf_allow_deletes_overrides_missing_sync_stamp(small_corpus):
    (small_corpus / ".hf-sync-stamp.json").unlink()

    result, mock_api = _run_export_with_orphan(small_corpus, extra_args=["--allow-deletes"])

    assert result.exit_code == 0, result.output
    mock_api.delete_files.assert_called_once()
    call_kwargs = mock_api.delete_files.call_args.kwargs
    assert call_kwargs["delete_patterns"] == ["xml/health-insurance-commission-act-1973.xml"]


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
        "year", "number", "effective_date", "xml_path", "aliases",
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


def test_export_jsonl_includes_aliases(tmp_path, privacy_meta):
    import json
    from dataclasses import replace
    from lexau.corpus import Corpus
    from lexau.builder import AknBuilder
    from lexau.parser import ParsedParagraph, ElementType

    corpus_dir = tmp_path / "corpus"
    corpus = Corpus(corpus_dir)
    meta = replace(privacy_meta, aliases=["Old Privacy Act Name 1988"])
    builder = AknBuilder(meta)
    builder.add(ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"))
    xml, _validation = builder.build()
    corpus.save(meta, xml)

    runner = CliRunner()
    result = runner.invoke(cli, ["export-jsonl", "--corpus-dir", str(corpus_dir)])
    assert result.exit_code == 0, result.output

    row = json.loads((corpus_dir / "data" / "train.jsonl").read_text().strip())
    assert row["aliases"] == ["Old Privacy Act Name 1988"]
