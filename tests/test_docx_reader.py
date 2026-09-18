import pytest
from pathlib import Path
from docx import Document
from docx.oxml import parse_xml
from lexau.docx_reader import iter_paragraphs
from lexau.parser import ElementType

CORPUS_DOCX = Path(__file__).parent / "fixtures" / "docx"


def test_paragraph_passthrough():
    doc = Document()
    doc.add_paragraph("Hello world")
    results = list(iter_paragraphs(doc))
    texts = [p.text for p in results if p.text.strip()]
    assert "Hello world" in texts


def test_table_extracted_as_table_type():
    doc = Document()
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "H1"
    table.cell(0, 1).text = "H2"
    table.cell(1, 0).text = "D1"
    table.cell(1, 1).text = "D2"
    results = list(iter_paragraphs(doc))
    table_blocks = [p for p in results if p.element_type == ElementType.TABLE]
    assert len(table_blocks) == 1
    assert table_blocks[0].table_rows == [["H1", "H2"], ["D1", "D2"]]


def test_document_order_preserved():
    doc = Document()
    doc.add_paragraph("Before")
    t = doc.add_table(rows=1, cols=1)
    t.cell(0, 0).text = "Cell"
    doc.add_paragraph("After")
    results = list(iter_paragraphs(doc))
    meaningful = [p for p in results if p.text.strip() or p.element_type == ElementType.TABLE]
    table_idx = next(i for i, p in enumerate(meaningful) if p.element_type == ElementType.TABLE)
    assert meaningful[table_idx - 1].text.strip() == "Before"
    assert meaningful[table_idx + 1].text.strip() == "After"


def test_empty_paragraph_yields_skip():
    doc = Document()
    doc.add_paragraph("")
    results = list(iter_paragraphs(doc))
    skip_results = [p for p in results if p.element_type == ElementType.SKIP]
    assert len(skip_results) >= 1


def test_list_level_detection():
    """A DOCX paragraph with numPr at ilvl=0 yields LIST_ITEM with number='0'."""
    doc = Document()
    p = doc.add_paragraph("Plain list item text")
    # Inject numPr to mark paragraph as a list item at level 0
    pPr_xml = (
        '<w:pPr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:numPr>'
        '<w:ilvl w:val="0"/>'
        '<w:numId w:val="1"/>'
        '</w:numPr>'
        '</w:pPr>'
    )
    p._element.insert(0, parse_xml(pPr_xml))

    results = list(iter_paragraphs(doc))
    list_items = [r for r in results if r.element_type == ElementType.LIST_ITEM]
    assert len(list_items) == 1
    assert list_items[0].number == "0"
    assert list_items[0].text == "Plain list item text"


def test_list_level_detection_nested():
    """A list paragraph at ilvl=1 yields LIST_ITEM with number='1'."""
    doc = Document()
    p = doc.add_paragraph("Nested list item")
    pPr_xml = (
        '<w:pPr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:numPr>'
        '<w:ilvl w:val="1"/>'
        '<w:numId w:val="1"/>'
        '</w:numPr>'
        '</w:pPr>'
    )
    p._element.insert(0, parse_xml(pPr_xml))

    results = list(iter_paragraphs(doc))
    list_items = [r for r in results if r.element_type == ElementType.LIST_ITEM]
    assert len(list_items) == 1
    assert list_items[0].number == "1"


def test_figure_element_type():
    """A paragraph containing an a:blip DrawingML element yields FIGURE element type.

    Because the paragraph also carries text, it SPLITS (v0.3.1 §2): the text is
    re-homed to a normally-classified paragraph and the FIGURE is text-free.
    """
    doc = Document()
    p = doc.add_paragraph("Figure caption text")
    # Inject a DrawingML inline image blip into the paragraph element
    blip_xml = (
        '<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:drawing>'
        '<wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<a:blip r:embed="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
        '</a:graphicData>'
        '</a:graphic>'
        '</wp:inline>'
        '</w:drawing>'
        '</w:r>'
    )
    p._element.append(parse_xml(blip_xml))

    results = list(iter_paragraphs(doc))
    figures = [r for r in results if r.element_type == ElementType.FIGURE]
    assert len(figures) == 1
    assert figures[0].text == ""
    assert [r.text for r in results if r.text.strip()] == ["Figure caption text"]


