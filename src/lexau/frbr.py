def make_section_eid(num: str) -> str:
    return f"sec-{num}"

def make_part_eid(num: str) -> str:
    return f"part-{num}"

def make_division_eid(num: str) -> str:
    return f"dvs-{num}"

def make_chapter_eid(num: str) -> str:
    return f"chapter-{num}"

_EID_PREFIX = {
    "chapter":     "chapter",
    "part":        "part",
    "dvs":         "dvs",
    "subdvs":      "subdvs",
    "section":     "sec",
    "level4":      "level4",
}


def make_eid(element_type_value: str, num: str) -> str:
    """Generic eId dispatcher; element_type_value is ElementType.value."""
    prefix = _EID_PREFIX.get(element_type_value, element_type_value)
    # AKN-NC §3.5: level4 numbers come from DOCX as uppercase (A)(B); normalise to lowercase
    if element_type_value == "level4":
        num = num.lower()
    return f"{prefix}-{num}"
