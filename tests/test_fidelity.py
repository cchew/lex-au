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
