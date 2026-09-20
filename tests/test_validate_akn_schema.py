import json
from pathlib import Path
import sys
import textwrap
from scripts.validate_akn_schema import validate_one, _signature, gate

# Derive the XSD path from sys.prefix (same as the script's _COBALT_XSD) rather
# than a CWD-relative literal, so the test passes regardless of pytest's cwd.
_XSD = (
    Path(sys.prefix)
    / "lib"
    / f"python3.{sys.version_info.minor}"
    / "site-packages"
    / "cobalt"
    / "xsd"
    / "akomantoso30.xsd"
)

_VALID = textwrap.dedent('''\
<akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">
  <act name="act"><meta><identification source="#x">
    <FRBRWork><FRBRthis value="/akn/au/act/2020/1/main"/><FRBRuri value="/akn/au/act/2020/1"/>
      <FRBRdate date="2020-01-01" name="Generation"/><FRBRauthor href="#x"/><FRBRcountry value="au"/></FRBRWork>
    <FRBRExpression><FRBRthis value="/akn/au/act/2020/1/eng@/main"/><FRBRuri value="/akn/au/act/2020/1/eng@"/>
      <FRBRdate date="2020-01-01" name="Generation"/><FRBRauthor href="#x"/><FRBRlanguage language="eng"/></FRBRExpression>
    <FRBRManifestation><FRBRthis value="/akn/au/act/2020/1/eng@/main.xml"/><FRBRuri value="/akn/au/act/2020/1/eng@.xml"/>
      <FRBRdate date="2020-01-01" name="Generation"/><FRBRauthor href="#x"/></FRBRManifestation>
  </identification></meta><body><section eId="sec_1"><content><p>Text.</p></content></section></body></act>
</akomaNtoso>
''')

_INVALID = '<akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0"><act><bogus/></act></akomaNtoso>'

def test_validate_one_accepts_valid(tmp_path):
    f = tmp_path / "ok.xml"; f.write_text(_VALID)
    ok, errors = validate_one(f, _XSD)
    assert ok is True and errors == []

def test_validate_one_rejects_invalid(tmp_path):
    f = tmp_path / "bad.xml"; f.write_text(_INVALID)
    ok, errors = validate_one(f, _XSD)
    assert ok is False and errors


_NS = "{http://docs.oasis-open.org/legaldocml/ns/akn/3.0}"


def test_signature_distinguishes_structurally_different_errors():
    """Four violations that the namespace-URI collapse buckets into two must key apart."""
    subsec = (
        f"248:SCHEMAV_ELEMENT_CONTENT: Element '{_NS}subsection': This element is not "
        f"expected. Expected is one of ( {_NS}intro, {_NS}content, {_NS}hcontainer )."
    )
    empty_body = (
        f"78:SCHEMAV_ELEMENT_CONTENT: Element '{_NS}body': Missing child element(s). "
        f"Expected is one of ( {_NS}hcontainer, {_NS}componentRef, {_NS}clause )."
    )
    dup_eid = (
        f"28566:SCHEMAV_CVC_IDC: Element '{_NS}chapter': Duplicate key-sequence "
        f"['chapter-4'] in unique identity-constraint '{_NS}eId-act'."
    )
    no_precomp = (
        f"117:SCHEMAV_CVC_IDC: Element '{_NS}part', attribute 'eId': Warning: No "
        f"precomputed value available, the value was either invalid or something strange happened."
    )
    sigs = {_signature(s) for s in (subsec, empty_body, dup_eid, no_precomp)}
    assert len(sigs) == 4, sigs
    for s in sigs:
        assert "{" not in s, f"namespace not stripped from bucket key: {s}"
    assert any("subsection" in s for s in sigs)
    assert any("body" in s for s in sigs)
    # Minor #1: duplicate-eId and "no precomputed value" must not share a bucket.
    assert _signature(dup_eid) != _signature(no_precomp)


# gate() -- strict-with-whitelist. _INVALID (above) reliably produces exactly
# two violation signatures against the real strict XSD:
#   "SCHEMAV_CVC_COMPLEX_TYPE_4 | act | required-attr:name"   (count 1)
#   "SCHEMAV_ELEMENT_CONTENT | bogus | not-expected"            (count 1)
# Tests build a small whitelist fixture (not the real docs/xsd-whitelist.json)
# so ceilings are controlled and the test doesn't depend on corpus content.

_SIG_ACT_NAME = "SCHEMAV_CVC_COMPLEX_TYPE_4 | act | required-attr:name"
_SIG_BOGUS = "SCHEMAV_ELEMENT_CONTENT | bogus | not-expected"


def _write_whitelist(path: Path, entries: dict) -> Path:
    path.write_text(json.dumps({"entries": entries}))
    return path


def test_gate_passes_when_all_signatures_whitelisted(tmp_path):
    xml_dir = tmp_path / "xml"; xml_dir.mkdir()
    (xml_dir / "bad.xml").write_text(_INVALID)
    whitelist = _write_whitelist(tmp_path / "whitelist.json", {
        _SIG_ACT_NAME: {"family": "X", "max_entries": 1, "reason": "test"},
        _SIG_BOGUS: {"family": "X", "max_entries": 1, "reason": "test"},
    })
    ok, failing = gate(xml_dir, _XSD, whitelist)
    assert ok is True
    assert failing == []


def test_gate_fails_on_non_whitelisted_signature(tmp_path):
    xml_dir = tmp_path / "xml"; xml_dir.mkdir()
    (xml_dir / "bad.xml").write_text(_INVALID)
    whitelist = _write_whitelist(tmp_path / "whitelist.json", {
        _SIG_ACT_NAME: {"family": "X", "max_entries": 1, "reason": "test"},
        # _SIG_BOGUS deliberately omitted.
    })
    ok, failing = gate(xml_dir, _XSD, whitelist)
    assert ok is False
    assert failing == [_SIG_BOGUS]


def test_gate_fails_when_whitelisted_signature_exceeds_ceiling(tmp_path):
    xml_dir = tmp_path / "xml"; xml_dir.mkdir()
    (xml_dir / "bad.xml").write_text(_INVALID)
    whitelist = _write_whitelist(tmp_path / "whitelist.json", {
        _SIG_ACT_NAME: {"family": "X", "max_entries": 0, "reason": "test"},  # ceiling below actual count of 1
        _SIG_BOGUS: {"family": "X", "max_entries": 1, "reason": "test"},
    })
    ok, failing = gate(xml_dir, _XSD, whitelist)
    assert ok is False
    assert failing == [_SIG_ACT_NAME]
