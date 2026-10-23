from dataclasses import fields

from click.testing import CliRunner

from lexau import cli
from lexau.profiles import CTH_PROFILE, ParserProfile, profile_for


def test_cth_profile_enables_both_flags() -> None:
    assert CTH_PROFILE.local_definitions is True
    assert CTH_PROFILE.scope_phrase_definitions is True
    assert CTH_PROFILE.dictionary_schedules is True
    default = ParserProfile()
    for f in fields(ParserProfile):
        if f.name in ("local_definitions", "scope_phrase_definitions", "dictionary_schedules"):
            continue
        assert getattr(CTH_PROFILE, f.name) == getattr(default, f.name), f.name


def test_profile_for_acts_only() -> None:
    assert profile_for("act", True) is CTH_PROFILE
    assert profile_for("act", False) is None
    assert profile_for("regulation", True) is None
    assert profile_for("instrument", True) is None


def _drive_build_acts(monkeypatch, tmp_path, doc_type: str, **kwargs) -> list:
    """Run _build_acts for one Act with every collaborator stubbed; return _convert_act's profile args."""
    from datetime import date
    from unittest.mock import MagicMock

    from lexau.models import ActMetadata, ParseReport

    meta = ActMetadata("X Act 2000", "T", "C", "1", 2000, 1, date(2000, 1, 1), doc_type=doc_type)
    crawler = MagicMock()
    crawler.fetch_metadata.return_value = meta
    crawler.fetch_docx_volumes.return_value = [tmp_path / "x.docx"]
    corpus = MagicMock()
    corpus.is_current.return_value = False
    corpus.save.return_value = tmp_path / "xml" / "x.xml"
    seen: list = []

    def fake_convert(meta, docx_paths, corpus_dir, corpus_index, profile):
        seen.append(profile)
        return None, ParseReport(act_name=meta.name)

    monkeypatch.setattr(cli, "Crawler", lambda: crawler)
    monkeypatch.setattr(cli, "Corpus", lambda _d: corpus)
    monkeypatch.setattr(cli, "_convert_act", fake_convert)
    cli._build_acts(["X Act 2000"], tmp_path, True, doc_type=doc_type, **kwargs)
    return seen


def test_build_acts_passes_profile_for_into_convert_act(monkeypatch, tmp_path) -> None:
    assert _drive_build_acts(monkeypatch, tmp_path, "act", local_definitions=True) == [CTH_PROFILE]
    assert _drive_build_acts(monkeypatch, tmp_path, "act", local_definitions=False) == [None]
    assert _drive_build_acts(monkeypatch, tmp_path, "regulation", local_definitions=True) == [None]
    # default (not passed) is on
    assert _drive_build_acts(monkeypatch, tmp_path, "act") == [CTH_PROFILE]


def test_convert_act_forwards_profile_to_builder(monkeypatch, tmp_path) -> None:
    from datetime import date
    from unittest.mock import MagicMock

    from lexau.models import ActMetadata

    meta = ActMetadata("X Act 2000", "T", "C", "1", 2000, 1, date(2000, 1, 1))
    recorder = MagicMock()
    monkeypatch.setattr(cli, "AknBuilder", recorder)
    monkeypatch.setattr(cli, "Document", lambda _p: object())
    monkeypatch.setattr(cli, "iter_paragraphs", lambda _d: [])
    monkeypatch.setattr(cli, "_find_endnote_volume", lambda _p: None)
    for sentinel in (CTH_PROFILE, None):
        recorder.reset_mock()
        cli._convert_act(meta, [tmp_path / "x.docx"], tmp_path, {}, sentinel)
        assert recorder.call_args.kwargs["profile"] is sentinel


def test_build_option_defaults_on() -> None:
    opts = {p.name: p for p in cli.build.params}
    assert opts["local_definitions"].default is True
    assert "--local-definitions" in opts["local_definitions"].opts
    assert "--no-local-definitions" in opts["local_definitions"].secondary_opts
    assert "--local-definitions" in CliRunner().invoke(cli.build, ["--help"]).output


def test_no_local_definitions_flag_disables_profile() -> None:
    from unittest.mock import patch

    with patch.object(cli, "_build_acts") as m:
        r = CliRunner().invoke(cli.build, ["--acts", "X Act 2000", "--no-local-definitions"])
        assert r.exit_code == 0, r.output
        assert m.call_args.kwargs["local_definitions"] is False
        CliRunner().invoke(cli.build, ["--acts", "X Act 2000"])
        assert m.call_args.kwargs["local_definitions"] is True