from lexau.parser import InlineSpan


def test_italic_run_populates_spans():
    """A paragraph with one italic run yields ParsedParagraph with spans."""
    doc = Document()
    p = doc.add_paragraph()
    run = p.add_run("personal information")
    run.italic = True
    results = list(iter_paragraphs(doc))
    body = [r for r in results if r.text.strip() == "personal information"]
    assert len(body) == 1
    pp = body[0]
    assert len(pp.spans) == 1
    assert pp.spans[0].text == "personal information"
    assert pp.spans[0].italic is True
    assert pp.spans[0].bold is False


def test_bold_run_populates_spans():
    doc = Document()
    p = doc.add_paragraph()
    run = p.add_run("important")
    run.bold = True
    results = list(iter_paragraphs(doc))
    body = [r for r in results if r.text.strip() == "important"]
    assert len(body) == 1
    assert body[0].spans[0].bold is True


def test_mixed_runs_populate_spans():
    """Italic run followed by plain run yields two spans."""
    doc = Document()
    p = doc.add_paragraph()
    r1 = p.add_run("term")
    r1.italic = True
    r2 = p.add_run(" means something")
    results = list(iter_paragraphs(doc))
    body = [r for r in results if "term" in r.text]
    assert len(body) == 1
    pp = body[0]
    assert len(pp.spans) == 2
    assert pp.spans[0].italic is True
    assert pp.spans[0].text == "term"
    assert pp.spans[1].italic is False
    assert pp.spans[1].text == " means something"


def test_plain_runs_span_not_formatted():
    doc = Document()
    p = doc.add_paragraph("hello world")
    results = list(iter_paragraphs(doc))
    body = [r for r in results if r.text.strip() == "hello world"]
    assert len(body) == 1
    pp = body[0]
    # spans may be populated but none should be formatted
    assert all(not (s.bold or s.italic or s.superscript or s.subscript) for s in pp.spans)


def test_superscript_run_populates_spans():
    doc = Document()
    p = doc.add_paragraph()
    r = p.add_run("2")
    r.font.superscript = True
    results = list(iter_paragraphs(doc))
    body = [r for r in results if r.text.strip() == "2"]
    assert len(body) == 1
    assert body[0].spans[0].superscript is True


def test_image_paragraph_spans_empty():
    """FIGURE paragraphs (inline image) still have empty spans."""
    doc = Document()
    p = doc.add_paragraph("Figure caption")
    blip_xml = (
        '<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:drawing>'
        '<wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">'
        '<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<a:blip r:embed="rId1" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/>'
        '</a:graphicData>'
        '</a:graphic>'
        '</wp:inline>'
        '</w:drawing>'
        '</w:r>'
    )
    p._element.append(parse_xml(blip_xml))
    results = list(iter_paragraphs(doc))
    figures = [r for r in results if r.element_type.value == "figure"]
    assert len(figures) == 1
    assert figures[0].spans == []


