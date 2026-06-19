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
}


def make_eid(element_type_value: str, num: str) -> str:
    """Generic eId dispatcher; element_type_value is ElementType.value."""
    prefix = _EID_PREFIX.get(element_type_value, element_type_value)
    return f"{prefix}-{num}"
