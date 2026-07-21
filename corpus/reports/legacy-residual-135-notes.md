# Legacy Residual — 135-Act Split (re-derived 2026-07-21, supersedes legacy-shape-discovery-notes.md)

`legacy-shape-discovery-notes.md` (written 2026-07-18) said "No third shape
was discovered" against the then-current 550-Act population. That was true
at the time — the third shape only became visible in the *residual* left
after the 2026-07-18 plan's two fixes shipped. This file documents that
residual's real split, replacing the stale 58/71 estimate carried in the
2026-07-21 spec.

## Split (against corpus/reports/legacy-residual-135-names.txt, 135 Acts)

- **Phase 1a candidates (style-driven third shape):** 118 Acts with at least one
  `Heading 5`-styled paragraph in their DOCX. A `Heading 5` paragraph carries
  the section number and heading on one line (`"1  Short title"`) — the same
  text shape `_SECTION_RE` already recognises for the ActHead-styled
  non-legacy path, just without an `ActHead*` style gate. Confirmed against
  three real fixtures: `agricultural-and-veterinary-chemical-products-levy-
  imposition-(customs)-act-1994`, `northern-territory-(commonwealth-lands)-
  act-1980`, `loan-(war-service-land-settlement)-act-1970`.
- **Phase 1b long tail:** 16 Acts with no `Heading 5` style anywhere — all in
  "Body Text N"-only style-signature clusters, no single addressable shape.
- **Non-legacy outlier:** `superannuation-industry-(supervision)-
  regulations-1994` — has no `-vol0.docx` file (starts at `-vol1.docx`), so it's
  not confirmed as legacy or non-legacy via discover_legacy_shapes.py; included
  in the 135-Act empty-`<body>` population but its empty body has an unrelated
  cause and is explicitly out of scope for this plan (see Task 4).

Total: 118 + 16 + 1 = 135

## Caveat

`discover_legacy_shapes.py` only opens each Act's `-vol0.docx`. Any Act whose
DOCX starts at `-vol1.docx` (no vol0) silently drops out of its
`total_legacy_acts` count — this is why that script reported 134 against
`spot_check.py`'s 135 on 2026-07-21. Not fixed in this plan (out of scope,
single known instance); flagged here so a future re-run isn't surprised by
the same off-by-one.
