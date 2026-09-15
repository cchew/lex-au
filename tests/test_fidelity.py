from __future__ import annotations

from pathlib import Path

from docx import Document
from lxml import etree

from lexau.fidelity import akn_paragraphs, compare, docx_paragraphs, normalise

FIXTURE_DOCX = (
    Path(__file__).parent
    / "fixtures"
    / "docx"
    / "loan-act-(no.-2)-1976-vol0.docx"
)


# --- Brief tests (verbatim) -------------------------------------------------


def test_normalise_collapses_whitespace():
    assert normalise("  a\t b\n c ") == "a b c"


def test_compare_flags_reorder_same_tokens_different_order():
    docx = ["Despite section 2H of the Acts Interpretation Act 1901, this Act is a law."]
    akn = ["Despite Acts Interpretation Act 1901, this Act is a law. section 2H of the"]
    divs = compare(docx, akn)
    assert len(divs) == 1
    assert divs[0].kind == "reorder"


def test_compare_flags_dropped_text():
    docx = ["An asset is property or a right of any kind and includes a chose in action."]
    akn = ["An asset is property or a right of any kind."]
    divs = compare(docx, akn)
    assert divs[0].kind == "drop_text"


def test_compare_flags_dropped_paragraph():
    docx = ["Para one.", "Para two.", "Para three."]
    akn = ["Para one.", "Para three."]
    divs = compare(docx, akn)
    assert any(d.kind == "drop_para" and "two" in d.docx_text for d in divs)


def test_compare_clean_conversion_has_no_divergences():
    paras = ["Section 1.", "Section 2 refers to section 1.", "Section 3."]
    assert compare(paras, list(paras)) == []


def test_compare_minor_divergence_below_reorder_threshold():
    docx = ["The Minister may, by legislative instrument, determine a matter."]
    akn = ["The Minister may by legislative instrument determine a matter"]
    divs = compare(docx, akn)
    assert divs and divs[0].kind == "minor"


# --- Added: total-rewrite paragraphs must not hide in "minor" -------------


def test_compare_total_rewrite_is_not_minor():
    divs = compare(["alpha beta gamma delta"], ["zulu yankee xray whiskey"])
    assert divs
    assert divs[0].kind != "minor"
    assert divs[0].kind == "drop_text"


# --- Added: regression pin for the concern-1 guard ----------------------


def test_compare_identical_token_sequence_stays_minor_not_reorder():
    # A `replace` opcode whose two sides share an identical lowercased \w+ token
    # sequence differs only in punctuation/whitespace. Nothing was reordered, so
    # it must be "minor", never "reorder". Pins the concern-1 guard against a
    # future refactor silently reverting to the brief's same-multiset rule.
    docx = ["Payment of the levy, and any penalty, is due; on 30 June."]
    akn = ["Payment of the levy and any penalty is due on 30 June"]
    divs = compare(docx, akn)
    assert len(divs) == 1
    assert divs[0].kind == "minor"


# --- Added: near-identical replace with a stray token is minor, not reorder ---


def test_compare_stray_enumerator_token_is_minor_not_reorder():
    # One extra enumerator token ("2") against an otherwise near-identical line.
    # The multisets differ and nothing is transposed, so this must be "minor".
    # The old "overlap >= 0.98 => reorder" fallback mislabelled every case of
    # this shape as "reorder" (the entire corpus-wide residual).
    docx = [
        "The applicant must give the Secretary the information mentioned in "
        "subsection (1) within 14 days after the notice is given to the applicant."
    ]
    akn = [
        "2 The applicant must give the Secretary the information mentioned in "
        "subsection (1) within 14 days after the notice is given to the applicant."
    ]
    divs = compare(docx, akn)
    assert len(divs) == 1
    assert divs[0].kind == "minor"


