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
from pathlib import Path

import pytest
from lxml import etree

from lexau.fidelity import akn_paragraphs, compare, docx_paragraphs

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
