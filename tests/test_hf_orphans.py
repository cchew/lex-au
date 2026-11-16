import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import hf_orphans as ho  # noqa: E402

REMOTE = [
    ".gitattributes", "README.md", "index.json", "data/train.jsonl",
    "xml/a.xml", "xml/gone.xml",
    "images/a-fig-1.png", "images/a-fig-2.png", "images/dropped-fig-1.png",
    "reports/a-v0.5.0.json", "reports/a-v0.3.0.json", "reports/gone-v0.5.0.json",
    "reports/fidelity/x.json", "reports/legacy-shape-discovery.json", "reports/export-hf-v0.7.2.log",
]


def test_find_orphans_classifies_only_what_the_corpus_proves_unused() -> None:
    orphans = ho.find_orphans(REMOTE, index_slugs={"a"}, referenced_images={"a-fig-1.png", "a-fig-2.png"})
    assert orphans == {
        "xml": ["xml/gone.xml"],
        "images": ["images/dropped-fig-1.png"],
        "reports": ["reports/a-v0.3.0.json", "reports/gone-v0.5.0.json"],
    }


def test_nothing_is_orphaned_when_everything_is_referenced() -> None:
    remote = [f for f in REMOTE if "gone" not in f and "dropped" not in f and "v0.3.0" not in f]
    orphans = ho.find_orphans(remote, index_slugs={"a"}, referenced_images={"a-fig-1.png", "a-fig-2.png"})
    assert all(not v for v in orphans.values())


def test_refuses_when_the_corpus_looks_partial() -> None:
    # An empty index or no image references means the local corpus is not a restore of the dataset.
    import pytest
    with pytest.raises(ValueError):
        ho.find_orphans(REMOTE, index_slugs=set(), referenced_images={"a-fig-1.png"})
    with pytest.raises(ValueError):
        ho.find_orphans(REMOTE, index_slugs={"a"}, referenced_images=set())
