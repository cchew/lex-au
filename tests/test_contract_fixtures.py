import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "contract-fixtures" / "src"))

import build_contract_fixtures as bcf  # noqa: E402
import lexau_contract_fixtures as fx  # noqa: E402
from lexau.corpus import STRUCTURE_VERSION  # noqa: E402


def test_fixture_versions_match_the_converter():
    index = json.loads((fx.corpus_dir() / "index.json").read_text())
    assert index["structure_version"] == STRUCTURE_VERSION
    assert fx.structure_version() == STRUCTURE_VERSION


def test_every_shape_class_has_a_fixture():
    for shape in fx.manifest()["shape_classes"]:
        assert fx.fixtures_with(shape), f"no fixture holds {shape}"


def test_index_and_manifest_list_the_same_fixtures():
    index = json.loads((fx.corpus_dir() / "index.json").read_text())["acts"]
    assert set(index) == set(fx.manifest()["fixtures"])
    for entry in index.values():
        assert (fx.corpus_dir() / entry["xml_path"]).exists()


@pytest.mark.parametrize("slug", sorted(fx.manifest()["fixtures"]))
def test_fixture_matches_its_manifest_entry(slug):
    path = fx.corpus_dir() / "xml" / f"{slug}.xml"
    recorded = fx.manifest()["fixtures"][slug]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == recorded["sha256"]
    assert bcf.measure(path) == recorded["facts"]
    assert bcf.classify(recorded["facts"]) == recorded["classes"]


def test_new_vocabulary_without_a_version_bump_is_refused():
    old = fx.manifest()
    new = copy.deepcopy(old)
    new["hcontainer_vocabulary"].append("brandnew")
    with pytest.raises(SystemExit, match="brandnew"):
        bcf.check_version_bump(new, old)


def test_new_vocabulary_with_a_version_bump_is_allowed():
    old = fx.manifest()
    new = copy.deepcopy(old)
    new["tag_vocabulary"].append("brandnew")
    new["structure_version"] = old["structure_version"] + 1
    bcf.check_version_bump(new, old)


def test_first_build_has_nothing_to_compare():
    bcf.check_version_bump(fx.manifest(), None)
