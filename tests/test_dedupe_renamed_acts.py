from scripts.dedupe_renamed_acts import dedupe_by_title_id


def _index(acts: dict) -> dict:
    return {"acts": acts, "updated_at": "2026-08-21T00:00:00+00:00"}


def test_dedupe_collapses_duplicate_title_id():
    index = _index({
        "health-insurance-commission-act-1973": {
            "name": "Health Insurance Commission Act 1973",
            "title_id": "C2004A00100",
            "comp_id": "C2025C00609",
            "comp_num": "51",
            "year": 1974,
            "number": 41,
            "effective_date": "2025-11-01",
            "xml_path": "xml/health-insurance-commission-act-1973.xml",
            "aliases": [],
        },
        "human-services-(medicare)-act-1973": {
            "name": "Human Services (Medicare) Act 1973",
            "title_id": "C2004A00100",
            "comp_id": "C2025C00609",
            "comp_num": "51",
            "year": 1974,
            "number": 41,
            "effective_date": "2025-11-01",
            "xml_path": "xml/human-services-(medicare)-act-1973.xml",
            "aliases": [],
        },
    })

    def resolve(title_id: str) -> str:
        assert title_id == "C2004A00100"
        return "Human Services (Medicare) Act 1973"

    result, to_delete = dedupe_by_title_id(index, resolve)

    assert list(result["acts"].keys()) == ["human-services-(medicare)-act-1973"]
    assert result["acts"]["human-services-(medicare)-act-1973"]["aliases"] == [
        "Health Insurance Commission Act 1973"
    ]
    assert to_delete == ["xml/health-insurance-commission-act-1973.xml"]


def test_dedupe_leaves_single_entry_groups_untouched():
    index = _index({
        "privacy-act-1988": {
            "name": "Privacy Act 1988", "title_id": "C2004A03712",
            "comp_id": "C2024C00280", "comp_num": "52", "year": 1988, "number": 119,
            "effective_date": "2024-01-01", "xml_path": "xml/privacy-act-1988.xml",
            "aliases": [],
        },
    })

    def resolve(title_id: str) -> str:
        raise AssertionError("should not be called for a non-duplicated title_id")

    result, to_delete = dedupe_by_title_id(index, resolve)

    assert result == index
    assert to_delete == []


def test_dedupe_merges_preexisting_aliases_from_both_sides():
    index = _index({
        "old-name-act-1973": {
            "name": "Old Name Act 1973", "title_id": "T1", "comp_id": "C1",
            "comp_num": "1", "year": 1973, "number": 1, "effective_date": "2025-01-01",
            "xml_path": "xml/old-name-act-1973.xml", "aliases": ["Even Older Name Act 1973"],
        },
        "current-name-act-1973": {
            "name": "Current Name Act 1973", "title_id": "T1", "comp_id": "C1",
            "comp_num": "1", "year": 1973, "number": 1, "effective_date": "2025-01-01",
            "xml_path": "xml/current-name-act-1973.xml", "aliases": [],
        },
    })

    result, _ = dedupe_by_title_id(index, lambda tid: "Current Name Act 1973")

    assert sorted(result["acts"]["current-name-act-1973"]["aliases"]) == [
        "Even Older Name Act 1973", "Old Name Act 1973",
    ]