def test_smart_tag_wrapped_run_populates_spans():
    """A <w:r> nested inside <w:smartTag> must not be silently dropped.

    Real corpus bug (Task 1 triage, 2026-09-08, wp_garble Group A /
    wp_word_drop Bug 1): Word's legacy Smart Tags feature wraps
    auto-detected place/person names in <w:smartTag>, and python-docx's own
    Paragraph.runs only finds direct-child <w:r> elements
    (docx.oxml.text.paragraph.CT_P.r_lst is `ZeroOrMore("w:r")`, a
    direct-child XPath) -- any run nested inside a smartTag wrapper is
    invisible to it, so its text is dropped entirely. Confirmed real case:
    australian-capital-territory-(planning-and-land-management)-act-1988's
    "National Land" definiendum (nested
    <w:smartTag element="place"><w:smartTag element="PlaceName">National
    </w:smartTag> <w:smartTag element="PlaceType">Land</w:smartTag>
    </w:smartTag>) vanished entirely, leaving only "has the meaning given by
    section 27." with no defined term at all.
    """
    doc = Document()
    p = doc.add_paragraph()
    p.add_run("The land is ")
    smart_tag_xml = (
        '<w:smartTag xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'w:uri="urn:schemas-microsoft-com:office:smarttags" w:element="place">'
        '<w:smartTag w:uri="urn:schemas-microsoft-com:office:smarttags" w:element="PlaceName">'
        '<w:r><w:t>National</w:t></w:r>'
        '</w:smartTag>'
        '<w:r><w:t xml:space="preserve"> </w:t></w:r>'
        '<w:smartTag w:uri="urn:schemas-microsoft-com:office:smarttags" w:element="PlaceType">'
        '<w:r><w:t>Land</w:t></w:r>'
        '</w:smartTag>'
        '</w:smartTag>'
    )
    p._element.append(parse_xml(smart_tag_xml))
    p.add_run(" for the purposes of this Act.")

    results = list(iter_paragraphs(doc))
    body = [r for r in results if "National Land" in r.text]
    assert len(body) == 1
    assert body[0].text == "The land is National Land for the purposes of this Act."
    # The smart-tag runs must show up as their own spans too, not just be
    # folded into full_text -- downstream builder consumes p.spans, not
    # p.text, whenever any formatting is present.
    span_text = "".join(s.text for s in body[0].spans)
    assert span_text == body[0].text


def test_smart_tag_wrapped_run_preserved_in_table_cell():
    """Same smartTag bug, table-cell path.

    Real case: comprehensive-nuclear-test-ban-treaty-act-1998's schedule
    table cell "The day on which the Treaty enters into force for Australia"
    -- "Australia" wrapped in
    <w:smartTag element="country-region"><w:smartTag element="place"> --
    dropped entirely by `cell.text` (docx.oxml.text.paragraph.CT_P.text uses
    the same direct-child-only "w:r | w:hyperlink" XPath as r_lst), leaving
    "The day on which the Treaty enters into force for ." in the AKN output.
    """
    doc = Document()
    table = doc.add_table(rows=1, cols=1)
    cell = table.cell(0, 0)
    cell_p = cell.paragraphs[0]._p
    cell_p.append(parse_xml(
        '<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:t xml:space="preserve">The day on which the Treaty enters into force for </w:t>'
        '</w:r>'
    ))
    cell_p.append(parse_xml(
        '<w:smartTag xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'w:uri="urn:schemas-microsoft-com:office:smarttags" w:element="country-region">'
        '<w:smartTag w:uri="urn:schemas-microsoft-com:office:smarttags" w:element="place">'
        '<w:r><w:t>Australia</w:t></w:r>'
        '</w:smartTag>'
        '</w:smartTag>'
    ))

    results = list(iter_paragraphs(doc))
    table_blocks = [r for r in results if r.element_type == ElementType.TABLE]
    assert len(table_blocks) == 1
    assert table_blocks[0].table_rows == [
        ["The day on which the Treaty enters into force for Australia"]
    ]


