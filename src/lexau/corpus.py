from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from lxml import etree

from lexau.models import ActMetadata


def orphan_asset_globs(key: str) -> tuple[str, list[str]]:
    """(report_glob, docx_globs) filename patterns for a corpus key's
    report/docx files -- e.g. the entry a title_id-merge or dedup migration
    just collapsed away, whose XML is already deleted via its exact
    `xml_path` but whose report/docx were never recorded as a single path.

    Report filenames are `{key}-v{version}.json` (cli.py's `_build_acts`);
    docx filenames are `{key}-c{comp_num}-vol{vol}.docx`, or, for downloads
    predating comp_num-in-filename, `{key}-vol{vol}.docx`
    (crawler.py's `fetch_docx_volumes`) -- an Act can have multiple volumes,
    hence a glob rather than one exact name.

    Patterns are anchored on the literal marker (-v, -c, -vol) immediately
    after `key`, not a bare f"{key}-*" wildcard, so a key that happens to be
    a string-prefix of a different Act's safe_name (e.g. "act-1996" vs.
    "act-1996-amendment-act-2020") can't accidentally match that other Act's
    files.
    """
    report_glob = f"{key}-v[0-9]*.json"
    docx_globs = [f"{key}-c[0-9]*-vol*.docx", f"{key}-vol[0-9]*.docx"]
    return report_glob, docx_globs


class Corpus:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._xml_dir = root / "xml"
        self._index_path = root / "index.json"
        self._xml_dir.mkdir(parents=True, exist_ok=True)
        if not self._index_path.exists():
            self._write_index({"acts": {}, "updated_at": None})

    def _read_index(self) -> dict:
        return json.loads(self._index_path.read_text())

    def _write_index(self, data: dict) -> None:
        self._index_path.write_text(json.dumps(data, indent=2, default=str))

    def save(self, meta: ActMetadata, xml: etree._Element, source_format: str | None = None) -> Path:
        index = self._read_index()

        # Trusts meta.name as canonical without re-verifying against the API --
        # safe because fetch_metadata() (crawler.py) always resolves the
        # canonical name before save() is ever called; the CLI's build command
        # is the only caller. If a future caller can pass an unverified name,
        # this merge logic would need its own canonical-name check.
        aliases = set(meta.aliases)
        for key, existing in list(index["acts"].items()):
            if existing["title_id"] == meta.title_id and key != meta.safe_name:
                aliases.add(existing["name"])
                aliases.update(existing.get("aliases", []))
                old_xml_path = self.root / existing["xml_path"]
                if old_xml_path.exists():
                    old_xml_path.unlink()
                report_glob, docx_globs = orphan_asset_globs(key)
                for old_report in (self.root / "reports").glob(report_glob):
                    old_report.unlink()
                for docx_glob in docx_globs:
                    for old_docx in (self.root / "docx").glob(docx_glob):
                        old_docx.unlink()
                del index["acts"][key]
        aliases.discard(meta.name)

        xml_path = self._xml_dir / f"{meta.safe_name}.xml"
        xml_path.write_bytes(
            etree.tostring(xml, pretty_print=True, xml_declaration=True, encoding="UTF-8")
        )

        entry = {
            "name": meta.name,
            "title_id": meta.title_id,
            "comp_id": meta.comp_id,
            "comp_num": meta.comp_num,
            "year": meta.year,
            "number": meta.number,
            "effective_date": meta.effective_date.isoformat(),
            "xml_path": str(xml_path.relative_to(self.root)),
            "aliases": sorted(aliases),
        }
        if source_format is not None:
            entry["source_format"] = source_format
        index["acts"][meta.safe_name] = entry
        index["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_index(index)
        return xml_path

    def is_current(self, meta: ActMetadata) -> bool:
        index = self._read_index()
        entry = index["acts"].get(meta.safe_name)
        if entry is None:
            return False
        return entry["comp_num"] == meta.comp_num

    def all_metadata(self) -> list[ActMetadata]:
        index = self._read_index()
        result = []
        for entry in index["acts"].values():
            result.append(
                ActMetadata(
                    name=entry["name"],
                    title_id=entry["title_id"],
                    comp_id=entry["comp_id"],
                    comp_num=entry["comp_num"],
                    year=entry["year"],
                    number=entry["number"],
                    effective_date=date.fromisoformat(entry["effective_date"]),
                    aliases=entry.get("aliases", []),
                )
            )
        return result
