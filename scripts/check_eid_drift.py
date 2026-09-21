#!/usr/bin/env python3
"""Release gate: assert only ``schedule-*`` eIds move between two corpus builds.

Task 17 re-converts the full 3,076-Act corpus with the schedule-restructuring
fixes from Tasks 6/13 (family B4 + family C), which deliberately renumber and
rescope eIds inside ``<attachments>``. That is expected and allowed. The
guarantee this gate actually checks is narrower than "no body eId changes":
no body eId STRING may enter or leave the set of body eIds present for an
Act. A change in how many times an eId string repeats (see Known limitation
below) is NOT detected -- only a string fully appearing or disappearing is.
lex-au-graph keys 110,969 graph nodes off exact body eId strings, and any
body eId string entering/leaving the set silently breaks that project's node
identity.

Classification is ancestor-based, not a string-prefix heuristic on the eId
text: in this builder's AKN output, ``<attachments>`` is a sibling of
``<body>`` (appearing after it) and is the sole container for every
``<hcontainer name="schedule">``. An eId belongs to "schedule" if its element
has an ``<attachments>`` ancestor; it belongs to "body" if its element has a
``<body>`` ancestor instead. Elements with neither ancestor (e.g. ``<meta>``
eventRefs) are not structural and are ignored.

Known limitation -- duplicate eId strings are invisible to this gate:
``_structural_eids`` collapses an Act's eIds into a ``{eId: kind}`` dict, so
two elements sharing the same duplicated eId string collapse to one entry.
28,747 distinct body eIds are already duplicated across 960 real Acts (a
pre-existing defect class this plan does not fix). If a re-convert changes
how many times a duplicated eId string repeats (e.g. 2 copies -> 1) without
the string itself ever fully leaving the set, this gate will not flag it.
Deliberately not fixed here: distinguishing pre-existing duplicate-count
noise from a genuine new regression would require design beyond this task's
scope, and a naive multiset comparison would flood the gate with false
positives from the known duplicate defect class.

Usage:
    python scripts/check_eid_drift.py --old-dir corpus-old/xml --new-dir corpus/xml
"""
from __future__ import annotations

import argparse
import json
import sys
from itertools import zip_longest
from pathlib import Path

from lxml import etree

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"


def _local(tag: str) -> str:
    return etree.QName(tag).localname


def _classify(el: etree._Element) -> str | None:
    """Return "schedule" if `el` sits under <attachments>, "body" if under
    <body>, or None if under neither (not a structural element -- e.g. <meta>).
    """
    for ancestor in el.iterancestors():
        name = _local(ancestor.tag)
        if name == "attachments":
            return "schedule"
        if name == "body":
            return "body"
    return None


def _structural_eids(xml_path: Path) -> dict[str, str]:
    """Map every structural @eId in `xml_path` to its classification
    ("body" or "schedule"), in document order.
    """
    tree = etree.parse(str(xml_path))
    eids: dict[str, str] = {}
    for el in tree.getroot().iter():
        eid = el.get("eId")
        if eid is None:
            continue
        kind = _classify(el)
        if kind is None:
            continue
        eids[eid] = kind
    return eids


def matching_filenames(old_dir: Path, new_dir: Path) -> list[str]:
    """Sorted Act XML filenames present in both directories. A typo'd path,
    a nonexistent directory, or two corpora with nothing in common all
    produce an empty list here -- callers MUST treat an empty list as a
    failure to actually run the check, not as a clean pass (`Path.glob` on a
    missing directory silently returns nothing, so a bad path and "zero
    drift" are otherwise indistinguishable).
    """
    old_names = {p.name for p in Path(old_dir).glob("*.xml")}
    new_names = {p.name for p in Path(new_dir).glob("*.xml")}
    return sorted(old_names & new_names)