def test_hyperlink_wrapped_run_preserved_in_table_cell():
    """Regression guard for a bug introduced (then caught in code review,
    2026-09-16) by the smart-tag fix above: python-docx's own `_Cell.text`
    (what the original `cell.text.strip()` used) sources from `CT_P.text`,
    whose `xpath("w:r | w:hyperlink")` already saw runs wrapped in
    <w:hyperlink> -- unlike `Paragraph.runs`, which never did. Swapping in an
    `_iter_run_elements` that only recursed into <w:smartTag> silently
    regressed that: any table cell containing a hyperlink would lose its
    text. Corpus impact was 0 (no <w:hyperlink> sits inside a <w:tc> in this
    corpus, verified in review), but the invariant was false. Confirmed
    the fix by scanning: `_iter_run_elements` now recurses into <w:hyperlink>
    too, matching `_Cell.text`'s original behaviour exactly.
    """
    doc = Document()
    table = doc.add_table(rows=1, cols=1)
    cell = table.cell(0, 0)
    cell_p = cell.paragraphs[0]._p
    cell_p.append(parse_xml(
        '<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:t xml:space="preserve">See </w:t>'
        '</w:r>'
    ))
    cell_p.append(parse_xml(
        '<w:hyperlink xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'r:id="rId1">'
        '<w:r><w:t>the Federal Register of Legislation</w:t></w:r>'
        '</w:hyperlink>'
    ))
    cell_p.append(parse_xml(
        '<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        '<w:t xml:space="preserve"> for the current version.</w:t>'
        '</w:r>'
    ))

    results = list(iter_paragraphs(doc))
    table_blocks = [r for r in results if r.element_type == ElementType.TABLE]
    assert len(table_blocks) == 1
    assert table_blocks[0].table_rows == [
        ["See the Federal Register of Legislation for the current version."]
    ]


def test_hyperlink_wrapped_run_populates_spans():
    """Same hyperlink fix, paragraph-span path -- extends `_iter_run_elements`
    hyperlink recursion to `iter_paragraphs`'s span-building loop too, so a
    hyperlinked cross-reference in ordinary body text is no longer silently
    dropped from operative text either (previously invisible to
    `Paragraph.runs`, same shape as the smart-tag bug, just not
    corpus-confirmed by Task 1).
    """
    doc = Document()
    p = doc.add_paragraph()
    p.add_run("See ")
    p._element.append(parse_xml(
        '<w:hyperlink xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        'r:id="rId1">'
        '<w:r><w:t>the Register</w:t></w:r>'
        '</w:hyperlink>'
    ))
    p.add_run(" for details.")

    results = list(iter_paragraphs(doc))
    body = [r for r in results if "the Register" in r.text]
    assert len(body) == 1
    assert body[0].text == "See the Register for details."


def test_loan_act_1976_shape1_fixture():
    # Shape 1: separate bold heading + single-tab numbered body.
    # Expect 5 sections (Short title, Commencement, Authority to borrow,
    # Application of moneys borrowed, Expenses of borrowing), 0 subsections.
    doc = Document(str(CORPUS_DOCX / "loan-act-(no.-2)-1976-vol0.docx"))
    paras = list(iter_paragraphs(doc))
    sections = [p for p in paras if p.element_type == ElementType.SECTION]
    subsections = [p for p in paras if p.element_type == ElementType.SUBSECTION]
    assert len(sections) == 5
    assert len(subsections) == 0
    assert sections[0].heading == "Short title."
    assert sections[1].heading == "Commencement."


def test_albury_wodonga_1982_shape2_fixture():
    # Shape 2: fused section+subsection, "1. (1) ...".
    # Expect section 1 containing subsection (1) and subsection (2).
    doc = Document(str(
        CORPUS_DOCX / "albury-wodonga-development-(financial-assistance)-amendment-act-1982-vol0.docx"
    ))
    paras = list(iter_paragraphs(doc))
    sections = [p for p in paras if p.element_type == ElementType.SECTION]
    subsections = [p for p in paras if p.element_type == ElementType.SUBSECTION]
    assert any(s.number == "1" for s in sections)
    subsec_numbers = {s.number for s in subsections}
    assert "1" in subsec_numbers
    assert "2" in subsec_numbers


def test_act_supreme_court_1992_heading_without_style():
    # PART 1—PRELIMINARY styled as plain bold Normal text, no ActHead
    # paragraphs anywhere; tests _HEADING_RE running without the style gate.
    doc = Document(str(
        CORPUS_DOCX / "a.c.t.-supreme-court-(transfer)-act-1992-vol0.docx"
    ))
    paras = list(iter_paragraphs(doc))
    parts = [p for p in paras if p.element_type == ElementType.PART]
    assert len(parts) >= 1
    assert any("PRELIMINARY" in p.heading.upper() for p in parts)


