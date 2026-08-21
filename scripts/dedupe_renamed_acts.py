"""One-off migration: collapse Acts ingested twice under an old and new name.

See docs/superpowers/specs/2026-08-21-duplicate-act-ingest-dedup-design.md
(EA wrapper repo) for the full root-cause writeup. Corpus.save() (fixed in
the same change series) prevents new duplicates going forward; this script
cleans up the entries that were already ingested before that fix landed.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Callable

import requests

from lexau.corpus import orphan_asset_globs

API_BASE = "https://api.prod.legislation.gov.au/v1"


def dedupe_by_title_id(
    index: dict, resolve_canonical_name: Callable[[str], str]
) -> tuple[dict, list[str], list[str]]:
    """Collapse index['acts'] entries that share a title_id.

    Returns the updated index (new dict, input not mutated), the list of
    root-relative xml_path values whose files should be deleted from disk,
    and a list of root-relative glob patterns for the collapsed entries'
    now-orphaned report/docx files (those aren't recorded as a single exact
    path in the index the way xml_path is, so a pattern per key is
    computed instead -- see corpus.orphan_asset_globs).
    """
    by_title_id: dict[str, list[str]] = defaultdict(list)
    for key, entry in index["acts"].items():
        by_title_id[entry["title_id"]].append(key)

    new_acts = dict(index["acts"])
    to_delete: list[str] = []
    to_delete_globs: list[str] = []

    for title_id, keys in by_title_id.items():
        if len(keys) < 2:
            continue
        canonical_name = resolve_canonical_name(title_id)
        survivor_key = next(
            (k for k in keys if new_acts[k]["name"] == canonical_name), None
        )
        if survivor_key is None:
            raise ValueError(
                f"No entry for title_id={title_id!r} matches canonical name "
                f"{canonical_name!r}; found names: "
                f"{[new_acts[k]['name'] for k in keys]}"
            )

        aliases = set(new_acts[survivor_key].get("aliases", []))
        for key in keys:
            if key == survivor_key:
                continue
            aliases.add(new_acts[key]["name"])
            aliases.update(new_acts[key].get("aliases", []))
            to_delete.append(new_acts[key]["xml_path"])
            report_glob, docx_globs = orphan_asset_globs(key)
            to_delete_globs.append(f"reports/{report_glob}")
            to_delete_globs.extend(f"docx/{g}" for g in docx_globs)
            del new_acts[key]
        aliases.discard(canonical_name)
        new_acts[survivor_key] = {**new_acts[survivor_key], "aliases": sorted(aliases)}

    return {**index, "acts": new_acts}, to_delete, to_delete_globs


def _live_resolve_canonical_name(title_id: str) -> str:
    r = requests.get(
        f"{API_BASE}/Titles",
        params={"$filter": f"id eq '{title_id}'", "$select": "id,name"},
        timeout=30,
    )
    r.raise_for_status()
    values = r.json().get("value", [])
    if not values:
        raise ValueError(f"No live Titles record found for title_id={title_id!r}")
    return values[0]["name"]


def main(corpus_dir: Path) -> None:
    index_path = corpus_dir / "index.json"
    index = json.loads(index_path.read_text())
    before = len(index["acts"])

    new_index, to_delete, to_delete_globs = dedupe_by_title_id(index, _live_resolve_canonical_name)

    for rel_path in to_delete:
        xml_path = corpus_dir / rel_path
        if xml_path.exists():
            xml_path.unlink()
            print(f"Deleted {xml_path}")

    for pattern in to_delete_globs:
        for asset_path in corpus_dir.glob(pattern):
            asset_path.unlink()
            print(f"Deleted {asset_path}")

    index_path.write_text(json.dumps(new_index, indent=2, default=str))
    after = len(new_index["acts"])
    print(f"Acts: {before} -> {after} ({before - after} duplicate(s) collapsed)")


if __name__ == "__main__":
    corpus_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("corpus")
    main(corpus_dir)