def test_compare_genuine_transposition_still_reorder():
    # Exact same token multiset, different order => still "reorder".
    docx = ["alpha beta gamma delta epsilon zeta eta theta"]
    akn = ["theta eta zeta epsilon delta gamma beta alpha"]
    divs = compare(docx, akn)
    assert len(divs) == 1
    assert divs[0].kind == "reorder"


# --- Added: akn_paragraphs excludes <meta> content ------------------------


def test_akn_paragraphs_excludes_meta_content():
    xml = (
        '<akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">'
        "<act>"
        "<meta><identification><FRBRWork>"
        "<p>meta paragraph must be excluded</p>"
        "</FRBRWork></identification>"
        "<heading>meta heading must be excluded</heading></meta>"
        "<body>"
        "<heading>Part 1  Preliminary</heading>"
        "<p>The first   operative paragraph.</p>"
        "<section><p>A nested operative paragraph.</p></section>"
        "</body>"
        "</act></akomaNtoso>"
    )
    root = etree.fromstring(xml.encode("utf-8"))
    assert akn_paragraphs(root) == [
        "Part 1 Preliminary",
        "The first operative paragraph.",
        "A nested operative paragraph.",
    ]


# --- Added: docx_paragraphs order preservation --------------------------


def test_docx_paragraphs_preserves_order_across_files(tmp_path):
    first = tmp_path / "first.docx"
    second = tmp_path / "second.docx"

    d1 = Document()
    for line in ["Alpha first para.", "Beta second para.", "   "]:
        d1.add_paragraph(line)
    d1.save(str(first))

    d2 = Document()
    for line in ["Gamma third para.", "Delta fourth para."]:
        d2.add_paragraph(line)
    d2.save(str(second))

    assert docx_paragraphs([first, second]) == [
        "Alpha first para.",
        "Beta second para.",
        "Gamma third para.",
        "Delta fourth para.",
    ]


def test_docx_paragraphs_keeps_non_breaking_hyphen(tmp_path):
    # Federal Register compilation DOCX encodes compound-word hyphens as
    # <w:noBreakHyphen/>, which carries no <w:t> text. Without explicit
    # handling "non-operative" collapses to "nonoperative" and every
    # hyphenated compound reads as a divergence against the AKN text.
    import zipfile

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    document_xml = (
        f'<w:document xmlns:w="{W}"><w:body>'
        f"<w:p><w:r><w:t>non</w:t></w:r>"
        f"<w:r><w:noBreakHyphen/></w:r>"
        f"<w:r><w:t>operative material</w:t></w:r></w:p>"
        f"</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" ContentType="application/'
        'vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        "</Types>"
    )
    rels = (
        '<?xml version="1.0"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/'
        'officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
        "</Relationships>"
    )
    path = tmp_path / "nbh.docx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document_xml)

    assert docx_paragraphs([path]) == ["non-operative material"]


def test_docx_paragraphs_reads_real_fixture_in_document_order():
    paras = docx_paragraphs([FIXTURE_DOCX])
    assert paras[0] == "LOAN ACT (No. 2) 1976"
    assert "Short title." in paras
    # tab between the section number and the body text is emitted as a space
    assert paras.index(
        "1. This Act may be cited as the Loan Act (No. 2) 1976."
    ) == paras.index("Short title.") + 1
    assert all(p == normalise(p) for p in paras)


# --- P6: within-paragraph audit mode -------------------------------------

from lexau.fidelity import within_para_classify, WithinParaResult, compare, Divergence


def _wp(d, a):
    return within_para_classify(d, a)


def test_wp_clean_identical():
    r = _wp("the quick brown fox jumps far", "the quick brown fox jumps far")
    assert r.kind == "wp_clean" and r.dropped == [] and r.inserted == []


def test_wp_punct_only():
    r = _wp("the quick, brown fox; jumps far", "the quick brown fox jumps far")
    assert r.kind == "wp_punct" and r.dropped == [] and r.inserted == []


def test_wp_word_drop():
    r = _wp("the quick brown fox jumps far", "the quick fox jumps far")
    assert r.kind == "wp_word_drop" and r.dropped == ["brown"] and r.inserted == []