def test_agricultural_chemical_levy_1994_shape3_fixture():
    # Shape 3: style-driven section heading ("Heading 5" style, "N  Heading"
    # text) + "subsection"-styled body/numbered-subsection paragraphs.
    # Expect 4 sections (Short title, Commencement, Imposition, Act does
    # not impose levy on property of a State); sections 3 and 4 each have
    # 2 numbered subsections, sections 1 and 2 have none.
    doc = Document(str(
        CORPUS_DOCX / "agricultural-and-veterinary-chemical-products-levy-imposition-(customs)-act-1994-vol0.docx"
    ))
    paras = list(iter_paragraphs(doc))
    sections = [p for p in paras if p.element_type == ElementType.SECTION]
    subsections = [p for p in paras if p.element_type == ElementType.SUBSECTION]
    assert len(sections) == 4
    assert sections[0].heading == "Short title"
    assert sections[2].heading == "Imposition"
    assert {s.number for s in subsections} >= {"1", "2"}


def test_northern_territory_commonwealth_lands_1980_shape3_fixture():
    # Expect 3 sections (Short title, Commencement, Notification of
    # acquisition of certain interests in land); section 3 has 3 numbered
    # subsections.
    doc = Document(str(
        CORPUS_DOCX / "northern-territory-(commonwealth-lands)-act-1980-vol0.docx"
    ))
    paras = list(iter_paragraphs(doc))
    sections = [p for p in paras if p.element_type == ElementType.SECTION]
    subsections = [p for p in paras if p.element_type == ElementType.SUBSECTION]
    assert len(sections) == 3
    assert sections[0].heading == "Short title"
    assert sections[2].heading == "Notification of acquisition of certain interests in land"
    assert {s.number for s in subsections} >= {"1", "2", "3"}


def test_loan_war_service_land_settlement_1970_shape3_fixture():
    # Expect 4 sections (Short title, Commencement, Authority to borrow
    # $4,500,000, Application of moneys), 0 subsections (all bodies are
    # plain "subsection"-styled prose with no "(N)" numbering).
    doc = Document(str(
        CORPUS_DOCX / "loan-(war-service-land-settlement)-act-1970-vol0.docx"
    ))
    paras = list(iter_paragraphs(doc))
    sections = [p for p in paras if p.element_type == ElementType.SECTION]
    assert len(sections) == 4
    assert sections[0].heading == "Short title"
    assert sections[3].heading == "Application of moneys"


def test_constitution_alteration_state_debts_1909_family_f_fixture():
    # Family F (XSD baseline, docs/superpowers/2026-09-07-xsd-baseline.md):
    # 8 corpus files -- this is the smallest -- whose marginal-note headings
    # are NOT bolded, unlike loan-act-(no.-2)-1976's identically-shaped
    # ("Short title." / "1.\ttext") but *bolded* donor. Before the fix,
    # neither of this Act's two sections was ever classified as SECTION, so
    # _split_stream's preface_end search found no structural element and the
    # entire Act -- including both operative sections -- fell into
    # <preface>, leaving <body/> completely empty (SCHEMAV_ELEMENT_CONTENT
    # body | missing-child:hcontainer).
    from datetime import date

    from lxml import etree

    from lexau.builder import AknBuilder
    from lexau.models import ActMetadata

    doc = Document(str(CORPUS_DOCX / "constitution-alteration-(state-debts)-1909-vol0.docx"))
    meta = ActMetadata(
        name="Constitution Alteration (State Debts) 1909",
        title_id="C1909A00003",
        comp_id="C1909Q00001",
        comp_num="1",
        year=1909,
        number=3,
        effective_date=date(1910, 8, 6),
    )
    b = AknBuilder(meta)
    for p in iter_paragraphs(doc):
        b.add(p)
    root, _report = b.build()

    ns = {"akn": "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"}
    body = root.find(".//akn:body", ns)
    preface = root.find(".//akn:preface", ns)
    assert body is not None
    structural_children = body.findall("akn:hcontainer", ns) + body.findall("akn:section", ns)
    assert len(structural_children) >= 1

    preface_text = " ".join(preface.itertext()) if preface is not None else ""
    assert "This Act may be cited as Constitution Alteration" not in preface_text
    assert "Section one hundred and five of the Constitution is altered" not in preface_text

    body_text = " ".join(body.itertext())
    assert "This Act may be cited as Constitution Alteration" in body_text
    assert "Section one hundred and five of the Constitution is altered" in body_text


