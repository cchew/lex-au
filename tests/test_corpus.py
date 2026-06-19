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
