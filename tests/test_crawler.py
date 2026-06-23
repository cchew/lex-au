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


@resp_lib.activate
def test_fetch_docx_volumes_single_volume(tmp_path: Path):
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json=TITLES_RESPONSE)
    resp_lib.add(resp_lib.GET, f"{API}/Versions", json=VERSIONS_RESPONSE)
    resp_lib.add(resp_lib.GET, f"{API}/Documents", json={"value": [{"volumeNumber": 0}]})
    resp_lib.add(
        resp_lib.GET,
        f"{API}/documents/find(registerId='C2024C00280',type='Primary',format='Word',uniqueTypeNumber=0,volumeNumber=0,rectificationVersionNumber=0)",
        body=DOCX_BYTES,
        content_type="application/octet-stream",
    )

    crawler = Crawler(crawl_delay=0)
    meta = crawler.fetch_metadata("Privacy Act 1988")
    paths = crawler.fetch_docx_volumes(meta, tmp_path)

    assert len(paths) == 1
    assert paths[0].exists()
    assert paths[0].read_bytes() == DOCX_BYTES


@resp_lib.activate
def test_fetch_docx_volumes_multi_volume(tmp_path: Path):
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json=TITLES_RESPONSE)
    resp_lib.add(resp_lib.GET, f"{API}/Versions", json=VERSIONS_RESPONSE)
    resp_lib.add(resp_lib.GET, f"{API}/Documents", json={
        "value": [{"volumeNumber": 0}, {"volumeNumber": 1}]
    })
    resp_lib.add(
        resp_lib.GET,
        f"{API}/documents/find(registerId='C2024C00280',type='Primary',format='Word',uniqueTypeNumber=0,volumeNumber=0,rectificationVersionNumber=0)",
        body=DOCX_BYTES,
        content_type="application/octet-stream",
    )
    resp_lib.add(
        resp_lib.GET,
        f"{API}/documents/find(registerId='C2024C00280',type='Primary',format='Word',uniqueTypeNumber=0,volumeNumber=1,rectificationVersionNumber=0)",
        body=DOCX_BYTES,
        content_type="application/octet-stream",
    )

    crawler = Crawler(crawl_delay=0)
    meta = crawler.fetch_metadata("Privacy Act 1988")
    paths = crawler.fetch_docx_volumes(meta, tmp_path)

    assert len(paths) == 2
    assert paths[0].name.endswith("vol0.docx")
    assert paths[1].name.endswith("vol1.docx")


@resp_lib.activate
def test_fetch_metadata_populates_long_title():
    titles_with_long_title = {
        "value": [{
            "id": "C2004A03712",
            "name": "Privacy Act 1988",
            "year": "1988",
            "number": "119",
            "longTitle": "An Act to protect privacy",
        }]
    }
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json=titles_with_long_title)
    resp_lib.add(resp_lib.GET, f"{API}/Versions", json=VERSIONS_RESPONSE)

    crawler = Crawler()
    meta = crawler.fetch_metadata("Privacy Act 1988")

    assert meta is not None
    assert meta.long_title == "An Act to protect privacy"


@resp_lib.activate
def test_fetch_metadata_populates_subject_keywords_from_list():
    titles_with_subjects = {
        "value": [{
            "id": "C2004A03712",
            "name": "Privacy Act 1988",
            "year": "1988",
            "number": "119",
            "subjects": ["Privacy", "Data Protection"],
        }]
    }
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json=titles_with_subjects)
    resp_lib.add(resp_lib.GET, f"{API}/Versions", json=VERSIONS_RESPONSE)

    crawler = Crawler()
    meta = crawler.fetch_metadata("Privacy Act 1988")

    assert meta is not None
    assert meta.subject_keywords == ["Privacy", "Data Protection"]


@resp_lib.activate
def test_fetch_metadata_populates_subject_keywords_from_string():
    titles_with_subjects = {
        "value": [{
            "id": "C2004A03712",
            "name": "Privacy Act 1988",
            "year": "1988",
            "number": "119",
            "subjects": "Privacy, Data Protection",
        }]
    }
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json=titles_with_subjects)
    resp_lib.add(resp_lib.GET, f"{API}/Versions", json=VERSIONS_RESPONSE)

    crawler = Crawler()
    meta = crawler.fetch_metadata("Privacy Act 1988")

    assert meta is not None
    assert meta.subject_keywords == ["Privacy", "Data Protection"]


@resp_lib.activate
def test_fetch_metadata_subject_keywords_defaults_to_empty():
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json=TITLES_RESPONSE)
    resp_lib.add(resp_lib.GET, f"{API}/Versions", json=VERSIONS_RESPONSE)

    crawler = Crawler()
    meta = crawler.fetch_metadata("Privacy Act 1988")

    assert meta is not None
    assert meta.subject_keywords == []


@resp_lib.activate
def test_fetch_docx_volumes_returns_empty_on_bad_response(tmp_path: Path):
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json=TITLES_RESPONSE)
    resp_lib.add(resp_lib.GET, f"{API}/Versions", json=VERSIONS_RESPONSE)
    resp_lib.add(resp_lib.GET, f"{API}/Documents", json={"value": [{"volumeNumber": 0}]})
    resp_lib.add(
        resp_lib.GET,
        f"{API}/documents/find(registerId='C2024C00280',type='Primary',format='Word',uniqueTypeNumber=0,volumeNumber=0,rectificationVersionNumber=0)",
        body=b"not a zip",
        content_type="application/octet-stream",
    )

    crawler = Crawler(crawl_delay=0)
    meta = crawler.fetch_metadata("Privacy Act 1988")
    paths = crawler.fetch_docx_volumes(meta, tmp_path)

    assert paths == []
