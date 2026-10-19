"""Golden AKN fixtures for the lex-au stack contract tests.

`corpus_dir()` is shaped like a lex-au `corpus/` directory (`index.json` + `xml/`), so a
consumer can point its normal corpus loader at it. `manifest()` records the shape facts
and SHA-256 of every fixture. Regenerate with lex-au's scripts/build_contract_fixtures.py.
"""
from __future__ import annotations

import json
from pathlib import Path

_DATA = Path(__file__).parent / "data"


def corpus_dir() -> Path:
    return _DATA


def manifest() -> dict:
    return json.loads((_DATA / "contract.json").read_text())


def structure_version() -> int:
    return manifest()["structure_version"]


def fixtures_with(shape: str) -> list[str]:
    """Slugs of fixtures exhibiting a shape class (see manifest()['shape_classes'])."""
    return [s for s, f in manifest()["fixtures"].items() if shape in f["classes"]]
