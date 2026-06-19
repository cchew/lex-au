def make_section_eid(num: str) -> str:
    return f"sec-{num}"

def make_part_eid(num: str) -> str:
    return f"part-{num}"

def make_division_eid(num: str) -> str:
    return f"dvs-{num}"

def make_chapter_eid(num: str) -> str:
    return f"chapter-{num}"

def make_eid(element_type_value: str, num: str) -> str:
    """Generic eId dispatcher; element_type_value is ElementType.value."""
    return f"{element_type_value}-{num}"
