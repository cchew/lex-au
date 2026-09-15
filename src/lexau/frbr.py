import re


def _normalize_eid_num(num: str) -> str:
    """Normalize eId number: strip whitespace and collapse internal spaces to underscore."""
    num = num.strip()
    num = re.sub(r"\s+", "_", num)
    return num


def make_section_eid(num: str) -> str:
    return f"sec-{_normalize_eid_num(num)}"

def make_part_eid(num: str) -> str:
    return f"part-{_normalize_eid_num(num)}"

def make_division_eid(num: str) -> str:
    return f"dvs-{_normalize_eid_num(num)}"

def make_chapter_eid(num: str) -> str:
    return f"chapter-{_normalize_eid_num(num)}"

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
    num = _normalize_eid_num(num)
    # AKN-NC §3.5: level4 numbers come from DOCX as uppercase (A)(B); normalise to lowercase
    if element_type_value == "level4":
        num = num.lower()
    return f"{prefix}-{num}"
