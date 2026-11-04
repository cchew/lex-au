from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from lexau import cli as cli_mod


@pytest.fixture
def harness(monkeypatch, tmp_path):
    state = SimpleNamespace(modified=[], corpus=[], builds=[])

    class FakeCrawler:
        def list_modified_since(self, since):
            return list(state.modified)

    class FakeCorpus:
        def __init__(self, corpus_dir):
            pass

        def all_metadata(self):
            return [SimpleNamespace(title_id=t, name=n) for t, n in state.corpus]

    monkeypatch.setattr(cli_mod, "Crawler", FakeCrawler)
    monkeypatch.setattr(cli_mod, "Corpus", FakeCorpus)
    monkeypatch.setattr(
        cli_mod, "_build_acts",
        lambda names, corpus_dir, force, **kw: state.builds.append((list(names), force)),
    )

    def run(*extra):
        return CliRunner().invoke(
            cli_mod.cli,
            ["update", "--since", "2026-08-01", "--corpus-dir", str(tmp_path), *extra],
        )

    state.run = run
    return state


def _acts(n):
    return [(f"C{i}", f"Act {i:02d}") for i in range(n)]


def test_update_matches_corpus_by_title_id_not_name(harness):
    harness.corpus = [("C1", "New Name Act 2020")]
    harness.modified = ["C1", "C9"]
    result = harness.run()
    assert result.exit_code == 0, result.output
    assert harness.builds == [(["New Name Act 2020"], False)]
    assert "1 not in corpus" in result.output
    assert "modified corpus Act" in result.output


def test_update_nothing_modified_exits_zero(harness):
    result = harness.run()
    assert result.exit_code == 0
    assert "No modified Acts found." in result.output
    assert harness.builds == []


def test_update_none_in_corpus(harness):
    harness.corpus = [("C1", "Act 1")]
    harness.modified = ["C9"]
    result = harness.run()
    assert result.exit_code == 0
    assert "none in the corpus" in result.output
    assert harness.builds == []


def test_update_allows_exactly_max_acts(harness):
    harness.corpus = _acts(3)
    harness.modified = [t for t, _ in harness.corpus]
    result = harness.run("--max-acts", "3")
    assert result.exit_code == 0, result.output
    assert len(harness.builds[0][0]) == 3


def test_update_refuses_above_max_acts(harness):
    harness.corpus = _acts(4)
    harness.modified = [t for t, _ in harness.corpus]
    result = harness.run("--max-acts", "3")
    assert result.exit_code != 0
    assert "more than --max-acts 3" in result.output
    assert harness.builds == []


def test_update_default_max_acts_is_25(harness):
    harness.corpus = _acts(26)
    harness.modified = [t for t, _ in harness.corpus]
    result = harness.run()
    assert result.exit_code != 0
    assert "more than --max-acts 25" in result.output
    assert harness.builds == []
