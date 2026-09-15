"""Corpus-level regression guard for the injected cross-reference reorder bug.

Task 5 rewrote ``reflinks._process_p`` so an injected ``<ref>`` is spliced at
its true document position instead of appended after every existing child of
the ``<p>``. The corpus fidelity audit (run 3, pre-fix) reported a ``reorder``
divergence for 1868 Acts driven by that bug; the canonical case is Corporations
Act 2001 s3(2), whose "section 2H of the" cross-reference was relocated to the
end of the paragraph ("... a law of the Commonwealth. section 2H of the").

For each guarded slug this test compares the source DOCX paragraph text against
the generated AKN paragraph text (``lexau.fidelity``) and fails if any
``reorder`` divergence (same tokens, different order) reappears. It is skipped
for any slug whose local corpus is absent -- ``corpus/`` is gitignored and not
present on CI -- so it guards local re-conversions and full-corpus runs, not a
hard CI gate.

The comparison here is the raw ``lexau.fidelity`` one, not the audit script's
marker-stripped pipeline: stripping leading "(a)"/"(b)" enumerators makes
difflib mis-align list-item paragraph spans and label a handful of them
``reorder`` for reasons unrelated to ``_process_p``. The raw comparison
isolates the injected-reference bug this test exists to catch.
"""
from __future__ import annotations

import importlib.util
import json
from dataclasses import replace as _dc_replace
from datetime import date
from pathlib import Path

import pytest
from docx import Document
from lxml import etree

from lexau.builder import AknBuilder
from lexau.docx_reader import iter_paragraphs
from lexau.fidelity import akn_paragraphs, compare, docx_paragraphs
from lexau.models import ActMetadata
from lexau.parser import ElementType

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "audit_conversion_fidelity",
    _REPO_ROOT / "scripts" / "audit_conversion_fidelity.py",
)
audit = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(audit)

CORPUS = _REPO_ROOT / "corpus"

# corporations-act-2001 is the canonical reproduction (s3(2) "section 2H of
# the"). The rest are the worst reorder offenders from run 3's SUMMARY whose
# reorder count dropped to 0 after re-conversion with the fixed _process_p.
GUARDED = [
    "corporations-act-2001",
    "income-tax-assessment-act-1997",
    "income-tax-assessment-act-1936",
    "taxation-administration-act-1953",
    "social-security-act-1991",
    "migration-regulations-1994",
    "corporations-regulations-2001",
    "civil-aviation-safety-regulations-1998",
    "family-law-(superannuation)-regulations-2025",
    "customs-tariff-act-1995",
    "customs-tariff-amendment-(thailand-australia-free-trade-agreement-implementation)-act-2004",
]


def _index_entry(slug: str) -> dict | None:
    index_path = CORPUS / "index.json"
    if not index_path.exists():
        return None
    index = json.loads(index_path.read_text())
    acts = index["acts"] if isinstance(index, dict) and "acts" in index else index
    return acts.get(slug)


@pytest.mark.parametrize("slug", GUARDED)
def test_guarded_act_has_no_cross_reference_reorder(slug: str) -> None:
    xml_path = CORPUS / "xml" / f"{slug}.xml"
    if not xml_path.exists():
        pytest.skip(f"{slug}: no local corpus XML")

    entry = _index_entry(slug)
    if entry is None:
        pytest.skip(f"{slug}: no index.json entry")

    docx_paths, _mode = audit._docx_paths(CORPUS, slug, entry)
    if not docx_paths:
        pytest.skip(f"{slug}: no local docx volumes")

    root = etree.parse(str(xml_path)).getroot()
    divs = compare(docx_paragraphs(docx_paths), akn_paragraphs(root))
    reorders = [d for d in divs if d.kind == "reorder"]

    assert not reorders, (
        f"{slug}: {len(reorders)} reorder divergence(s) reappeared; "
        f"first: {reorders[0].akn_text[:200]!r}"
    )