FIGURES_DOCX = Path(__file__).parent / "fixtures" / "figures"


def test_figure_paragraph_carries_dotted_ext_blobs():
    figs = [
        p
        for p in iter_paragraphs(Document(str(FIGURES_DOCX / "one_wmf.docx")))
        if p.element_type == ElementType.FIGURE
    ]
    assert len(figs) == 1 and len(figs[0].image_blobs) == 1
    ext, blob = figs[0].image_blobs[0]
    assert ext == ".wmf" and isinstance(blob, bytes) and blob


def test_figure_paragraph_png_blob_dotted_ext():
    figs = [
        p
        for p in iter_paragraphs(Document(str(FIGURES_DOCX / "one_png.docx")))
        if p.element_type == ElementType.FIGURE
    ]
    assert len(figs) == 1
    assert [ext for ext, _ in figs[0].image_blobs] == [".png"]


def test_non_figure_paragraph_has_empty_image_blobs():
    doc = Document()
    doc.add_paragraph("plain text")
    paras = list(iter_paragraphs(doc))
    assert paras and all(p.image_blobs == [] for p in paras)


# --- v0.3.1 §2: VML-only figure extraction ------------------------------------
#
# Legacy DOCX embed an image as VML (<w:pict>/<v:imagedata r:id>) with no
# DrawingML <a:blip>. The reader must treat those as figures, but only after
# the four decoration guards: mc:Fallback (the mc:Choice a:blip sibling is the
# real source), w:object (OLE equation/embedded-doc preview), sub-8pt shapes
# (horizontal-rule dividers) and the cover-page Coat-of-Arms crest blob.

from io import BytesIO

from docx.oxml.ns import qn as _qn

from lexau.docx_reader import (
    _CREST_BYTES,
    _figure_blobs,
    _has_inline_image,
    _vml_figure_parts,
)
from tests.test_figures import _PNG_1x1

_VML_DECLS = (
    ' xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    ' xmlns:v="urn:schemas-microsoft-com:vml"'
    ' xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    ' xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
)

_FIG_STYLE = "width:120pt;height:24.75pt"
_VML_IMAGEDATA_TAG = ".//{urn:schemas-microsoft-com:vml}imagedata"


def _pict_run(rid: str, style: str = _FIG_STYLE, *, host: str = "w:pict"):
    """A <w:r> holding a single VML <v:imagedata r:id>, optionally inside <w:object>."""
    shape = f'<v:shape style="{style}"><v:imagedata r:id="{rid}"/></v:shape>'
    if host == "w:object":
        inner = f"<w:object>{shape}</w:object>"
    else:
        inner = f"<w:pict>{shape}</w:pict>"
    return parse_xml(f"<w:r{_VML_DECLS}>{inner}</w:r>")


def _vml_doc(text: str = "", *, style: str = _FIG_STYLE, host: str = "w:pict", rid: str = "rId21"):
    """one_wmf.docx with its DrawingML run swapped for VML markup on rId21.

    rId21 -> /word/media/image2.wmf (10,354 bytes) in that fixture, so the
    relationship resolves exactly as it does in a real legacy compilation.
    """
    doc = Document(str(FIGURES_DOCX / "one_wmf.docx"))
    para = doc.paragraphs[0]
    for run in list(para._element.findall(_qn("w:r"))):
        para._element.remove(run)
    if text:
        para.add_run(text)
    para._element.append(_pict_run(rid, style, host=host))
    return doc, para


def test_vml_only_paragraph_counts_as_inline_image():
    _, para = _vml_doc()
    assert para._element.findall(f".//{_qn('a:blip')}") == []
    assert _has_inline_image(para) is True


