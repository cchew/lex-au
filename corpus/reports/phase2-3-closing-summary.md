# Phase 2 + 3 Closing Summary (2026-07-22)

## Phase 2 (doc-conversion stragglers)
- RTF detection: 2 Acts ingested via the new magic-byte branch
  (`australian-national-railways-commission-sale-act-1997`,
  `corporate-law-economic-reform-program-act-1999`) — 55 and 470 sections
  respectively, confirmed by direct XML parse (Task 1-2).
- 2026-07-13 ingestion residual: 5 of 9 already present, 4 re-fetched
  successfully, 0 still genuinely unresolved (Task 3).

## Phase 3 (doc-conversion quality verification)
- Structural pass: 130/130 clean — zero Acts with an empty `<section>`
  body among the doc-converted population (Task 4 Step 5; independently
  re-run in this task with `spot_check.py --only-source-format
  doc-converted`, same result: "Acts with zero `<section>` elements: 0 /
  130", 304 non-fatal metadata-gap failures across four known categories
  — `temporalData in meta`, `lifecycle in meta`, `date elements present`,
  `Subsections present` — none section-heading parse failures).
- Currency verification: closed — 18/18 sampled Acts (of 130) matched the
  live `isLatest eq true` compilation record via the legislation.gov.au
  API, 0 mismatches (Task 4, Step 7).
- Provenance: 130 Acts confirmed `source_format: doc-converted` in
  `corpus/index.json` (Task 5, Step 1) — matches the population size used
  throughout Tasks 4-5. (Corpus total: 3074 Acts.)

## Final gate check (Task 5, Step 2)
- `spot_check.py --corpus-dir corpus` (full corpus, 3074 Acts): 17 Acts
  with zero `<section>` elements — cross-checked byte-for-byte against
  `corpus/reports/legacy-residual-final-triage.md`'s documented Phase 1
  legacy-template residual list; zero overlap with the doc-converted-130
  set. 6213 total check failures corpus-wide, all in the same four known
  metadata-gap categories (no new failure types).
- `pytest tests/ -q`: 3424 passed (0 failed), matching the cumulative
  count expected from Tasks 1 and 4.

## Gate status
Met. Every Act in Phase 2's scope is either ingested (2 RTF Acts, 4
re-fetched residual Acts, 5 already-present residual Acts) or, for the
17 Phase-1 legacy-template Acts appearing in the corpus-wide spot_check,
documented with a specific reason (out of this plan's scope, tracked in
`corpus/reports/legacy-residual-final-triage.md`). Phase 3's gate is met:
spot_check is clean across all 130 doc-converted Acts (0 empty-body),
the currency question is closed (18/18 API matches, 0 mismatches), and
provenance is verified (130 Acts tagged `source_format: doc-converted`).
The full test suite passes (3424 tests, 0 failures). No genuinely new
failures were found in this final check beyond what Tasks 1-4 already
explained.
