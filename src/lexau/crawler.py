import re
import time
from datetime import date
from pathlib import Path

import requests

from lexau.models import ActMetadata

API_BASE = "https://api.prod.legislation.gov.au/v1"

_TITLE_ID_RE = re.compile(r"C\d{4}A(\d+)")


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

    def fetch_metadata(self, act_name: str) -> ActMetadata | None:
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

        return ActMetadata(
            name=act_name,
            title_id=title_id,
            comp_id=v["registerId"],
            comp_num=v["compilationNumber"],
            year=year,
            number=number,
            effective_date=date.fromisoformat(v["start"][:10]),
        )

    def fetch_docx(self, meta: ActMetadata, dest_dir: Path) -> Path | None:
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Check available volumes
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
        vol = volumes[0]
        time.sleep(0.3)

        dest = dest_dir / f"{meta.safe_name}-vol{vol}.docx"
        if dest.exists():
            return dest

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
            return None
        dest.write_bytes(r.content)
        time.sleep(self._delay)
        return dest

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