def eid_drift(old_dir: Path, new_dir: Path) -> dict[str, list[dict[str, str | None]]]:
    """Compare structural @eId sets across every matching Act filename in two
    corpus XML directories. Returns {"body_moved": [...], "schedule_moved":
    [...]}, each entry {"act": filename, "old_eid": str | None, "new_eid":
    str | None}. `old_eid`/`new_eid` is None when the eId was purely added or
    purely removed rather than paired as a rename.

    The release gate for Task 17 asserts `eid_drift(...)["body_moved"] == []`
    AND that at least one Act was actually compared (see `matching_filenames`
    and `main`'s zero-comparison guard) -- an empty result here is not
    itself proof of a clean corpus; it can equally mean nothing was compared.
    """
    old_dir = Path(old_dir)
    new_dir = Path(new_dir)

    body_moved: list[dict[str, str | None]] = []
    schedule_moved: list[dict[str, str | None]] = []

    for name in matching_filenames(old_dir, new_dir):
        old_eids = _structural_eids(old_dir / name)
        new_eids = _structural_eids(new_dir / name)

        # Document order is preserved by dict insertion order (Python 3.7+),
        # since _structural_eids walks the tree with etree's .iter().
        old_only = [eid for eid in old_eids if eid not in new_eids]
        new_only = [eid for eid in new_eids if eid not in old_eids]

        # Bucket by kind BEFORE pairing. <body> precedes <attachments> in
        # document order, so old_only/new_only each have all body-kind eIds
        # before all schedule-kind eIds -- pairing across the raw lists with
        # zip_longest would cross-pair a body-kind entry from one side with a
        # schedule-kind entry from the other whenever the two sides' body-only
        # counts differ, silently hiding a real body move inside
        # schedule_moved. Pairing within same-kind buckets makes that
        # impossible: a body-kind eid can only ever pair with another
        # body-kind eid (or None), never with a schedule-kind one.
        for kind, target in (("body", body_moved), ("schedule", schedule_moved)):
            old_kind_only = [eid for eid in old_only if old_eids[eid] == kind]
            new_kind_only = [eid for eid in new_only if new_eids[eid] == kind]
            for old_eid, new_eid in zip_longest(old_kind_only, new_kind_only):
                target.append({"act": name, "old_eid": old_eid, "new_eid": new_eid})

    return {"body_moved": body_moved, "schedule_moved": schedule_moved}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--old-dir", type=Path, required=True, help="Pre-re-convert corpus XML directory")
    ap.add_argument("--new-dir", type=Path, required=True, help="Freshly re-converted corpus XML directory")
    ap.add_argument("--out", type=Path, default=None, help="Optional path to write the full JSON report")
    ap.add_argument(
        "--min-acts", type=int, default=1,
        help="Fail if fewer than this many Acts were actually compared (default: 1, "
             "i.e. just guard against a typo'd/missing path or zero filename overlap). "
             "Pass e.g. --min-acts 3000 for a stronger corpus-size sanity check on a "
             "full-corpus run; not hardcoded here since the corpus size drifts.",
    )
    args = ap.parse_args()

    compared = matching_filenames(args.old_dir, args.new_dir)
    print(f"acts compared: {len(compared)}")
    if len(compared) < args.min_acts:
        print(
            f"FAIL: only {len(compared)} Act(s) compared (< --min-acts {args.min_acts}) -- "
            "check --old-dir/--new-dir for a typo or a directory with no matching XML "
            "filenames. Zero Acts compared looks identical to zero drift and must never "
            "be treated as a clean pass."
        )
        return 1

    result = eid_drift(args.old_dir, args.new_dir)

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
        print(f"wrote {args.out}")

    print(f"body_moved: {len(result['body_moved'])}")
    print(f"schedule_moved: {len(result['schedule_moved'])}")

    if result["body_moved"]:
        print("FAIL: body eIds moved -- lex-au-graph node identity would break:")
        for entry in result["body_moved"]:
            print(f"  {entry['act']}: {entry['old_eid']!r} -> {entry['new_eid']!r}")
        return 1

    print("PASS: only schedule eIds moved.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