def test_wp_word_insert():
    r = _wp("the quick fox jumps far", "the quick brown fox jumps far")
    assert r.kind == "wp_word_insert" and r.inserted == ["brown"] and r.dropped == []


def test_wp_word_reorder():
    r = _wp("the brown quick fox jumps far", "the quick brown fox jumps far")
    assert r.kind == "wp_word_reorder" and r.dropped == [] and r.inserted == []


def test_wp_garble_substitution():
    r = _wp("the quick brown fox jumps far", "the quick brown dog runs far")
    assert r.kind == "wp_garble"
    assert r.dropped == ["fox", "jumps"] and r.inserted == ["dog", "runs"]


def test_wp_skipped_below_min_tokens():
    r = _wp("a b c", "a b d")
    assert r.kind == "wp_skipped"
    assert r.kind != "wp_clean" and r.kind != "wp_garble"


def test_wp_casefold_matches_outer_tokeniser():
    r = _wp("The Minister may act here", "the minister may act here")
    assert r.kind == "wp_clean"


def test_compare_k1_substitution_attaches_within_para():
    docx = ["alpha", "the quick brown fox must jump over the lazy sleeping dog today", "omega"]
    akn  = ["alpha", "the quick brown fox may jump over the lazy sleeping dog today", "omega"]
    divs = compare(docx, akn)
    d = next(x for x in divs if x.within_para)
    assert d.kind == "minor"
    assert len(d.within_para) == 1
    assert d.within_para[0].kind == "wp_garble"
    assert "must" in d.within_para[0].dropped and "may" in d.within_para[0].inserted


def test_compare_k3_equal_length_replace_block():
    docx = ["p one alpha beta gamma", "p two delta epsilon zeta", "p three eta theta iota"]
    akn  = ["p one alpha beta gamma X", "p two delta epsilon ZETA", "p three eta theta MISSING"]
    divs = compare(docx, akn)
    assert len(divs) == 1
    d = next(x for x in divs if x.within_para)
    assert len(d.within_para) == 3


# --- Task 9: unequal-length replace blocks now classify within_para ------
#
# Phase 1 (test_compare_unequal_replace_block_has_no_within_para) pinned
# within_para == [] for every unequal-length replace block. That is now
# intentionally superseded: compare() best-match aligns the two sides within
# the block and classifies each aligned pair, reporting any paragraph left
# over on the longer side as wp_word_drop / wp_word_insert.


def test_compare_unequal_replace_block_now_classifies_within_para():
    # Same fixture Phase 1 used to pin the *absence* of within_para; now pins
    # its presence. Not re-asserting specific per-pair kinds here (see the two
    # more tightly-controlled scenarios below for that) -- this is the direct
    # regression update the brief calls for.
    docx = ["keep", "aaa bbb ccc ddd", "eee fff ggg hhh"]
    akn = ["keep", "aaa bbb ccc ddd eee", "fff ggg", "hhh iii jjj"]
    divs = compare(docx, akn)
    replace_divs = [
        d
        for d in divs
        if (d.docx_span[1] - d.docx_span[0]) != (d.akn_span[1] - d.akn_span[0])
    ]
    assert replace_divs, "fixture must still produce an unequal-length block"
    for d in replace_divs:
        assert d.within_para != []


def test_compare_delete_and_insert_opcodes_still_have_no_within_para():
    # Fresh guard (brief-required): only `replace` opcodes ever populate
    # within_para. delete/insert opcodes must not regress.
    docx = ["Para one.", "Para two.", "Para three."]
    akn = ["Para one.", "Para three.", "Completely new paragraph appended."]
    divs = compare(docx, akn)
    kinds = {d.kind for d in divs}
    assert "drop_para" in kinds
    assert "spurious_para" in kinds
    for d in divs:
        if d.kind in ("drop_para", "spurious_para"):
            assert d.within_para == []


