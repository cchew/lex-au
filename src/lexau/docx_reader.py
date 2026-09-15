from __future__ import annotations

import hashlib
import re
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.text.run import Run
from lxml import etree

from lexau.parser import (
    ElementType,
    InlineSpan,
    ParsedParagraph,
    classify_legacy_stream,
    is_legacy_document,
    parse_paragraph,
)

# --- VML (legacy) inline images ---------------------------------------------
#
# Pre-2010 compilations embed an image as VML (<w:pict> wrapping
# <v:shape><v:imagedata r:id>) with no DrawingML <a:blip>. 142 live Acts carry
# 621 such figure paragraphs -- almost all rendered mathematical formulae in
# 1970s-1980s superannuation Acts (investigation note
# docs/superpowers/notes/2026-09-07-p3-vml.md).
#
# A bare `.//v:imagedata` match is NOT safe: corpus-wide it returns ~5,000
# DOCX, dominated by 6,988 OLE-object equation previews, 1,794 cover-page
# Coat-of-Arms crest paragraphs and 246 horizontal-rule PNG dividers. Every
# guard below is load-bearing -- without the crest guard alone, the cover
# Coat-of-Arms WMF reclassifies as a figure and injects an empty <p> into
# <preface> for ~63 Acts.
_VML_IMAGEDATA = "{urn:schemas-microsoft-com:vml}imagedata"
_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
_REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"

# Observed byte lengths of the Commonwealth Coat of Arms cover WMF/PNG.
_CREST_BYTES = frozenset({36736, 36536, 32784, 36436, 36336})

# Crest shapes are not one fixed blob: a second, much smaller Coat-of-Arms WMF
# (7,036 bytes, one hash recurring across 17 live Acts) and several one-off
# re-renders sit outside _CREST_BYTES entirely. What they share is geometry --
# every cover crest measured in the live corpus lands in 106-191 pt wide by
# 79-112 pt tall. A text-free image paragraph in the cover region whose shape
# falls in this (deliberately wider) box is boilerplate, not a figure. Without
# this gate the byte-length list alone lets 29 extra Acts through with a crest
# masquerading as their only figure.
_CREST_BOX_PT = (55.0, 200.0, 55.0, 140.0)  # w_min, w_max, h_min, h_max

# A VML shape whose smaller dimension is under this is a rule/divider, not a
# figure (the corpus' 246 horizontal-rule PNGs all sit well under 6 pt).
_MIN_FIGURE_PT = 8.0

# Paragraph index (0-based) up to which a text-free image paragraph counts as
# cover-page boilerplate for the whole-document crest-hash pass.
_CREST_POS_LIMIT = 8

_VML_DIM_RE = re.compile(r"\b(width|height)\s*:\s*(-?[0-9.]+)\s*pt", re.IGNORECASE)

