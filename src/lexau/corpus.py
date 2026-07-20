from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from lxml import etree

from lexau.models import ActMetadata


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
        xml_path = self._xml_dir / f"{meta.safe_name}.xml"
        xml_path.write_bytes(
            etree.tostring(xml, pretty_print=True, xml_declaration=True, encoding="UTF-8")
        )

        index = self._read_index()
        entry = {
            "name": meta.name,
            "title_id": meta.title_id,
            "comp_id": meta.comp_id,
            "comp_num": meta.comp_num,
            "year": meta.year,
            "number": meta.number,
            "effective_date": meta.effective_date.isoformat(),
            "xml_path": str(xml_path.relative_to(self.root)),
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
                )
            )
        return result
