import importlib.util
import json
from pathlib import Path

import click
import pytest

_spec = importlib.util.spec_from_file_location(
    "merge_offline", Path(__file__).resolve().parent.parent / "scripts" / "merge_offline.py"
)
merge_offline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(merge_offline)


def _corpus(root: Path, keys: list[str], text: str, structure_version: int | None = None) -> Path:
    (root / "xml").mkdir(parents=True)
    for k in keys:
        (root / "xml" / f"{k}.xml").write_text(f"{text}-{k}")
    index: dict = {"acts": {k: {"name": k, "comp_num": 7} for k in keys}, "updated_at": "x"}
    if structure_version is not None:
        index["structure_version"] = structure_version
    (root / "index.json").write_text(json.dumps(index))
    return root


def test_merge_overlays_rebuilt_and_keeps_baseline(tmp_path):
    base = _corpus(tmp_path / "base", ["a", "b", "c"], "old")
    c0 = _corpus(tmp_path / "c0", ["a"], "new", 2)
    c1 = _corpus(tmp_path / "c1", ["b"], "new", 2)
    out = tmp_path / "out"
    stats = merge_offline.merge(base, [c0, c1], out)
    assert stats == {"baseline_acts": 3, "rebuilt": 2, "kept_baseline": 1}
    assert (out / "xml" / "a.xml").read_text() == "new-a"
    assert (out / "xml" / "c.xml").read_text() == "old-c"
    index = json.loads((out / "index.json").read_text())
    assert index["structure_version"] == 2
    assert index["acts"]["a"]["comp_num"] == 7
    assert (base / "xml" / "a.xml").read_text() == "old-a"


def test_merge_rejects_duplicate_and_unknown(tmp_path):
    base = _corpus(tmp_path / "base", ["a"], "old")
    dup0 = _corpus(tmp_path / "d0", ["a"], "new", 2)
    dup1 = _corpus(tmp_path / "d1", ["a"], "new", 2)
    with pytest.raises(click.UsageError, match="two chunks"):
        merge_offline.merge(base, [dup0, dup1], tmp_path / "o1")
    unknown = _corpus(tmp_path / "u", ["zzz"], "new", 2)
    with pytest.raises(click.UsageError, match="not in the baseline"):
        merge_offline.merge(base, [unknown], tmp_path / "o2")


def test_merge_requires_matching_structure_version(tmp_path):
    base = _corpus(tmp_path / "base", ["a", "b"], "old")
    c0 = _corpus(tmp_path / "c0", ["a"], "new", 2)
    c1 = _corpus(tmp_path / "c1", ["b"], "new", 3)
    with pytest.raises(click.UsageError, match="structure_version"):
        merge_offline.merge(base, [c0, c1], tmp_path / "out")