# ---------------------------------------------------------------------------
# Task 8 (2026-09-08, wfw v0.3.1 phase 2-4): wp_garble / wp_word_drop fixes
# ---------------------------------------------------------------------------
#
# The GUARDED test above re-reads an already-persisted corpus/xml/*.xml
# snapshot -- correct for guarding a bug that was fixed by a prior full-corpus
# re-conversion, but Task 8's three fixes have not yet been baked into a
# fresh corpus-wide re-conversion (that's Task 18's job), so the local
# corpus/xml/*.xml files still reflect the PRE-fix converter and reading them
# here would pin the bug, not the fix. Instead, each test below builds a
# fresh AKN root from the real corpus DOCX using the actual converter
# pipeline (docx_reader.iter_paragraphs -> AknBuilder), exactly mirroring
# cli.py's `build` command's per-Act loop -- so these pins are self-verifying
# against whatever code is currently checked out, not a snapshot that can go
# stale, and reuse the same audit.akn_paragraphs()/audit._docx_paths() this
# file already depends on.

_DUMMY_META = ActMetadata(
    name="dummy", title_id="X", comp_id="X", comp_num="1",
    year=1900, number=1, effective_date=date(1900, 1, 1),
)


def _make_builder(slug: str) -> AknBuilder | None:
    """Load slug's real corpus DOCX volume(s) into a fresh AknBuilder via the
    actual converter pipeline (docx_reader.iter_paragraphs), exactly
    mirroring cli.py's `build` command's per-Act loop -- except FIGURE
    paragraphs are dropped before `.add()`. None of these text-fidelity pins
    touch figures, and `.build()` unconditionally calls `materialise_figures`
    (builder.py ~line 1625) for any Act with resolvable image blobs, which
    shells out to `soffice` for EMF/WMF conversion; some exemplar Acts here
    carry dozens of embedded images (e.g. the GST Act's ~86 `a:blip`
    references across its two volumes) and `soffice` is slow/flaky in this
    sandbox (see the 2 pre-existing, unrelated test_figures.py failures) --
    keeping figures in the stream made a full build of that Act hang well
    past a two-minute timeout. Skipping them keeps these tests fast and
    focused on the text path Task 8 actually touches. Returns None if the
    local corpus lacks this Act (caller should skip).
    """
    entry = _index_entry(slug)
    if entry is None:
        return None
    docx_paths, _mode = audit._docx_paths(CORPUS, slug, entry)
    if not docx_paths:
        return None

    builder = AknBuilder(_DUMMY_META)
    for vol_idx, docx_path in enumerate(docx_paths):
        doc = Document(str(docx_path))
        for p in iter_paragraphs(doc):
            if p.element_type == ElementType.FIGURE:
                continue
            builder.add(_dc_replace(p, volume_index=vol_idx))
    return builder


def _build_structural_root(slug: str) -> etree._Element | None:
    """Structural-only AKN root (plain `.build()`, no injection passes).

    Correct and much cheaper for exemplars that don't touch definition/ref/
    quantity/date injection: Fix items 1 (smart-tag preservation) and 3
    (run-split) both operate at or below the docx_reader/`_emit_p_inline`
    layer, entirely upstream of `build_with_report()`'s injection passes.
    """
    builder = _make_builder(slug)
    if builder is None:
        return None
    xml, _ = builder.build()
    return xml


def _build_full_root(slug: str) -> etree._Element | None:
    """Full AKN root, injection passes included (`build_with_report()`).

    Required for Fix item 2 (relational-definition qualifying clause):
    `inject_terms` -- which the fix touches -- is NOT run by plain
    `.build()` (confirmed by reading builder.py: `build_with_report()` calls
    `self.build()` at its own line 1730 to get `root`, then injects terms/
    refs/quantities/dates on top of it). `build_with_report({})` (empty
    corpus_index -- no cross-Act ref resolution needed here) is what cli.py's
    real per-Act loop calls too, so this mirrors production exactly.
    """
    builder = _make_builder(slug)
    if builder is None:
        return None
    xml, _ = builder.build_with_report({})
    return xml


def test_smart_tag_national_land_recovered():
    """Fix item 1 (smart-tag run-text preservation), exemplar 1: the
    "National Land" definiendum in australian-capital-territory-(planning-
    and-land-management)-act-1988 is wrapped in nested
    <w:smartTag element="place"><w:smartTag element="PlaceName">/"PlaceType">
    and previously vanished entirely, converting to just "has the meaning
    given by section 27." with no defined term at all.
    """
    slug = "australian-capital-territory-(planning-and-land-management)-act-1988"
    root = _build_structural_root(slug)
    if root is None:
        pytest.skip(f"{slug}: no local corpus")
    paras = audit.akn_paragraphs(root)
    assert any("National Land has the meaning given by" in p for p in paras), (
        "'National Land' definiendum missing from converted output"
    )


