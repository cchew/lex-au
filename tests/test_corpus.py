import json
import pytest
from pathlib import Path
from lxml import etree
from lxml.builder import ElementMaker
from datetime import date
from lexau.corpus import Corpus
from lexau.models import ActMetadata

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"


@pytest.fixture
def corpus(tmp_path):
    return Corpus(tmp_path)


@pytest.fixture
def minimal_xml():
    AKN = ElementMaker(namespace=AKN_NS, nsmap={None: AKN_NS})
    return AKN.akomaNtoso(AKN.act(AKN.body(), name="act"))


def test_save_writes_xml_file(corpus, privacy_meta, minimal_xml):
    path = corpus.save(privacy_meta, minimal_xml)
    assert path.exists()
    assert path.suffix == ".xml"


def test_save_updates_index(corpus, privacy_meta, minimal_xml):
    corpus.save(privacy_meta, minimal_xml)
    index = json.loads((corpus.root / "index.json").read_text())
    assert "privacy-act-1988" in index["acts"]
    entry = index["acts"]["privacy-act-1988"]
    assert entry["comp_num"] == "52"
    assert entry["year"] == 1988


def test_save_records_source_format_when_provided(corpus, privacy_meta, minimal_xml):
    corpus.save(privacy_meta, minimal_xml, source_format="doc-converted")
    index = json.loads((corpus.root / "index.json").read_text())
    assert index["acts"]["privacy-act-1988"]["source_format"] == "doc-converted"


def test_save_omits_source_format_by_default(corpus, privacy_meta, minimal_xml):
    corpus.save(privacy_meta, minimal_xml)
    index = json.loads((corpus.root / "index.json").read_text())
    assert "source_format" not in index["acts"]["privacy-act-1988"]


def test_is_current_true_when_comp_num_matches(corpus, privacy_meta, minimal_xml):
    corpus.save(privacy_meta, minimal_xml)
    assert corpus.is_current(privacy_meta) is True


def test_is_current_false_for_new_compilation(corpus, privacy_meta, minimal_xml):
    corpus.save(privacy_meta, minimal_xml)
    updated = ActMetadata(
        name=privacy_meta.name,
        title_id=privacy_meta.title_id,
        comp_id="C2025C00001",
        comp_num="53",  # newer compilation
        year=privacy_meta.year,
        number=privacy_meta.number,
        effective_date=date(2025, 1, 1),
    )
    assert corpus.is_current(updated) is False


def test_all_metadata_round_trips(corpus, privacy_meta, minimal_xml):
    corpus.save(privacy_meta, minimal_xml)
    metas = corpus.all_metadata()
    assert len(metas) == 1
    assert metas[0].name == "Privacy Act 1988"
    assert metas[0].year == 1988


def test_save_merges_into_existing_entry_on_title_id_match(corpus, minimal_xml):
    old_meta = ActMetadata(
        name="Health Insurance Commission Act 1973",
        title_id="C2004A00100",
        comp_id="C2025C00609",
        comp_num="51",
        year=1974,
        number=41,
        effective_date=date(2025, 11, 1),
    )
    corpus.save(old_meta, minimal_xml)

    new_meta = ActMetadata(
        name="Human Services (Medicare) Act 1973",
        title_id="C2004A00100",
        comp_id="C2025C00609",
        comp_num="51",
        year=1974,
        number=41,
        effective_date=date(2025, 11, 1),
        aliases=["Health Insurance Commission Act 1973"],
    )
    corpus.save(new_meta, minimal_xml)

    index = json.loads((corpus.root / "index.json").read_text())
    assert "health-insurance-commission-act-1973" not in index["acts"]
    entry = index["acts"]["human-services-(medicare)-act-1973"]
    assert entry["name"] == "Human Services (Medicare) Act 1973"
    assert entry["aliases"] == ["Health Insurance Commission Act 1973"]
    assert not (corpus.root / "xml" / "health-insurance-commission-act-1973.xml").exists()


