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
    assert len(re.findall(r"AknBuilder\(", src)) == 1
    flat = re.sub(r"\s+", " ", src)
    assert "profile=profile_for(doc_type, local_definitions)" in flat
    assert "local_definitions: bool = False" in src


def test_build_option_defaults_off() -> None:
    opts = {p.name: p for p in cli.build.params}
    assert opts["local_definitions"].default is False
    assert "--local-definitions" in opts["local_definitions"].opts
    assert "--no-local-definitions" in opts["local_definitions"].secondary_opts
    assert "--local-definitions" in CliRunner().invoke(cli.build, ["--help"]).output