# --- Smart Tags / hyperlinks (transparent run wrappers) ---------------------
#
# Word's legacy "Smart Tags" feature wraps auto-detected place/person/date
# spans -- <w:element="place">, "PlaceName", "PlaceType", "country-region",
# "PersonName" all confirmed present in the corpus -- in a <w:smartTag>
# element sitting BETWEEN <w:p> and the <w:r> run(s) it contains (and smart
# tags can nest, e.g. <w:smartTag place><w:smartTag PlaceName><w:r>...).
# python-docx's own `Paragraph.runs` (CT_P.r_lst, generated from a
# `ZeroOrMore("w:r")` grammar entry, direct-children-only) walks only DIRECT
# children of <w:p> -- any run nested inside a <w:smartTag> is invisible to
# it, and its text is silently dropped. Confirmed real losses (Task 1 triage,
# 2026-09-08): "National Land" and "Australia" (x5 distinct Acts) vanish
# entirely from operative text; when the smart-tag boundary falls mid-token
# the drop instead garbles the surviving fragments ("is 1/11" -> "i/11").
#
# `Paragraph.text`/`_Cell.text` (CT_P.text: `"".join(e.text for e in
# self.xpath("w:r | w:hyperlink"))`) is ALSO direct-children-only, so it
# drops smart-tag-wrapped runs the same way -- but unlike `.runs`, it does
# already see runs wrapped in <w:hyperlink> (an earlier version of
# `_cell_text` below did not, which regressed hyperlink text in table cells
# that `_Cell.text` used to preserve -- caught in code review, 2026-09-16;
# zero corpus impact at the time, since no <w:hyperlink> in this corpus sits
# inside a <w:tc>, but the invariant was false and would have bitten the
# first cell that did).
#
# _iter_run_elements recurses into both <w:smartTag> and <w:hyperlink>
# (arbitrarily deep / in combination, to handle nesting) so runs wrapped in
# either are found in document order, for BOTH callers below -- paragraph
# spans now see hyperlink-wrapped text for the first time too (previously
# invisible to `.runs`, same silent-drop shape as the smart-tag bug this task
# exists to fix, just not corpus-confirmed by Task 1). It deliberately does
# NOT recurse into <w:ins>/<w:del> or <w:sdt> -- those are unconfirmed by
# Task 1's triage and structurally different (revision-tracking and content
# controls, not simple transparent wrappers); existing behaviour for them
# (whatever it is) is unchanged.
_W_R = qn("w:r")
_W_SMARTTAG = qn("w:smartTag")
_W_HYPERLINK = qn("w:hyperlink")
_TRANSPARENT_WRAPPERS = (_W_SMARTTAG, _W_HYPERLINK)


def _iter_run_elements(parent_el: etree._Element) -> Iterator[etree._Element]:
    """Yield <w:r> descendants of ``parent_el`` in document order, recursing
    into (possibly nested/combined) <w:smartTag> and <w:hyperlink> wrappers.
    See module comment above.
    """
    for child in parent_el:
        if child.tag == _W_R:
            yield child
        elif child.tag in _TRANSPARENT_WRAPPERS:
            yield from _iter_run_elements(child)


def _cell_text(cell) -> str:
    """Table cell text, including text nested inside <w:smartTag> and
    <w:hyperlink> wrappers.

    Mirrors python-docx's own `_Cell.text` (`"\\n".join(p.text for p in
    self.paragraphs)`) but sources each paragraph's text from
    `_iter_run_elements` instead of `Paragraph.text`, so smart-tag-wrapped
    runs (see module comment above) are not dropped -- while still matching
    `_Cell.text`'s original hyperlink-inclusive behaviour. `Run(r, p).text`
    still handles the same `<w:tab/>`/`<w:cr/>`/`<w:br>` translation
    `CT_P.text` did for each individual run.
    """
    return "\n".join(
        "".join(Run(r, p).text for r in _iter_run_elements(p._element))
        for p in cell.paragraphs
    )


def _iter_ancestors(el: etree._Element) -> Iterator[etree._Element]:
    """Yield ``el``'s ancestors, nearest first, up to the document root."""
    node = el.getparent()
    while node is not None:
        yield node
        node = node.getparent()


def _vml_shape_pt(shape_el: etree._Element | None) -> tuple[float | None, float | None]:
    """Parse ``style="width:..pt;height:..pt"`` into ``(width, height)`` points.

    Returns ``(None, None)`` when the host shape carries no style, or sizes it
    in a unit other than points (VML also allows px/in/cm) -- an unparsed
    dimension must never gate a figure out.
    """
    if shape_el is None:
        return (None, None)
    dims = {
        key.lower(): float(value)
        for key, value in _VML_DIM_RE.findall(shape_el.get("style") or "")
    }
    return (dims.get("width"), dims.get("height"))


def _is_crest_shape(width: float | None, height: float | None) -> bool:
    """True if a VML shape's declared size is cover-crest geometry."""
    if width is None or height is None:
        return False
    w_min, w_max, h_min, h_max = _CREST_BOX_PT
    return w_min <= width <= w_max and h_min <= height <= h_max