def test_compare_unequal_block_classifies_matched_pairs_and_flags_insertion():
    # 3 DOCX paragraphs vs 4 AKN paragraphs: the real edit is one wholly new
    # inserted AKN paragraph. The other three differ from their DOCX
    # counterpart only by punctuation, so they must classify wp_punct (their
    # \w-token sequences are identical once punctuation is stripped, but the
    # raw token streams differ -- see within_para_classify), never wp_clean.
    docx = [
        "alpha bravo charlie delta first paragraph text",
        "echo foxtrot golf hotel second paragraph text",
        "india juliet kilo lima third paragraph text",
    ]
    akn = [
        "alpha, bravo, charlie, delta, first paragraph text.",
        "echo, foxtrot, golf, hotel, second paragraph text.",
        "india, juliet, kilo, lima, third paragraph text.",
        "mike november oscar papa completely new inserted sentence",
    ]
    divs = compare(docx, akn)
    assert len(divs) == 1
    d = divs[0]
    assert d.docx_span == (0, 3)
    assert d.akn_span == (0, 4)
    assert d.within_para != []
    assert len(d.within_para) == 4

    inserted = [w for w in d.within_para if w.kind == "wp_word_insert"]
    assert len(inserted) == 1
    assert inserted[0].dropped == []
    assert inserted[0].inserted == [
        "mike",
        "november",
        "oscar",
        "papa",
        "completely",
        "new",
        "inserted",
        "sentence",
    ]

    matched = [w for w in d.within_para if w.kind != "wp_word_insert"]
    assert len(matched) == 3
    assert all(w.kind in ("wp_clean", "wp_punct") for w in matched)


def test_compare_unequal_block_wholesale_rewrite_forces_garble_pairs():
    # Genuine wholesale rewrite: 2 DOCX paragraphs vs 3 AKN paragraphs, no
    # shared vocabulary anywhere. Best-match alignment still forces
    # min(2, 3) = 2 pairs (there is no "good" match, but the pairing is not
    # abandoned) -- read within_para_classify: two same-length-ish paragraphs
    # sharing zero \w tokens fail both the drop-subset and insert-subset
    # checks, so they land in its terminal case, wp_garble. The one paragraph
    # left over on the longer (AKN) side reports wp_word_insert.
    docx = [
        "quantum flux reactor stabilizes rapidly today",
        "silent violin echoes through empty concert hall",
    ]
    akn = [
        "purple elephant dances gracefully near river",
        "wooden chair creaks under heavy morning frost",
        "golden sunrise paints the distant mountain peaks",
    ]
    divs = compare(docx, akn)
    assert len(divs) == 1
    d = divs[0]
    assert d.within_para != []
    assert len(d.within_para) == 3
    garbled = [w for w in d.within_para if w.kind == "wp_garble"]
    assert len(garbled) == 2
    inserted = [w for w in d.within_para if w.kind == "wp_word_insert"]
    assert len(inserted) == 1


def test_compare_unequal_block_above_cap_falls_back_to_wp_block_skipped():
    # A block above _WP_ALIGN_MAX_PARAS (40) on either side must skip
    # pairwise best-match alignment (O(min(n,m)*n*m) is fine at the cap but
    # not unbounded) and fall back to one whole-block classification, tagged
    # wp_block_skipped so it reads distinctly from wp_skipped (too-few-tokens)
    # in aggregation. Real (not mocked) run through compare() at 41 vs 42
    # paragraphs, none of which string-match across sides.
    docx = [f"docx paragraph number {i} has some unique filler words" for i in range(41)]
    akn = [f"akn paragraph number {i} has some unique filler words!" for i in range(42)]
    divs = compare(docx, akn)
    assert len(divs) == 1
    d = divs[0]
    assert d.docx_span == (0, 41)
    assert d.akn_span == (0, 42)
    assert len(d.within_para) == 1
    assert d.within_para[0].kind == "wp_block_skipped"
