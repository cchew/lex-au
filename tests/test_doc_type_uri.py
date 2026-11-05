from datetime import date

from lexau.models import ActMetadata, doc_type_for


def _meta(**kw) -> ActMetadata:
    base = dict(name="X", title_id="C1", comp_id="c", comp_num="1", year=1994, number=57,
                effective_date=date(2026, 1, 1))
    base.update(kw)
    return ActMetadata(**base)


def test_doc_type_for():
    assert doc_type_for("F1996B00580", "Superannuation Industry (Supervision) Regulations 1994") == "regulation"
    assert doc_type_for("F2015L00000", "Foreign Acquisitions and Takeovers Regulation 2015") == "regulation"
    assert doc_type_for("F2020L00001", "Aged Care Rules 2020") == "instrument"
    assert doc_type_for("C2004A03712", "Privacy Act 1988") == "act"
    assert doc_type_for("C2004A00001", "Something Regulations Act 2000") == "act"


def test_regulation_work_uri_uses_title_id():
    m = _meta(name="Superannuation Industry (Supervision) Regulations 1994",
              title_id="F1996B00580", doc_type="regulation")
    assert m.frbr_work_uri == "/akn/au/regulation/1994/F1996B00580"
    assert m.frbr_expression_uri.startswith("/akn/au/regulation/1994/F1996B00580/eng@")


def test_act_work_uri_unchanged():
    m = _meta(year=1988, number=119)
    assert m.frbr_work_uri == "/akn/au/act/1988/119"


def test_locality_instrument_uri_unchanged():
    m = _meta(doc_type="instrument", locality="vic", title_id="F2020L00001")
    assert m.frbr_work_uri.endswith("/1994/57")


# --- persistence (Task 2) ---------------------------------------------------

import importlib.util
import json
from pathlib import Path

from lxml import etree

from lexau.corpus import Corpus

_AKN = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"


def _xml():
    return etree.fromstring(f'<akomaNtoso xmlns="{_AKN}"><act name="act"><body/></act></akomaNtoso>')


def test_save_writes_doc_type_only_when_not_act(tmp_path):
    corpus = Corpus(tmp_path)
    corpus.save(_meta(name="Privacy Act 1988", title_id="C2004A03712"), _xml())
    corpus.save(_meta(name="SIS Regulations 1994", title_id="F1996B00580", doc_type="regulation"), _xml())
    acts = json.loads((tmp_path / "index.json").read_text())["acts"]
    assert "doc_type" not in acts["privacy-act-1988"]
    assert acts["sis-regulations-1994"]["doc_type"] == "regulation"


def test_all_metadata_derives_doc_type_when_missing(tmp_path):
    corpus = Corpus(tmp_path)
    corpus.save(_meta(name="Privacy Act 1988", title_id="C2004A03712"), _xml())
    corpus.save(_meta(name="SIS Regulations 1994", title_id="F1996B00580", doc_type="regulation"), _xml())
    index = json.loads((tmp_path / "index.json").read_text())
    for entry in index["acts"].values():
        entry.pop("doc_type", None)  # an index written before doc_type was persisted
    (tmp_path / "index.json").write_text(json.dumps(index))
    by_name = {m.name: m.doc_type for m in Corpus(tmp_path).all_metadata()}
    assert by_name == {"Privacy Act 1988": "act", "SIS Regulations 1994": "regulation"}


def test_meta_from_entry_derives_doc_type():
    spec = importlib.util.spec_from_file_location(
        "rebuild_offline", Path(__file__).parent.parent / "scripts" / "rebuild_offline.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    entry = dict(name="SIS Regulations 1994", title_id="F1996B00580", comp_id="c", comp_num="1",
                 year=1994, number=57, effective_date="2026-01-01")
    assert mod.meta_from_entry(entry).doc_type == "regulation"
    assert mod.meta_from_entry(dict(entry, title_id="C1", name="Privacy Act 1988")).doc_type == "act"


# --- XML (Task 4) -----------------------------------------------------------

_NS = {"a": _AKN}


def _built(meta):
    from lexau.builder import AknBuilder
    return AknBuilder(meta).build_with_report({})[0]


def test_regulation_xml_carries_uri_subtype_and_number():
    m = _meta(name="SIS Regulations 1994", title_id="F1996B00580", doc_type="regulation")
    xml = _built(m)
    work = xml.xpath("//a:FRBRWork", namespaces=_NS)[0]
    assert work.xpath("a:FRBRuri/@value", namespaces=_NS) == ["/akn/au/regulation/1994/F1996B00580"]
    assert work.xpath("a:FRBRsubtype/@value", namespaces=_NS) == ["regulation"]
    assert work.xpath("a:FRBRnumber/@value", namespaces=_NS) == ["57"]
    assert not work.xpath("a:FRBRalias", namespaces=_NS)


def test_act_xml_subtype_stays_act():
    xml = _built(_meta(name="Privacy Act 1988", title_id="C2004A03712", year=1988, number=119))
    assert xml.xpath("//a:FRBRWork/a:FRBRsubtype/@value", namespaces=_NS) == ["act"]
    assert xml.xpath("//a:FRBRWork/a:FRBRuri/@value", namespaces=_NS) == ["/akn/au/act/1988/119"]