def _vml_figure_parts(
    para: Paragraph,
    crest_hashes: frozenset[bytes] = frozenset(),
    *,
    cover_region: bool = False,
) -> list:
    """Return the resolvable ``<v:imagedata>`` image parts that are real figures.

    A candidate survives only if:

    - its ``r:id`` resolves to an embedded image part;
    - it has no ``<mc:Fallback>`` ancestor -- in an ``<mc:AlternateContent>``
      pair the ``<mc:Choice>`` ``<a:blip>`` sibling is the source of truth and
      the VML twin is inert (all 4 corpus coexistences are this shape);
    - it has no ``<w:object>`` ancestor -- that is an OLE equation or
      embedded-document preview, not a document figure;
    - its host ``<v:shape>``, where it declares one in points, is at least
      ``_MIN_FIGURE_PT`` on its smaller side -- smaller is a rule/divider;
    - it is not cover-page Coat-of-Arms boilerplate. Three separate tests,
      all restricted to text-free paragraphs: a known crest byte length; crest
      geometry inside the cover region (``cover_region``); or a blob
      byte-identical to one the cover region already registered
      (``crest_hashes``), which kills the page-2 and part-divider repeats.
    """
    out: list = []
    w_object = qn("w:object")
    para_text = "".join(para._element.itertext()).strip()
    for idt in para._element.findall(f".//{_VML_IMAGEDATA}"):
        rid = idt.get(_REL_ID)
        if not rid:
            continue
        if any(anc.tag in (_MC_FALLBACK, w_object) for anc in _iter_ancestors(idt)):
            continue
        width, height = _vml_shape_pt(idt.getparent())
        if width is not None and height is not None and min(width, height) < _MIN_FIGURE_PT:
            continue
        try:
            part = para.part.related_parts[rid]
        except KeyError:
            continue
        if not para_text and cover_region and _is_crest_shape(width, height):
            continue
        blob = part.blob
        if not para_text and len(blob) in _CREST_BYTES:
            continue
        if crest_hashes and hashlib.sha1(blob).digest() in crest_hashes:
            continue
        out.append(part)
    return out


def _crest_blob_hashes(blocks: list) -> frozenset[bytes]:
    """SHA-1 digests of the cover-region crest blobs in one document.

    A text-free, crest-shaped image paragraph within the first
    ``_CREST_POS_LIMIT`` + 1 paragraphs is cover boilerplate; any byte-identical
    repeat later in the document is the same crest recurring (page 2, part
    dividers) and must not be extracted as a figure. Registration is restricted
    to crest geometry so that a genuine figure appearing early in a volume can
    never poison its own later repeats.
    """
    seen: set[bytes] = set()
    pos = 0
    for block in blocks:
        if not isinstance(block, Paragraph):
            continue
        if pos > _CREST_POS_LIMIT:
            break
        pos += 1
        if "".join(block._element.itertext()).strip():
            continue
        for idt in block._element.findall(f".//{_VML_IMAGEDATA}"):
            rid = idt.get(_REL_ID)
            if not rid:
                continue
            try:
                part = block.part.related_parts[rid]
            except KeyError:
                continue
            width, height = _vml_shape_pt(idt.getparent())
            if not (_is_crest_shape(width, height) or len(part.blob) in _CREST_BYTES):
                continue
            seen.add(hashlib.sha1(part.blob).digest())
    return frozenset(seen)


def _has_inline_image(
    para: Paragraph,
    crest_hashes: frozenset[bytes] = frozenset(),
    *,
    cover_region: bool = False,
) -> bool:
    """Return True if the paragraph contains at least one inline figure image.

    DrawingML (``<a:blip>``) wins outright; VML is only consulted when there is
    no blip at all, so an ``<mc:AlternateContent>`` pair is never double-counted.
    """
    if para._element.findall(f".//{qn('a:blip')}"):
        return True
    return bool(_vml_figure_parts(para, crest_hashes, cover_region=cover_region))


