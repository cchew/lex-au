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


# Task 3: doc_type and list_instruments tests

REGULATION_TITLES_RESPONSE = {
    "value": [{
        "id": "F2002B00238",
        "name": "Therapeutic Goods (Medical Devices) Regulations 2002",
        "year": "2002",
        "number": "34",
    }]
}

REGULATION_VERSIONS_RESPONSE = {
    "value": [{
        "titleId": "F2002B00238",
        "registerId": "F2024C00100",
        "compilationNumber": "10",
        "start": "2024-01-01",
    }]
}


@resp_lib.activate
def test_fetch_metadata_with_doc_type_regulation():
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json=REGULATION_TITLES_RESPONSE)
    resp_lib.add(resp_lib.GET, f"{API}/Versions", json=REGULATION_VERSIONS_RESPONSE)

    crawler = Crawler()
    meta = crawler.fetch_metadata(
        "Therapeutic Goods (Medical Devices) Regulations 2002",
        doc_type="regulation",
    )

    assert meta is not None
    assert meta.doc_type == "regulation"
    assert "regulation" in meta.frbr_work_uri


@resp_lib.activate
def test_fetch_metadata_default_doc_type_is_act():
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json=TITLES_RESPONSE)
    resp_lib.add(resp_lib.GET, f"{API}/Versions", json=VERSIONS_RESPONSE)

    crawler = Crawler()
    meta = crawler.fetch_metadata("Privacy Act 1988")

    assert meta is not None
    assert meta.doc_type == "act"


@resp_lib.activate
def test_list_instruments_returns_non_act_names():
    # Mix of Act (C-prefix A-infix) and instrument/regulation (F-prefix) titleIds
    page = {
        "value": [
            {"id": "C2004A03712", "name": "Privacy Act 1988"},       # Act — exclude
            {"id": "F2002B00238", "name": "Therapeutic Goods (Medical Devices) Regulations 2002"},  # instrument — include
            {"id": "F2020L00100", "name": "Some Instrument 2020"},    # instrument — include
        ]
    }
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json=page)

    crawler = Crawler()
    names = crawler.list_instruments()

    assert "Privacy Act 1988" not in names
    assert "Therapeutic Goods (Medical Devices) Regulations 2002" in names
    assert "Some Instrument 2020" in names


@resp_lib.activate
def test_list_instruments_returns_sorted():
    page = {
        "value": [
            {"id": "F2020L00200", "name": "Zoo Regulations 2020"},
            {"id": "F2020L00100", "name": "Alpha Instrument 2020"},
        ]
    }
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json=page)

    crawler = Crawler()
    names = crawler.list_instruments()

    assert names == sorted(names)


@resp_lib.activate
def test_list_instruments_paginates():
    page1 = {
        "value": [{"id": f"F2020L{i:05d}", "name": f"Instrument {i}"} for i in range(200)]
    }
    page2 = {
        "value": [{"id": "F2020L99999", "name": "Last Instrument"}]
    }
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json=page1)
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json=page2)

    crawler = Crawler()
    names = crawler.list_instruments(page_size=200)

    assert len(names) == 201
    assert "Last Instrument" in names


@resp_lib.activate
def test_list_instruments_empty():
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json={"value": []})

    crawler = Crawler()
    names = crawler.list_instruments()

    assert names == []


@resp_lib.activate
def test_fetch_metadata_falls_back_to_contains_on_400():
    # eq query 400s (e.g. an apostrophe followed by a parenthesized clause
    # breaks the server's OData string-literal parser -- confirmed live
    # 2026-07-10 against "Veterans' Entitlements (Transitional Provisions
    # and Consequential Amendments) Act 1986"). Fallback drops the leading
    # word and retries via contains(), then confirms an exact name match.
    resp_lib.add(resp_lib.GET, f"{API}/Titles", status=400)
    resp_lib.add(
        resp_lib.GET,
        f"{API}/Titles",
        json={"value": [{
            "id": "C2004A03269",
            "name": "Veterans' Entitlements (Transitional Provisions and Consequential Amendments) Act 1986",
            "year": "1986",
            "number": "27",
        }]},
    )
    resp_lib.add(resp_lib.GET, f"{API}/Versions", json=VERSIONS_RESPONSE)

    crawler = Crawler()
    meta = crawler.fetch_metadata(
        "Veterans' Entitlements (Transitional Provisions and Consequential Amendments) Act 1986"
    )

    assert meta is not None
    assert meta.title_id == "C2004A03269"