def test_vml_only_paragraph_yields_dotted_wmf_blob():
    _, para = _vml_doc()
    blobs = _figure_blobs(para)
    assert len(blobs) == 1
    ext, blob = blobs[0]
    assert ext == ".wmf"
    assert isinstance(blob, bytes) and len(blob) == 10354


def test_vml_unresolvable_rid_is_not_a_figure():
    _, para = _vml_doc(rid="rIdNoSuchThing")
    assert _has_inline_image(para) is False
    assert _figure_blobs(para) == []


def test_vml_ole_object_preview_is_not_a_figure():
    """<w:object> wraps an OLE equation preview, not a document figure."""
    _, para = _vml_doc(host="w:object")
    assert _has_inline_image(para) is False
    assert _figure_blobs(para) == []


def test_vml_sub_8pt_shape_is_a_rule_not_a_figure():
    _, para = _vml_doc(style="width:400pt;height:2.25pt")
    assert _has_inline_image(para) is False


def _crest_doc(blob_len: int, *, text: str = ""):
    """A doc whose VML image part blob is exactly ``blob_len`` bytes.

    Built by padding the 1x1 PNG with trailing bytes (the PNG chunk stream
    ends at IEND, so python-docx still parses the header) and referencing the
    resulting image part from VML.
    """
    padded = _PNG_1x1 + b"\x00" * (blob_len - len(_PNG_1x1))
    doc = Document()
    holder = doc.add_paragraph()
    holder.add_run().add_picture(BytesIO(padded))
    blip = holder._element.findall(f".//{_qn('a:blip')}")[0]
    rid = blip.get(_qn("r:embed"))
    for run in list(holder._element.findall(_qn("w:r"))):
        holder._element.remove(run)
    if text:
        holder.add_run(text)
    holder._element.append(_pict_run(rid, "width:82.5pt;height:99pt"))
    return doc, holder, rid


def test_vml_cover_crest_is_not_a_figure():
    """Text-free paragraph whose blob is a known Coat-of-Arms WMF size."""
    crest_len = sorted(_CREST_BYTES)[0]
    doc, para, _ = _crest_doc(crest_len)
    assert len(para.part.related_parts[_pict_rid(para)].blob) in _CREST_BYTES
    assert _has_inline_image(para) is False


def test_vml_crest_sized_blob_with_text_is_still_a_figure():
    """The crest guard is text-free-only: a captioned image of the same byte
    length is a real figure, not cover boilerplate."""
    crest_len = sorted(_CREST_BYTES)[0]
    _, para, _ = _crest_doc(crest_len, text="Figure 1—the diagram")
    assert _has_inline_image(para) is True


def _pict_rid(para) -> str:
    idt = para._element.findall(
        ".//{urn:schemas-microsoft-com:vml}imagedata"
    )[0]
    return idt.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")


def test_mc_fallback_vml_defers_to_drawingml_blip():
    """mc:AlternateContent — the mc:Choice <a:blip> is the source of truth and
    the mc:Fallback <v:imagedata> must contribute nothing."""
    import copy

    doc = Document(str(FIGURES_DOCX / "one_wmf.docx"))
    holder = doc.add_paragraph()
    holder.add_run().add_picture(BytesIO(_PNG_1x1))
    drawing = copy.deepcopy(holder._element.findall(f".//{_qn('w:drawing')}")[0])

    para = doc.paragraphs[0]
    for run in list(para._element.findall(_qn("w:r"))):
        para._element.remove(run)
    run_el = parse_xml(
        f"<w:r{_VML_DECLS}><mc:AlternateContent>"
        '<mc:Choice Requires="wps"/>'
        f'<mc:Fallback><w:pict><v:shape style="{_FIG_STYLE}">'
        '<v:imagedata r:id="rId21"/></v:shape></w:pict></mc:Fallback>'
        "</mc:AlternateContent></w:r>"
    )
    choice = run_el.findall(
        ".//{http://schemas.openxmlformats.org/markup-compatibility/2006}Choice"
    )[0]
    choice.append(drawing)
    para._element.append(run_el)

    assert _vml_figure_parts(para) == []
    blobs = _figure_blobs(para)
    assert len(blobs) == 1
    ext, blob = blobs[0]
    assert ext == ".png"
    assert blob == _PNG_1x1
    assert len(blob) != 10354  # not the VML fallback's WMF


