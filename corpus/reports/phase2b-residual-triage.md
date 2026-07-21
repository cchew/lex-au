# Phase 2b Residual Triage (closed 2026-07-21)

The spec's cited "9 conversion exceptions" was actually a mis-attributed
figure — re-derivation against `corpus/reports/ingest-remaining-20260713.log`
found the real source: 9 `ERROR --` lines (grep `"^ERROR --"`), all
transient network failures during the 2026-07-13 ingestion run, unrelated
to the `.doc`-population `.doc` classification.

## The 9, and their status as of 2026-07-21

Already present in the corpus (picked up by a later run):
- Broadcasting Legislation Amendment (Primary Television Broadcasting Service) Act 2015
- Broadcasting Legislation Amendment Act 1988
- Broadcasting Services (Transitional Provisions and Consequential Amendments) Act 1992
- Customs Amendment (Australia-United Arab Emirates Comprehensive Economic Partnership Agreement Implementation) Act 2025
- Early Childhood Education and Care (Strengthening Regulation of Early Education) Act 2025

Re-fetched by this task: all 4 were still missing at Step 1 re-confirmation,
and all 4 fetched cleanly (`saved ->`) on the first attempt — no retries
needed.

- Broadcasting Legislation Amendment Act (No. 1) 2003 — saved,
  `xml/broadcasting-legislation-amendment-act-(no.-1)-2003.xml`.
  Parse report: 1 schedule, 12 clauses. 3 `<section>` elements
  (Short title / Commencement / Schedule(s)), 0 `<subsection>` elements —
  expected for a short amendment Act whose substantive changes live in the
  Schedule, not the body.
- Broadcasting Legislation Amendment Act 2001 — saved,
  `xml/broadcasting-legislation-amendment-act-2001.xml`.
  Parse report: 3 schedules, 22 clauses. Same 3-section /
  0-subsection body structure as above, same explanation.
- Broadcasting Services Amendment (Digital Television and Datacasting) Act
  2000 — saved,
  `xml/broadcasting-services-amendment-(digital-television-and-datacasting)-act-2000.xml`.
  Parse report: 4 schedules, 358 clauses, 5 subsections, 78 refs. Largest
  of the 4; substantive body content present.
- Tax Laws Amendment (Medicare Levy and Medicare Levy Surcharge) Act 2009 —
  saved,
  `xml/tax-laws-amendment-(medicare-levy-and-medicare-levy-surcharge)-act-2009.xml`.
  Parse report: 1 schedule, 13 clauses. Same 3-section / 0-subsection
  body structure, same explanation.

Post-fetch verification (`scripts/spot_check.py --corpus-dir corpus`):
corpus total is 3074 Acts, up from 3070 before this task. None of the 4
appear in the "Acts with zero `<section>` elements" list (17/3074, all
pre-existing and unrelated). Three of the 4 (all except the Digital
Television Act) fail the script's `[Subsections present]` check with
`got []` — confirmed by direct XML inspection to be a real, benign
structural pattern (amendment Acts whose only body sections are Short
title / Commencement / Schedule(s), with the substantive amendments
carried in the Schedule's `<clause>` elements instead), not an empty-body
defect. The same pattern already exists in 253 other Acts across the
corpus prior to this task, so it is not something this task introduced.
All 4 also carry the corpus-wide, pre-existing, unrelated
`[lifecycle in meta]` / `[temporalData in meta]` gap.

## Gate

All 9 are now accounted for: 5 were already present from an earlier run,
and the remaining 4 have been fetched and structurally verified in this
task. No genuine residual failures remain from the 2026-07-13 `ERROR --`
list.
