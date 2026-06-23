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
