import hashlib
import json
import os
from types import SimpleNamespace

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


HEAD_SHA = "0" * 40


def _write_sync_stamp(corpus_dir: Path, *, repo="cchew/lex-au", age=timedelta(minutes=5),
                      sha=HEAD_SHA, **extra):
    restored_at = datetime.now(timezone.utc) - age
    stamp_path = corpus_dir / ".hf-sync-stamp.json"
    stamp_path.write_text(
        json.dumps(
            {
                "repo": repo,
                "repo_type": "dataset",
                "restored_at": restored_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "remote_sha": sha,
                **extra,
            }
        )
    )
    # The restore happened before this run built anything: date the stamp
    # back so the corpus files read as "written this run".
    past = stamp_path.stat().st_mtime - 3600
    os.utime(stamp_path, (past, past))


def _configure(mock_api, head=HEAD_SHA, tree=()):
    mock_api.repo_info.return_value.sha = head
    mock_api.list_repo_tree.return_value = list(tree)
    return mock_api


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


def test_installed_huggingface_hub_supports_upload_large_folder():
    """export_hf() calls api.upload_large_folder against a *mocked* HfApi in
    every other test here, so those tests can't detect the installed
    huggingface_hub version actually dropping the method (it was removed
    outright in 2.0.0, breaking growth-check 2026-09-27 -- CI's unpinned
    install picked up 2.0.0 the day it released). Exercise the real class."""
    from huggingface_hub import HfApi

    assert hasattr(HfApi(), "upload_large_folder"), (
        "HfApi.upload_large_folder is gone from the installed huggingface_hub "
        "-- pyproject.toml's huggingface-hub ceiling needs revisiting (and "
        "lexau.cli.export_hf needs a different upload path)."
    )


def test_export_hf_calls_upload_large_folder(small_corpus):
    runner = CliRunner()
    with patch("lexau.cli.HfApi") as mock_api_cls:
        mock_api = _configure(MagicMock())
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
        mock_api = _configure(MagicMock())
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
        mock_api = _configure(MagicMock())
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
        mock_api = _configure(MagicMock())
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
        mock_api = _configure(MagicMock())
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
        mock_api = _configure(MagicMock())
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


def test_export_hf_refuses_when_sync_stamp_missing(small_corpus):
    (small_corpus / ".hf-sync-stamp.json").unlink()

    result, mock_api = _run_export_with_orphan(small_corpus)

    assert result.exit_code != 0
    mock_api.upload_large_folder.assert_not_called()
    mock_api.delete_files.assert_not_called()
    assert "Refusing to export" in result.output
    assert "not found" in result.output


def test_export_hf_skips_reconcile_when_sync_stamp_stale(small_corpus):
    _write_sync_stamp(small_corpus, age=timedelta(days=3))

    result, mock_api = _run_export_with_orphan(small_corpus)

    assert result.exit_code == 0, result.output
    mock_api.delete_files.assert_not_called()
    assert "skipping remote-deletion reconcile" in result.output
    assert "old (limit 24h)" in result.output


def test_export_hf_refuses_when_sync_stamp_is_for_another_repo(small_corpus):
    _write_sync_stamp(small_corpus, repo="someone/other-dataset")

    result, mock_api = _run_export_with_orphan(small_corpus)

    assert result.exit_code != 0
    mock_api.upload_large_folder.assert_not_called()
    mock_api.delete_files.assert_not_called()
    assert "written for repo" in result.output


def test_export_hf_allow_deletes_overrides_missing_sync_stamp(small_corpus):
    (small_corpus / ".hf-sync-stamp.json").unlink()

    result, mock_api = _run_export_with_orphan(
        small_corpus, extra_args=["--allow-deletes", "--skip-sync-check"]
    )

    assert result.exit_code == 0, result.output
    mock_api.delete_files.assert_called_once()
    call_kwargs = mock_api.delete_files.call_args.kwargs
    assert call_kwargs["delete_patterns"] == ["xml/health-insurance-commission-act-1973.xml"]


def _remote_entry(corpus_dir: Path, rel: str, data: bytes | None = None):
    """A list_repo_tree entry for rel, matching the local file unless data
    is given."""
    if data is None:
        data = (corpus_dir / rel).read_bytes()
    blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
    return SimpleNamespace(path=rel, size=len(data), blob_id=blob, lfs=None)


def _export(corpus_dir, *, head=HEAD_SHA, tree=(), extra_args=()):
    runner = CliRunner()
    with patch("lexau.cli.HfApi") as mock_api_cls:
        mock_api = _configure(MagicMock(), head=head, tree=tree)
        mock_api_cls.return_value = mock_api
        mock_api.list_repo_files.return_value = [e.path for e in tree]
        result = runner.invoke(cli, [
            "export-hf", "--repo", "cchew/lex-au", "--corpus-dir", str(corpus_dir), *extra_args,
        ])
    return result, mock_api


def _backdate(path: Path, stamp: Path) -> None:
    old = stamp.stat().st_mtime - 60
    os.utime(path, (old, old))


def test_export_hf_refuses_when_remote_head_moved(small_corpus):
    result, mock_api = _export(small_corpus, head="f" * 40)

    assert result.exit_code != 0
    assert "someone published in between" in result.output
    mock_api.upload_large_folder.assert_not_called()