def _figure_blobs(
    para: Paragraph,
    crest_hashes: frozenset[bytes] = frozenset(),
    *,
    cover_region: bool = False,
) -> list[tuple[str, bytes]]:
    """Return the first embedded image of a FIGURE paragraph as ``[(ext, bytes)]``.

    At most one entry: the first ``a:blip`` with a resolvable ``r:embed``
    relationship, in document order. The extension is taken from the image
    part name in its *dotted* form (``.wmf``, not ``wmf``) so downstream
    vector/raster routing works. A blip that only carries ``r:link``
    (external image) or an unresolvable rId is skipped; a FIGURE with no
    usable image yields an empty list.

    Capture is capped at one blob because the builder consumes only
    ``image_blobs[0]`` per FIGURE (spec design §A2). Two Acts
    (``excise-tariff-act-1921``, ``corporate-law-economic-reform-program-act-1999``)
    carry two inline ``a:blip`` in a single FIGURE ``<w:p>`` where the
    second blob is a byte-identical preview of the following figure; keeping
    only the first here stops an unreferenced ``-fig-N<letter>`` orphan file
    being written for those paragraphs.
    """
    for blip in para._element.findall(f".//{qn('a:blip')}"):
        rid = blip.get(qn("r:embed"))
        if not rid:
            continue
        try:
            part = para.part.related_parts[rid]
        except KeyError:
            continue
        ext = Path(str(part.partname)).suffix.lower()
        return [(ext, part.blob)]
    # VML fallback: only reached when the paragraph has no usable <a:blip>, so
    # the VML blob is an *alternative* first blob, never an additional one.
    # ".wmf" routes through figures.VECTOR_EXTS -> soffice with no extra wiring.
    for part in _vml_figure_parts(para, crest_hashes, cover_region=cover_region):
        ext = Path(str(part.partname)).suffix.lower()
        return [(ext, part.blob)]
    return []


def _list_level(para: Paragraph) -> int | None:
    """Return 0-based list level if paragraph is a list item, else None."""
    pPr = para._element.pPr
    if pPr is None:
        return None
    numPr = pPr.numPr
    if numPr is None:
        return None
    ilvl = numPr.ilvl
    return int(ilvl.val) if ilvl is not None else 0


def _all_bold(spans: list[InlineSpan]) -> bool:
    """True iff every span with non-whitespace text is bold."""
    non_ws = [s for s in spans if s.text.strip()]
    return bool(non_ws) and all(s.bold for s in non_ws)


