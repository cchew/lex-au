import inspect
import re
from dataclasses import fields

from click.testing import CliRunner

from lexau import cli
from lexau.profiles import CTH_PROFILE, ParserProfile, profile_for


def test_cth_profile_enables_both_flags() -> None:
    assert CTH_PROFILE.local_definitions is True
    assert CTH_PROFILE.scope_phrase_definitions is True
    default = ParserProfile()
    for f in fields(ParserProfile):
        if f.name in ("local_definitions", "scope_phrase_definitions"):
            continue
        assert getattr(CTH_PROFILE, f.name) == getattr(default, f.name), f.name


def test_profile_for_acts_only() -> None:
    assert profile_for("act", True) is CTH_PROFILE
    assert profile_for("act", False) is None
    assert profile_for("regulation", True) is None
    assert profile_for("instrument", True) is None


def test_build_acts_uses_profile_for() -> None:
    src = inspect.getsource(cli._build_acts)
    assert "_convert_act(" in src
    flat = re.sub(r"\s+", " ", src)
    assert "profile_for(doc_type, local_definitions)" in flat
    assert "local_definitions: bool = True" in src


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


def test_update_uses_build_acts_default() -> None:
    sig = inspect.signature(cli._build_acts)
    assert sig.parameters["local_definitions"].default is True


def test_convert_act_is_the_only_builder_site() -> None:
    assert len(re.findall(r"AknBuilder\(", inspect.getsource(cli._convert_act))) == 1
    assert "AknBuilder(" not in inspect.getsource(cli._build_acts)