def test_save_merge_deletes_old_key_report_and_docx(corpus, minimal_xml):
    old_meta = ActMetadata(
        name="Health Insurance Commission Act 1973",
        title_id="C2004A00100",
        comp_id="C2025C00609",
        comp_num="51",
        year=1974,
        number=41,
        effective_date=date(2025, 11, 1),
    )
    corpus.save(old_meta, minimal_xml)

    reports_dir = corpus.root / "reports"
    docx_dir = corpus.root / "docx"
    reports_dir.mkdir(parents=True, exist_ok=True)
    docx_dir.mkdir(parents=True, exist_ok=True)
    old_report = reports_dir / "health-insurance-commission-act-1973-v0.5.0.json"
    old_docx = docx_dir / "health-insurance-commission-act-1973-c51-vol0.docx"
    old_report.write_text("{}")
    old_docx.write_bytes(b"")

    # A different, unrelated Act whose safe_name happens to share the old
    # key as a string prefix -- must survive the glob-based cleanup.
    unrelated_report = reports_dir / "health-insurance-commission-act-1973-amendment-v0.5.0.json"
    unrelated_docx = docx_dir / "health-insurance-commission-act-1973-amendment-c1-vol0.docx"
    unrelated_report.write_text("{}")
    unrelated_docx.write_bytes(b"")

    new_meta = ActMetadata(
        name="Human Services (Medicare) Act 1973",
        title_id="C2004A00100",
        comp_id="C2025C00609",
        comp_num="51",
        year=1974,
        number=41,
        effective_date=date(2025, 11, 1),
        aliases=["Health Insurance Commission Act 1973"],
    )
    corpus.save(new_meta, minimal_xml)

    assert not old_report.exists()
    assert not old_docx.exists()
    assert unrelated_report.exists()
    assert unrelated_docx.exists()


def test_save_merge_leaves_index_untouched_when_old_key_has_no_report_or_docx(corpus, minimal_xml):
    old_meta = ActMetadata(
        name="Health Insurance Commission Act 1973",
        title_id="C2004A00100",
        comp_id="C2025C00609",
        comp_num="51",
        year=1974,
        number=41,
        effective_date=date(2025, 11, 1),
    )
    corpus.save(old_meta, minimal_xml)  # no report/docx ever written for this key

    new_meta = ActMetadata(
        name="Human Services (Medicare) Act 1973",
        title_id="C2004A00100",
        comp_id="C2025C00609",
        comp_num="51",
        year=1974,
        number=41,
        effective_date=date(2025, 11, 1),
        aliases=["Health Insurance Commission Act 1973"],
    )
    corpus.save(new_meta, minimal_xml)  # must not raise

    index = json.loads((corpus.root / "index.json").read_text())
    assert "human-services-(medicare)-act-1973" in index["acts"]


def test_save_merge_deduplicates_aliases(corpus, minimal_xml):
    old_meta = ActMetadata(
        name="Old Name Act 1973", title_id="T1", comp_id="C1", comp_num="1",
        year=1973, number=1, effective_date=date(2025, 1, 1),
        aliases=["Even Older Name Act 1973"],
    )
    corpus.save(old_meta, minimal_xml)

    new_meta = ActMetadata(
        name="Current Name Act 1973", title_id="T1", comp_id="C1", comp_num="1",
        year=1973, number=1, effective_date=date(2025, 1, 1),
        aliases=["Old Name Act 1973"],
    )
    corpus.save(new_meta, minimal_xml)

    index = json.loads((corpus.root / "index.json").read_text())
    entry = index["acts"]["current-name-act-1973"]
    assert sorted(entry["aliases"]) == ["Even Older Name Act 1973", "Old Name Act 1973"]


def test_save_same_key_resave_unaffected(corpus, privacy_meta, minimal_xml):
    corpus.save(privacy_meta, minimal_xml)
    corpus.save(privacy_meta, minimal_xml)  # recompilation update, same safe_name
    index = json.loads((corpus.root / "index.json").read_text())
    assert len(index["acts"]) == 1
    assert "privacy-act-1988" in index["acts"]


def test_all_metadata_round_trips_aliases(corpus, privacy_meta, minimal_xml):
    meta_with_aliases = ActMetadata(
        name=privacy_meta.name, title_id=privacy_meta.title_id,
        comp_id=privacy_meta.comp_id, comp_num=privacy_meta.comp_num,
        year=privacy_meta.year, number=privacy_meta.number,
        effective_date=privacy_meta.effective_date,
        aliases=["Old Privacy Act Name 1988"],
    )
    corpus.save(meta_with_aliases, minimal_xml)
    metas = corpus.all_metadata()
    assert metas[0].aliases == ["Old Privacy Act Name 1988"]


def test_all_metadata_defaults_aliases_when_absent_from_index(corpus, privacy_meta, minimal_xml):
    corpus.save(privacy_meta, minimal_xml)
    # simulate a pre-existing index entry written before this field existed
    index = json.loads((corpus.root / "index.json").read_text())
    del index["acts"]["privacy-act-1988"]["aliases"]
    (corpus.root / "index.json").write_text(json.dumps(index))

    metas = corpus.all_metadata()
    assert metas[0].aliases == []
