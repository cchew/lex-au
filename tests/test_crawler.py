import responses as resp_lib
import pytest
from pathlib import Path
from datetime import date
from lexau.crawler import Crawler


API = "https://api.prod.legislation.gov.au/v1"

TITLES_RESPONSE = {
    "value": [{
        "id": "C2004A03712",
        "name": "Privacy Act 1988",
        "year": "1988",
        "number": "119",
    }]
}

VERSIONS_RESPONSE = {
    "value": [{
        "titleId": "C2004A03712",
        "registerId": "C2024C00280",
        "compilationNumber": "52",
        "start": "2024-01-01",
    }]
}

DOCX_BYTES = b"PK\x03\x04" + b"\x00" * 100  # fake ZIP/DOCX magic bytes


@resp_lib.activate
def test_fetch_metadata_returns_act_metadata():
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json=TITLES_RESPONSE)
    resp_lib.add(resp_lib.GET, f"{API}/Versions", json=VERSIONS_RESPONSE)

    crawler = Crawler()
    meta = crawler.fetch_metadata("Privacy Act 1988")

    assert meta is not None
    assert meta.name == "Privacy Act 1988"
    assert meta.title_id == "C2004A03712"
    assert meta.comp_id == "C2024C00280"
    assert meta.comp_num == "52"
    assert meta.year == 1988
    assert meta.number == 119
    assert meta.effective_date.isoformat() == "2024-01-01"


@resp_lib.activate
def test_fetch_metadata_returns_none_for_unknown_act():
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json={"value": []})

    crawler = Crawler()
    assert crawler.fetch_metadata("Nonexistent Act 9999") is None


@resp_lib.activate
def test_fetch_docx_saves_file(tmp_path: Path):
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json=TITLES_RESPONSE)
    resp_lib.add(resp_lib.GET, f"{API}/Versions", json=VERSIONS_RESPONSE)
    resp_lib.add(resp_lib.GET, f"{API}/Documents", json={"value": [{"volumeNumber": 0}]})
    resp_lib.add(
        resp_lib.GET,
        f"{API}/documents/find(registerId='C2024C00280',type='Primary',format='Word',uniqueTypeNumber=0,volumeNumber=0,rectificationVersionNumber=0)",
        body=DOCX_BYTES,
        content_type="application/octet-stream",
    )

    crawler = Crawler(crawl_delay=0)  # no delay in tests
    meta = crawler.fetch_metadata("Privacy Act 1988")
    path = crawler.fetch_docx(meta, tmp_path)

    assert path is not None
    assert path.exists()
    assert path.read_bytes() == DOCX_BYTES


@resp_lib.activate
def test_list_modified_since_returns_act_names():
    resp_lib.add(
        resp_lib.GET,
        f"{API}/Versions",
        json={"value": [
            {"titleId": "C2004A03712"},
            {"titleId": "C2009A00028"},
        ]},
    )
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json={"value": [{"name": "Privacy Act 1988"}]})
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json={"value": [{"name": "Fair Work Act 2009"}]})

    crawler = Crawler()
    names = crawler.list_modified_since(date(2026, 1, 1))
    assert "Privacy Act 1988" in names
