"""One-off verification: run complete_list_definitions against every
existing corpus/xml/*.xml file (WITHOUT writing anything back) and report
how many <def> elements it would complete, cross-checked against the spec's
verified count (3,136 qualifying cases across the corpus).

This does NOT rebuild the corpus -- it re-parses each already-built XML file,
runs complete_list_definitions on an in-memory copy, and reports counts. The
actual corpus rebuild (which re-runs the full lexau build pipeline from DOCX)
is Task 5, gated on this script's output looking correct.
"""
import glob
from lxml import etree
from lexau.termlinks import complete_list_definitions

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
AKN = f"{{{AKN_NS}}}"


def main() -> None:
    total_completed = 0
    total_files_affected = 0
    errors = []

    for path in sorted(glob.glob("corpus/xml/*.xml")):
        try:
            root = etree.parse(path).getroot()
        except etree.XMLSyntaxError as e:
            errors.append((path, str(e)))
            continue
        count = complete_list_definitions(root)
        if count > 0:
            total_files_affected += 1
            total_completed += count

    print(f"Files affected: {total_files_affected}")
    print(f"<def> elements completed: {total_completed}")
    print(f"Parse errors: {len(errors)}")
    for path, err in errors[:10]:
        print(f"  {path}: {err}")

    print()
    print("Spot-check: bankruptcy-act-1966.xml related-entity / relative pair")
    root = etree.parse("corpus/xml/bankruptcy-act-1966.xml").getroot()
    complete_list_definitions(root)

    related_entity_def = None
    for def_el in root.iter(f"{AKN}def"):
        p_text = "".join(def_el.getparent().itertext())
        if p_text.startswith("related entity"):
            related_entity_def = def_el
            break

    assert related_entity_def is not None, "related-entity <def> not found -- corpus structure may have changed"
    related_text = "".join(related_entity_def.itertext())
    print(f"  related-entity <def> length after: {len(related_text)} chars")
    assert "spouse of the person" not in related_text, \
        "REGRESSION: related-entity swallowed relative's list"
    assert "relative, in relation to a person" not in related_text, \
        "REGRESSION: related-entity swallowed relative's own untagged lead-in text"

    # "relative" is expected to remain untagged (no <term>/<def> at all) --
    # a separate, known, out-of-scope gap in inject_list_defs (see Global
    # Constraints). This spot-check confirms that gap wasn't papered over by
    # accidentally absorbing relative's content into related-entity instead.
    relative_tagged = any(
        "relative" == (t.text or "").strip()
        for t in root.iter(f"{AKN}term")
    )
    print(f"  'relative' tagged as its own <term>: {relative_tagged} (expected: False -- known separate gap)")

    print("  Spot-check passed: no cross-contamination between the two definitions.")


if __name__ == "__main__":
    main()