def iter_paragraphs(doc: Document) -> Iterator[ParsedParagraph]:
    """Yield ParsedParagraph for each Paragraph and Table in document order.

    Uses doc.iter_inner_content() (python-docx 1.2.0) to preserve document order.
    Tables are yielded as ParsedParagraph(TABLE, table_rows=[[cell, ...], ...]).
    _cell_text() concatenates all paragraph text in the cell (including text
    nested inside <w:smartTag>/<w:hyperlink> wrappers); nested tables are
    flattened.
    FIGURE paragraphs (inline image) yield with empty spans.
    All other paragraphs populate spans from _iter_run_elements(), which walks
    the same smartTag/hyperlink-transparent run set as _cell_text().

    A `<w:p>` that carries BOTH its own text and an inline image is SPLIT: it
    is classified normally (so a numbered provision keeps its element type and,
    downstream, its eId) and additionally yields a text-free FIGURE immediately
    AFTER that provision. Pre-2010 drafting inlines a formula image mid-sentence
    -- "…ascertained in accordance with the formula [WMF], where A is…" -- so
    without the split the builder's FIGURE branch, which reads only
    `image_blobs`, would discard the provision's operative text and eId
    outright (7 Acts measured; see the Legacy-reclassification finding in
    docs/superpowers/notes/2026-09-07-p3-vml.md). Emitting the provision first
    matters: the builder appends `<figure>` to the open stack top, so a
    figure-first order would nest each figure inside its *predecessor*
    paragraph. This also fixes the same latent loss on the `a:blip` path, where
    it fires rarely only because modern Word templates give a figure its own
    dedicated `<w:p>`.

    Acts whose DOCX has no ActHead*-styled paragraph anywhere ("legacy"
    documents, ~550 of 2,944 in the corpus) route through
    classify_legacy_stream instead of parse_paragraph, since legacy Acts
    have no reliable style signal and must be classified from paragraph
    text and bold-run shape instead.
    """
    blocks = list(doc.iter_inner_content())
    # Cover-page boilerplate is gated two ways: geometry inside the cover
    # region, and byte-identity with a cover blob anywhere after it.
    crest_hashes = _crest_blob_hashes(blocks)
    _cover_ids = {
        id(b)
        for b in [b for b in blocks if isinstance(b, Paragraph)][: _CREST_POS_LIMIT + 1]
    }

    def _in_cover(block: Paragraph) -> bool:
        return id(block) in _cover_ids

    def _figure_only(block: Paragraph) -> bool:
        """True for a dedicated image-only paragraph (no text of its own)."""
        return _has_inline_image(
            block, crest_hashes, cover_region=_in_cover(block)
        ) and not block.text.strip()

    # Only text-free image paragraphs are held out of the classification
    # stream. A mixed text+image paragraph stays in it, exactly as it was
    # before VML extraction existed, so its style/legacy classification is
    # unchanged by the matcher.
    para_blocks: list[Paragraph] = [
        b for b in blocks if isinstance(b, Paragraph) and not _figure_only(b)
    ]
    styles = [b.style.name if b.style else "Default" for b in para_blocks]
    legacy = is_legacy_document(styles)

    para_spans: list[list[InlineSpan]] = []
    para_texts: list[str] = []
    for block in para_blocks:
        spans = [
            InlineSpan(
                text=run.text,
                bold=bool(run.bold),
                italic=bool(run.italic),
                superscript=bool(run.font.superscript),
                subscript=bool(run.font.subscript),
            )
            for run in (
                Run(r_el, block) for r_el in _iter_run_elements(block._element)
            )
            if run.text
        ]
        para_spans.append(spans)
        para_texts.append("".join(s.text for s in spans))

    if legacy:
        stream_input = [
            (text, _all_bold(spans), style)
            for text, spans, style in zip(para_texts, para_spans, styles)
        ]
        legacy_results = classify_legacy_stream(stream_input)
    else:
        legacy_results = None

    para_pos = 0
    for block in blocks:
        if isinstance(block, Paragraph):
            if _figure_only(block):
                yield ParsedParagraph(
                    ElementType.FIGURE,
                    text=block.text,
                    image_blobs=_figure_blobs(
                        block, crest_hashes, cover_region=_in_cover(block)
                    ),
                )
                continue
            style = styles[para_pos]
            full_text = para_texts[para_pos]
            spans = para_spans[para_pos]
            level = _list_level(block)

            if legacy:
                parsed_list = legacy_results[para_pos]
            else:
                parsed_list = [parse_paragraph(style, full_text)]

            for parsed in parsed_list:
                if level is not None and parsed.element_type == ElementType.BODY:
                    parsed = replace(parsed, element_type=ElementType.LIST_ITEM, number=str(level), spans=spans)
                else:
                    parsed = replace(parsed, spans=spans)
                yield parsed

            if _has_inline_image(block, crest_hashes, cover_region=_in_cover(block)):
                # Mixed text+image <w:p>: the text has just been emitted as its
                # own provision, so the FIGURE carries no text of its own and
                # the builder's text-retention guard stays inert (no duplicate).
                yield ParsedParagraph(
                    ElementType.FIGURE,
                    text="",
                    image_blobs=_figure_blobs(
                        block, crest_hashes, cover_region=_in_cover(block)
                    ),
                )

            para_pos += 1
        elif isinstance(block, Table):
            rows = [
                [_cell_text(cell).strip() for cell in row.cells]
                for row in block.rows
            ]
            yield ParsedParagraph(element_type=ElementType.TABLE, table_rows=rows)
