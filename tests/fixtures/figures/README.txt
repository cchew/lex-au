Figure fixtures for tests/test_figures.py
=========================================

one_png.docx
  Synthetic. Built with python-docx:
      d = Document()
      d.add_paragraph("Figure fixture: one inline PNG.")
      d.add_picture(BytesIO(_PNG_1x1))   # 1x1 opaque PNG, 67 bytes
  One FIGURE paragraph, one inline raster PNG (a:blip -> image1.png).

one_wmf.docx
  Real corpus blob. Extracted from
      corpus/docx/income-tax-assessment-act-1997-c266-vol1.docx
  Body paragraph index 565 (python-docx doc.paragraphs order), whose run holds
  a single a:blip -> r:embed -> /word/media/image2.wmf (10354-byte WMF).
  Rebuilt as a minimal .docx: the source <w:document> element (all namespace
  decls kept) with its <w:body> reduced to that one <w:p> plus the source
  <w:sectPr>; a fresh [Content_Types].xml / _rels/.rels /
  word/_rels/document.xml.rels carrying only the one image relationship; the
  image2.wmf blob copied verbatim into word/media/.

one_emf.docx
  Real corpus blob. Same source Act and same extraction method as one_wmf.docx,
  body paragraph index 675, a:blip -> /word/media/image3.emf (33172-byte EMF).

Extraction / rebuild was done with lxml (deep-copy the document root, swap the
body). No LibreOffice involved in fixture creation. soffice IS present on the
build machine, so test_vector_converted_when_soffice_present runs (not skipped)
and really rasterises both blobs to PNG.