def test_export_hf_refuses_partial_restore_stamp(small_corpus):
    _write_sync_stamp(small_corpus, allow_patterns=["xml/*"])

    result, mock_api = _export(small_corpus)

    assert result.exit_code != 0
    assert "partial restore" in result.output
    mock_api.upload_large_folder.assert_not_called()


def test_export_hf_refuses_stale_files_untouched_since_restore(small_corpus):
    """The 2026-10-25 clobber: files left over from before the restore
    differ from the remote although nothing this run wrote them."""
    stamp = small_corpus / ".hf-sync-stamp.json"
    stale = small_corpus / "xml" / "stale-act.xml"
    stale.write_text("<akn>old</akn>")
    _backdate(stale, stamp)
    tree = [
        _remote_entry(small_corpus, "xml/stale-act.xml", b"<akn>new</akn>"),
        _remote_entry(small_corpus, "index.json"),
    ]

    result, mock_api = _export(small_corpus, tree=tree)

    assert result.exit_code != 0
    assert "not written since the restore" in result.output
    assert "xml/stale-act.xml" in result.output
    mock_api.upload_large_folder.assert_not_called()


def test_export_hf_refuses_change_set_larger_than_built_plus_allowance(small_corpus):
    reports = small_corpus / "reports"
    reports.mkdir(exist_ok=True)
    for i in range(30):
        (reports / f"r{i:02d}.json").write_text(str(i))

    result, mock_api = _export(small_corpus, extra_args=["--change-allowance", "10"])

    assert result.exit_code != 0
    assert "31 file(s) outside the 1 Act(s) built this run" in result.output  # 30 + index.json
    assert "allowance 10" in result.output
    assert "First 20 of" in result.output
    mock_api.upload_large_folder.assert_not_called()


def _add_figures(corpus_dir: Path, safe_name: str, count: int) -> None:
    images = corpus_dir / "images"
    images.mkdir(exist_ok=True)
    for n in range(1, count + 1):
        (images / f"{safe_name}-fig-{n}.png").write_bytes(b"\x89PNG %d" % n)


def test_export_hf_built_act_figures_and_report_are_expected(small_corpus):
    """ITAA 1997 has 362 figures. Rebuilding it legitimately rewrites its
    xml, report and every figure; none of that counts against the
    allowance for unexpected files."""
    _add_figures(small_corpus, "privacy-act-1988", 362)
    reports = small_corpus / "reports"
    reports.mkdir(exist_ok=True)
    (reports / "privacy-act-1988-v0.5.0.json").write_text("{}")

    result, mock_api = _export(small_corpus)

    assert result.exit_code == 0, result.output
    mock_api.upload_large_folder.assert_called_once()


def test_export_hf_images_referenced_by_built_xml_are_expected(small_corpus):
    xml = small_corpus / "xml" / "privacy-act-1988.xml"
    srcs = "".join(f'<img src="corpus/images/odd-name-{n}.png"/>' for n in range(20))
    xml.write_text(xml.read_text().replace("</akomaNtoso>", srcs + "</akomaNtoso>"))
    images = small_corpus / "images"
    images.mkdir(exist_ok=True)
    for n in range(20):
        (images / f"odd-name-{n}.png").write_bytes(b"png")

    result, mock_api = _export(small_corpus, extra_args=["--change-allowance", "5"])

    assert result.exit_code == 0, result.output
    mock_api.upload_large_folder.assert_called_once()


def test_export_hf_figures_of_act_not_built_count_against_allowance(small_corpus):
    """Images newer than the stamp but belonging to an Act whose xml was not
    rewritten this run are unexpected."""
    _add_figures(small_corpus, "other-act-2001", 12)

    result, mock_api = _export(small_corpus, extra_args=["--change-allowance", "10"])

    assert result.exit_code != 0
    assert "outside the 1 Act(s) built this run" in result.output
    mock_api.upload_large_folder.assert_not_called()


def test_export_hf_stale_figure_of_built_act_still_refused(small_corpus):
    """Being an expected path never excuses a file the run did not write."""
    _add_figures(small_corpus, "privacy-act-1988", 1)
    stale = small_corpus / "images" / "privacy-act-1988-fig-1.png"
    _backdate(stale, small_corpus / ".hf-sync-stamp.json")

    result, mock_api = _export(small_corpus)

    assert result.exit_code != 0
    assert "not written since the restore" in result.output
    mock_api.upload_large_folder.assert_not_called()


def test_export_hf_allow_large_change_overrides_limits(small_corpus):
    reports = small_corpus / "reports"
    reports.mkdir(exist_ok=True)
    for i in range(30):
        (reports / f"r{i:02d}.json").write_text(str(i))

    result, mock_api = _export(
        small_corpus, extra_args=["--change-allowance", "10", "--allow-large-change"]
    )

    assert result.exit_code == 0, result.output
    mock_api.upload_large_folder.assert_called_once()


def test_export_hf_unchanged_old_files_are_fine(small_corpus):
    """Restored files older than the stamp are fine as long as they still
    match the remote; only the Act built this run is uploaded."""
    stamp = small_corpus / ".hf-sync-stamp.json"
    old = small_corpus / "xml" / "untouched-act.xml"
    old.write_text("<akn>same</akn>")
    _backdate(old, stamp)
    tree = [_remote_entry(small_corpus, "xml/untouched-act.xml")]

    result, mock_api = _export(small_corpus, tree=tree)

    assert result.exit_code == 0, result.output
    mock_api.upload_large_folder.assert_called_once()
    assert "file(s) differ from cchew/lex-au@" in result.output


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