@resp_lib.activate
def test_fetch_metadata_falls_back_to_contains_on_403():
    # eq query 403s (WAF false-positive on a specific multi-word phrase --
    # confirmed live 2026-07-10 against "Foreign Acquisitions and Takeovers
    # Act 1975", not a general API outage). Same fallback as the 400 case.
    resp_lib.add(resp_lib.GET, f"{API}/Titles", status=403)
    resp_lib.add(
        resp_lib.GET,
        f"{API}/Titles",
        json={"value": [{
            "id": "C2004A01402",
            "name": "Foreign Acquisitions and Takeovers Act 1975",
            "year": "1975",
            "number": "92",
        }]},
    )
    resp_lib.add(resp_lib.GET, f"{API}/Versions", json=VERSIONS_RESPONSE)

    crawler = Crawler()
    meta = crawler.fetch_metadata("Foreign Acquisitions and Takeovers Act 1975")

    assert meta is not None
    assert meta.title_id == "C2004A01402"


@resp_lib.activate
def test_fetch_metadata_fallback_rejects_ambiguous_contains_match():
    # If the contains() fallback's fragment matches more than one title
    # exactly (case-insensitive), don't guess -- fail closed.
    resp_lib.add(resp_lib.GET, f"{API}/Titles", status=400)
    resp_lib.add(
        resp_lib.GET,
        f"{API}/Titles",
        json={"value": [
            {"id": "C2004A01402", "name": "Ambiguous Act 1975"},
            {"id": "C2004A01403", "name": "Ambiguous Act 1975"},
        ]},
    )

    crawler = Crawler()
    assert crawler.fetch_metadata("Ambiguous Act 1975") is None


@resp_lib.activate
def test_fetch_metadata_parses_number_from_f_prefixed_instrument_id():
    # Some post-2015-framework instruments return null year/number from the
    # API (confirmed live 2026-07-11: "Family Law (Superannuation)
    # Regulations 2025" = F2025L00178, year=None, number=None). Both must
    # fall back to parsing from the name/titleId rather than raising.
    resp_lib.add(
        resp_lib.GET,
        f"{API}/Titles",
        json={"value": [{
            "id": "F2025L00178",
            "name": "Family Law (Superannuation) Regulations 2025",
            "year": None,
            "number": None,
        }]},
    )
    resp_lib.add(
        resp_lib.GET,
        f"{API}/Versions",
        json={"value": [{
            "titleId": "F2025L00178",
            "registerId": "F2025C00200",
            "compilationNumber": "1",
            "start": "2025-01-01",
        }]},
    )

    crawler = Crawler()
    meta = crawler.fetch_metadata(
        "Family Law (Superannuation) Regulations 2025", doc_type="regulation"
    )

    assert meta is not None
    assert meta.year == 2025
    assert meta.number == 178


@resp_lib.activate
def test_list_acts_filters_by_collection():
    page = {"value": [{"id": "C2004A03712", "name": "Privacy Act 1988"}]}
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json=page)

    crawler = Crawler()
    crawler.list_acts()

    request_url = resp_lib.calls[0].request.url
    assert "collection+eq+%27Act%27" in request_url or "collection eq 'Act'" in request_url.replace("+", " ")


@resp_lib.activate
def test_list_acts_default_page_size_is_100():
    page = {"value": [{"id": "C2004A03712", "name": "Privacy Act 1988"}]}
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json=page)

    crawler = Crawler()
    crawler.list_acts()

    request_url = resp_lib.calls[0].request.url
    assert "%24top=100" in request_url


@resp_lib.activate
def test_list_instruments_default_page_size_is_100():
    page = {"value": [{"id": "F2020L00100", "name": "Some Instrument 2020"}]}
    resp_lib.add(resp_lib.GET, f"{API}/Titles", json=page)

    crawler = Crawler()
    crawler.list_instruments()

    request_url = resp_lib.calls[0].request.url
    assert "%24top=100" in request_url