def test_smart_tag_australia_table_cell_recovered():
    """Fix item 1, exemplar 2 (table-cell path, not just paragraph spans):
    comprehensive-nuclear-test-ban-treaty-act-1998's schedule table cell
    "The day on which the Treaty enters into force for Australia" --
    "Australia" wrapped in <w:smartTag element="country-region">
    <w:smartTag element="place"> -- previously dropped entirely by the
    table-cell text path, leaving "...enters into force for ." with a
    dangling preposition.
    """
    slug = "comprehensive-nuclear-test-ban-treaty-act-1998"
    root = _build_structural_root(slug)
    if root is None:
        pytest.skip(f"{slug}: no local corpus")
    paras = audit.akn_paragraphs(root)
    assert any("enters into force for Australia" in p for p in paras), (
        "'Australia' dropped from schedule table cell"
    )


def test_smart_tag_garble_1_11_recovered():
    """Fix item 1, exemplar 3 (garble, not clean drop): a-new-tax-system-
    (goods-and-services-tax)-act-1999's "is 1/11" -- the smart-tag boundary
    falls mid-token (<w:smartTag element="PersonName"> wraps "s " + a raised
    "1"), so the drop previously merged the surviving fragments into "i/11"
    instead of leaving a clean gap.
    """
    slug = "a-new-tax-system-(goods-and-services-tax)-act-1999"
    root = _build_structural_root(slug)
    if root is None:
        pytest.skip(f"{slug}: no local corpus")
    paras = audit.akn_paragraphs(root)
    assert any("is 1/11 of" in p for p in paras), (
        "'is 1/11' garbled (e.g. to 'i/11') by a dropped smart-tag run"
    )
    assert not any("i/11" in p for p in paras)


def test_run_split_excise_title_recovered():
    """Fix item 3 (spurious mid-token run-split, Group C): excise-tariff-
    amendment-act-1990's long title splits "Excise Tariff Amendment Act
    1990" across two adjacent bold <w:r> runs (separated only by an
    intervening <w:bookmarkStart>/<w:bookmarkEnd>, no real whitespace in the
    source). Comparison goes through the SAME pretty-print round trip
    src/lexau/corpus.py:77 uses for persisted output -- the bug only
    manifests once lxml's pretty-print serializer fills an unset tail
    between the two sibling <b> elements with indentation whitespace.
    """
    slug = "excise-tariff-amendment-act-1990"
    root = _build_structural_root(slug)
    if root is None:
        pytest.skip(f"{slug}: no local corpus")
    pretty = etree.tostring(root, pretty_print=True)
    reparsed = etree.fromstring(pretty)
    paras = audit.akn_paragraphs(reparsed)
    assert any("Excise Tariff Amendment Act 1990" in p for p in paras), (
        "title split into 'E' + 'xcise...' by a pretty-print-filled tail"
    )
    assert not any("E xcise" in p for p in paras)


def test_relational_definition_clause_recovered():
    """Fix item 2 (relational-definition qualifying-clause preservation,
    wp_word_drop Bug 2): royal-australian-air-force-veterans'-residences-
    act-1953's "surviving spouse or de facto partner, in relation to a
    deceased person, means a person who..." previously converted to
    "<term>surviving spouse or de facto partner</term> means a person
    who...", silently dropping the ", in relation to a deceased person,"
    qualifying clause and turning a context-qualified definition into an
    unconditional one.
    """
    slug = "royal-australian-air-force-veterans'-residences-act-1953"
    root = _build_full_root(slug)
    if root is None:
        pytest.skip(f"{slug}: no local corpus")
    paras = audit.akn_paragraphs(root)
    assert any(
        "surviving spouse or de facto partner, in relation to a deceased "
        "person, means a person who" in p
        for p in paras
    ), "', in relation to a deceased person,' qualifying clause missing"
