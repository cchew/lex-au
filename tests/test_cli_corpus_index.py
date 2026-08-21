import json

from lexau.cli import _load_corpus_index


def test_load_corpus_index_maps_canonical_name(tmp_path):
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps({
        "acts": {
            "privacy-act-1988": {
                "name": "Privacy Act 1988",
                "frbr_uri": "/akn/au/act/1988/119",
                "aliases": [],
            },
        },
    }))
    corpus_index = _load_corpus_index(index_path)
    assert corpus_index["Privacy Act 1988"] == {"frbr_uri": "/akn/au/act/1988/119"}


def test_load_corpus_index_resolves_alias_to_same_entry(tmp_path):
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps({
        "acts": {
            "human-services-(medicare)-act-1973": {
                "name": "Human Services (Medicare) Act 1973",
                "frbr_uri": "/akn/au/act/1974/41",
                "aliases": ["Health Insurance Commission Act 1973"],
            },
        },
    }))
    corpus_index = _load_corpus_index(index_path)
    assert corpus_index["Human Services (Medicare) Act 1973"] == {"frbr_uri": "/akn/au/act/1974/41"}
    assert corpus_index["Health Insurance Commission Act 1973"] == {"frbr_uri": "/akn/au/act/1974/41"}


def test_load_corpus_index_canonical_name_wins_over_alias_collision(tmp_path):
    index_path = tmp_path / "index.json"
    index_path.write_text(json.dumps({
        "acts": {
            "act-a": {"name": "Act A 2000", "frbr_uri": "/akn/au/act/2000/1", "aliases": ["Act B 2000"]},
            "act-b": {"name": "Act B 2000", "frbr_uri": "/akn/au/act/2000/2", "aliases": []},
        },
    }))
    corpus_index = _load_corpus_index(index_path)
    # Act B's own canonical entry must win over Act A's alias of the same string,
    # regardless of dict iteration order.
    assert corpus_index["Act B 2000"] == {"frbr_uri": "/akn/au/act/2000/2"}


def test_load_corpus_index_empty_when_no_index_file(tmp_path):
    assert _load_corpus_index(tmp_path / "missing.json") == {}
