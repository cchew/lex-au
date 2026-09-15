from lexau.frbr import make_section_eid, make_part_eid, make_division_eid, make_chapter_eid, make_eid


def test_section_eid_simple():
    assert make_section_eid("4") == "sec-4"

def test_section_eid_alphanumeric():
    assert make_section_eid("2A") == "sec-2A"

def test_section_eid_hyphenated():
    assert make_section_eid("2A-1") == "sec-2A-1"

def test_part_eid_roman():
    assert make_part_eid("I") == "part-I"

def test_part_eid_decimal():
    assert make_part_eid("1-1") == "part-1-1"

def test_division_eid():
    assert make_division_eid("3") == "dvs-3"

def test_chapter_eid():
    assert make_chapter_eid("1") == "chapter-1"


def test_make_eid_level4_lowercase():
    assert make_eid("level4", "A") == "level4-a"


def test_make_eid_level4_multi_char():
    assert make_eid("level4", "AA") == "level4-aa"


def test_make_eid_existing_section_unchanged():
    # Confirm existing behaviour is unaffected
    assert make_eid("section", "16") == "sec-16"


def test_section_eid_trailing_whitespace():
    """eId with trailing whitespace must be stripped."""
    eid = make_section_eid("4 ")
    assert eid == "sec-4"
    assert " " not in eid


def test_part_eid_trailing_whitespace():
    """eId with trailing whitespace must be stripped."""
    eid = make_part_eid("4 ")
    assert eid == "part-4"
    assert " " not in eid


def test_division_eid_trailing_whitespace():
    """eId with trailing whitespace must be stripped."""
    eid = make_division_eid("3 ")
    assert eid == "dvs-3"
    assert " " not in eid


def test_chapter_eid_trailing_whitespace():
    """eId with trailing whitespace must be stripped."""
    eid = make_chapter_eid("1 ")
    assert eid == "chapter-1"
    assert " " not in eid


def test_section_eid_internal_whitespace():
    """eId with internal whitespace must collapse to underscore."""
    eid = make_section_eid("4 A")
    assert eid == "sec-4_A"
    assert " " not in eid


def test_make_eid_trailing_whitespace():
    """make_eid must strip trailing whitespace."""
    eid = make_eid("section", "16 ")
    assert eid == "sec-16"
    assert " " not in eid


def test_make_eid_internal_whitespace():
    """make_eid must collapse internal whitespace to underscore."""
    eid = make_eid("part", "1 A")
    assert eid == "part-1_A"
    assert " " not in eid


def test_make_eid_multiple_internal_spaces():
    """make_eid must collapse multiple spaces to single underscore."""
    eid = make_eid("section", "4A   B")
    assert eid == "sec-4A_B"
    assert "  " not in eid
