import re
import time
from datetime import date
from pathlib import Path

import requests

from lexau.models import ActMetadata

API_BASE = "https://api.prod.legislation.gov.au/v1"

_TITLE_ID_RE = re.compile(r"C\d{4}A(\d+)")
_INSTRUMENT_RE = re.compile(r"F\d{4}[A-Z](\d+)")  # F-prefixed = legislative instruments; reserved for future filter-by-type logic
_REG_RE = re.compile(r"C\d{4}R(\d+)")  # C-prefixed with R = regulations; reserved for future filter-by-type logic


def _odata_escape(s: str) -> str:
    """Escape a string literal for use inside an OData $filter value.

    OData escapes a single quote by doubling it, e.g.
    "Children's Education Act" -> "Children''s Education Act".
    """
    return s.replace("'", "''")


def _parse_year_from_name(name: str) -> int:
    """Parse year from Act name: last token if 4-digit number."""
    last = name.rsplit(None, 1)[-1]
    if last.isdigit() and len(last) == 4:
        return int(last)
    raise ValueError(f"Cannot parse year from Act name: {name!r}")


def _parse_number_from_title_id(title_id: str) -> int:
    """Parse Act number from titleId format C{year}A{number}, e.g. C2004A03712 -> 3712."""
    m = _TITLE_ID_RE.match(title_id)
    if not m:
        raise ValueError(f"Cannot parse number from titleId: {title_id!r}")
    return int(m.group(1))


class Crawler:
    def __init__(self, crawl_delay: float = 1.5, timeout: int = 60) -> None:
        self._delay = crawl_delay
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"Accept": "application/json"})

    def _get(self, path: str, params: dict | None = None) -> dict:
        r = self._session.get(f"{API_BASE}/{path}", params=params, timeout=self._timeout)
        r.raise_for_status()
        return r.json()

    def fetch_metadata(self, act_name: str, doc_type: str = "act") -> ActMetadata | None:
        # Step 1: resolve series title ID
        titles = self._get(
            "Titles",
            {
                "$filter": f"name eq '{_odata_escape(act_name)}' and isInForce eq true",
                "$top": 1,
                "$select": "id,name,year,number",
            },
        ).get("value", [])
        if not titles:
            return None
        t = titles[0]
        title_id: str = t["id"]

        # year/number may be absent from the API response — fall back if needed
        raw_year = t.get("year")
        raw_number = t.get("number")
        year = int(raw_year) if raw_year is not None else _parse_year_from_name(act_name)
        number = int(raw_number) if raw_number is not None else _parse_number_from_title_id(title_id)

        time.sleep(0.3)

        # Step 2: latest compilation
        versions = self._get(
            "Versions",
            {
                "$filter": f"titleId eq '{_odata_escape(title_id)}' and isLatest eq true",
                "$top": 1,
                "$select": "titleId,registerId,compilationNumber,start",
            },
        ).get("value", [])
        if not versions:
            return None
        v = versions[0]
        time.sleep(0.3)

        raw_subjects = t.get("subjects") or []
        subject_keywords = raw_subjects if isinstance(raw_subjects, list) else [s.strip() for s in raw_subjects.split(",") if s.strip()]

        return ActMetadata(
            name=act_name,
            title_id=title_id,
            comp_id=v["registerId"],
            comp_num=v["compilationNumber"],
            year=year,
            number=number,
            effective_date=date.fromisoformat(v["start"][:10]),
            long_title=t.get("longTitle") or "",
            subject_keywords=subject_keywords,
            doc_type=doc_type,
        )

    def fetch_docx_volumes(self, meta: ActMetadata, dest_dir: Path) -> list[Path]:
        """Fetch all volumes for an Act and return ordered list of DOCX paths.

        Returns empty list if no valid DOCX is found for any volume.
        """
        dest_dir.mkdir(parents=True, exist_ok=True)

        volumes_resp = self._get(
            "Documents",
            {
                "$filter": (
                    f"titleId eq '{_odata_escape(meta.title_id)}'"
                    f" and registerId eq '{_odata_escape(meta.comp_id)}'"
                    " and format eq 'Word'"
                ),
                "$select": "volumeNumber",
                "$orderby": "volumeNumber asc",
            },
        ).get("value", [])
        volumes = sorted({v["volumeNumber"] for v in volumes_resp}) if volumes_resp else [0]

        paths: list[Path] = []
        for vol in volumes:
            dest = dest_dir / f"{meta.safe_name}-vol{vol}.docx"
            if not dest.exists():
                time.sleep(self._delay)
                url = (
                    f"{API_BASE}/documents/find("
                    f"registerId='{meta.comp_id}',"
                    f"type='Primary',"
                    f"format='Word',"
                    f"uniqueTypeNumber=0,"
                    f"volumeNumber={vol},"
                    f"rectificationVersionNumber=0)"
                )
                r = self._session.get(
                    url,
                    headers={"Accept": "application/octet-stream"},
                    timeout=self._timeout,
                )
                if r.status_code != 200 or not r.content.startswith(b"PK"):
                    return []
                dest.write_bytes(r.content)
            paths.append(dest)

        return paths

    def fetch_docx(self, meta: ActMetadata, dest_dir: Path) -> Path | None:
        """Backward-compat alias. cli.py switches to fetch_docx_volumes in Task 7."""
        paths = self.fetch_docx_volumes(meta, dest_dir)
        return paths[0] if paths else None

    def list_acts(self, page_size: int = 200) -> list[str]:
        """Return names of all in-force Commonwealth Acts, sorted alphabetically.

        Paginates the Titles endpoint and filters by titleId pattern (C{year}A{number})
        to exclude legislative instruments and other non-Act titles.
        """
        names: list[str] = []
        skip = 0
        while True:
            resp = self._get(
                "Titles",
                {
                    "$filter": "isInForce eq true",
                    "$select": "id,name",
                    "$top": page_size,
                    "$skip": skip,
                    "$orderby": "name asc",
                },
            )
            page = resp.get("value", [])
            if not page:
                break
            for item in page:
                if _TITLE_ID_RE.match(item.get("id", "")):
                    names.append(item["name"])
            skip += page_size
            if len(page) < page_size:
                break
            time.sleep(0.5)
        return sorted(names)

    def list_instruments(self, page_size: int = 200) -> list[str]:
        """Return names of all in-force Commonwealth legislative instruments."""
        names: list[str] = []
        skip = 0
        while True:
            resp = self._get(
                "Titles",
                {
                    "$filter": "isInForce eq true",
                    "$select": "id,name",
                    "$top": page_size,
                    "$skip": skip,
                    "$orderby": "name asc",
                },
            )
            page = resp.get("value", [])
            if not page:
                break
            for item in page:
                tid = item.get("id", "")
                if not _TITLE_ID_RE.match(tid):  # exclude Acts
                    names.append(item["name"])
            skip += page_size
            if len(page) < page_size:
                break
            time.sleep(0.5)
        return sorted(names)

    def list_modified_since(self, since: date) -> list[str]:
        """Return Act names whose latest compilation started after `since`."""
        since_str = since.isoformat()
        versions = self._get(
            "Versions",
            {
                "$filter": f"isLatest eq true and start gt '{_odata_escape(since_str)}'",
                "$select": "titleId",
            },
        ).get("value", [])

        names: list[str] = []
        for v in versions:
            title_resp = self._get(
                "Titles",
                {
                    "$filter": f"id eq '{_odata_escape(v['titleId'])}'",
                    "$top": 1,
                    "$select": "name",
                },
            ).get("value", [])
            if title_resp:
                names.append(title_resp[0]["name"])
            time.sleep(0.3)
        return names