def test_crest_geometry_in_cover_region_is_not_a_figure():
    """The 7,036-byte Coat of Arms is outside _CREST_BYTES entirely; what marks
    it is crest geometry in the cover region."""
    _, para, _ = _crest_doc(7036)  # length deliberately NOT in _CREST_BYTES
    assert _has_inline_image(para, cover_region=True) is False
    # Same paragraph, same blob, outside the cover region: nothing to go on, so
    # it is treated as a figure (the hash pass is what suppresses real repeats).
    assert _has_inline_image(para, cover_region=False) is True


def test_crest_repeat_later_in_document_is_skipped():
    """Whole-document crest pass: a text-free, crest-shaped VML image in the
    cover region (doc position <= 8) registers its blob hash, so it and every
    byte-identical repeat later in the document are decoration, not figures."""
    doc, cover, rid = _crest_doc(40_000)  # length deliberately NOT in _CREST_BYTES
    for _ in range(12):
        doc.add_paragraph("Body prose that pushes the repeat past the cover region.")
    repeat = doc.add_paragraph()
    repeat._element.append(_pict_run(rid, "width:82.5pt;height:99pt"))

    figures = [p for p in iter_paragraphs(doc) if p.element_type == ElementType.FIGURE]
    assert figures == []


def test_cover_region_figure_outside_crest_box_survives():
    """The cover gate is geometry-bound: an image too large to be a crest is
    still extracted even at document position 0, and does not poison a later
    byte-identical repeat."""
    doc, cover, rid = _crest_doc(40_000)
    idt = cover._element.findall(_VML_IMAGEDATA_TAG)[0]
    idt.getparent().set("style", "width:430pt;height:320pt")
    for _ in range(12):
        doc.add_paragraph("Body prose that pushes the repeat past the cover region.")
    repeat = doc.add_paragraph()
    repeat._element.append(_pict_run(rid, "width:430pt;height:320pt"))

    figures = [p for p in iter_paragraphs(doc) if p.element_type == ElementType.FIGURE]
    assert len(figures) == 2


def test_mixed_text_and_vml_image_splits_into_figure_plus_paragraph():
    """A <w:p> carrying BOTH operative text and an inline image must yield the
    normal (numbered) paragraph as well as the FIGURE, so the provision's text
    and eId survive. The FIGURE's own text is cleared to avoid a duplicate."""
    text = (
        "(a) if the annual pay of the member is less than the prescribed "
        "amount—the number ascertained in accordance with the formula"
    )
    _, para = _vml_doc(text)
    doc = para.part.document
    results = list(iter_paragraphs(doc))

    figures = [p for p in results if p.element_type == ElementType.FIGURE]
    assert len(figures) == 1
    assert figures[0].text.strip() == ""
    assert figures[0].image_blobs and figures[0].image_blobs[0][0] == ".wmf"

    provisions = [p for p in results if p.text.strip().startswith("(a) if the annual pay")]
    assert len(provisions) == 1
    assert provisions[0].element_type != ElementType.FIGURE
    # The provision is emitted BEFORE the figure, so the builder nests the
    # <figure> inside the paragraph it belongs to rather than its predecessor.
    assert results.index(provisions[0]) < results.index(figures[0])


def test_text_free_image_paragraph_is_figure_only():
    """Regression: a dedicated image-only <w:p> still yields exactly one
    FIGURE and no extra body paragraph."""
    _, para = _vml_doc()
    doc = para.part.document
    results = list(iter_paragraphs(doc))
    assert [p.element_type for p in results].count(ElementType.FIGURE) == 1
    assert not [p for p in results if p.element_type == ElementType.BODY and p.text.strip()]
