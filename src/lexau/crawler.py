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

    The OData spec escapes a single quote by doubling it, but
    api.prod.legislation.gov.au's implementation does not follow this:
    a doubled quote returns zero results (confirmed live 2026-07-09 against
    "Veterans' Entitlements Act 1986"), while an unescaped single quote inside
    the filter value round-trips correctly through requests' URL encoding and
    matches. Pass the value through unchanged rather than spec-escaping it.
    """
    return s


def _parse_year_from_name(name: str) -> int:
    """Parse year from Act name: last token if 4-digit number."""
    last = name.rsplit(None, 1)[-1]
    if last.isdigit() and len(last) == 4:
        return int(last)
    raise ValueError(f"Cannot parse year from Act name: {name!r}")


def _parse_number_from_title_id(title_id: str) -> int:
    """Parse the trailing numeric id from a titleId, e.g. C2004A03712 -> 3712.

    Tried in order: legacy Act (C{year}A{number}), legacy Regulation
    (C{year}R{number}), then modern F-prefixed instrument (F{year}{letter}
    {number} -- the API returns null `number` for some post-2015-framework
    instruments, e.g. "Family Law (Superannuation) Regulations 2025" =
    F2025L00178, confirmed live 2026-07-11).
    """
    for pattern in (_TITLE_ID_RE, _REG_RE, _INSTRUMENT_RE):
        m = pattern.match(title_id)
        if m:
            return int(m.group(1))
    raise ValueError(f"Cannot parse number from titleId: {title_id!r}")


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

    def _resolve_title(self, act_name: str) -> dict | None:
        """Resolve an Act/Regulation name to its Titles record, tolerating two
        OData quirks discovered during the 2026-07-10 corpus expansion:

        1. A literal apostrophe followed later in the same string by a
           parenthesized clause breaks the server's OData string-literal
           parser with a 400 (e.g. "Veterans' Entitlements (Transitional
           Provisions and Consequential Amendments) Act 1986") -- confirmed
           independent of eq vs contains(), and independent of spec-compliant
           quote-doubling (which the API's implementation doesn't honour;
           see _odata_escape). Some shorter apostrophe titles happen to parse
           fine unescaped, so this can't be handled by escaping alone.
        2. The API's edge/WAF blocks specific multi-word phrases outright
           with a 403 HTML error page (not the API's JSON error format),
           e.g. any query containing "Foreign Acquisitions and Takeovers"
           regardless of filter shape -- confirmed not a general outage,
           other queries succeed in parallel.

        Both are dodged the same way: drop the leading word(s) and retry via
        contains(), then confirm an exact case-insensitive full-name match
        before accepting -- a trimmed fragment doesn't reconstruct the exact
        title on its own.
        """
        try:
            titles = self._get(
                "Titles",
                {
                    "$filter": f"name eq '{_odata_escape(act_name)}' and isInForce eq true",
                    "$top": 1,
                    "$select": "id,name,year,number",
                },
            ).get("value", [])
            if titles:
                return titles[0]
            return None
        except requests.HTTPError:
            pass

        words = act_name.split()
        for drop in range(1, min(4, len(words))):
            frag = " ".join(words[drop:])
            if len(frag) < 6:
                continue
            time.sleep(0.3)
            try:
                candidates = self._get(
                    "Titles",
                    {
                        "$filter": f"contains(name,'{frag}') and isInForce eq true",
                        "$top": 10,
                        "$select": "id,name,year,number",
                    },
                ).get("value", [])
            except requests.HTTPError:
                continue
            exact = [c for c in candidates if c["name"].lower() == act_name.lower()]
            if len(exact) == 1:
                return exact[0]
        return None

    def fetch_metadata(self, act_name: str, doc_type: str = "act") -> ActMetadata | None:
        # Step 1: resolve series title ID
        t = self._resolve_title(act_name)
        if t is None:
            return None
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

    def fetch_volume_bytes(self, meta: ActMetadata, vol: int) -> bytes | None:
        """Fetch one volume's raw response bytes, whatever the underlying format.

        Unlike fetch_docx_volumes, does not filter on the DOCX ("PK") magic
        bytes -- used by the .doc-conversion spike (and, if it clears the
        go/no-go gate, the production doc-conversion path) to capture legacy
        OLE2/CFB ("\\xd0\\xcf\\x11\\xe0") binaries that fetch_docx_volumes
        silently discards.
        """
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
        if r.status_code != 200:
            return None
        return r.content

    def fetch_docx(self, meta: ActMetadata, dest_dir: Path) -> Path | None:
        """Backward-compat alias. cli.py switches to fetch_docx_volumes in Task 7."""
        paths = self.fetch_docx_volumes(meta, dest_dir)
        return paths[0] if paths else None

    def list_acts(self, page_size: int = 100) -> list[str]:
        """Return names of all in-force Commonwealth Acts, sorted alphabetically.

        Filters server-side on collection eq 'Act' (confirmed live 2026-07-12:
        returns exactly the ~4,747 real Acts directly, vs. the previous
        isInForce-only filter which walked all 51,246 titles of every type).
        _TITLE_ID_RE is kept as a defensive secondary check.
        """
        names: list[str] = []
        skip = 0
        while True:
            resp = self._get(
                "Titles",
                {
                    "$filter": "isInForce eq true and collection eq 'Act'",
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
            time.sleep(self._delay)
        return sorted(names)

    def list_instruments(self, page_size: int = 100) -> list[str]:
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
            time.sleep(self._delay)
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
