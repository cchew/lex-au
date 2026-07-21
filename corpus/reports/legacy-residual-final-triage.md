# Legacy Residual — Final Triage (Phase 1, closed 2026-07-21)

Post-Task-2 (third-shape fix) + Task 3 (corpus rebuild) residual:
17 Acts still have an empty `<body>`, down from 135 at Phase 1 start.

## Composition

- `superannuation-industry-(supervision)-regulations-1994` — not a legacy
  document (has modern compiled-Regulation styles: `ShortT`, `CompiledActNo`,
  `MadeunderText`, `CompiledMadeUnder`); empty `<body>` has an unrelated root
  cause. Confirmed: this Regulation has no `-vol0.docx` at all — its docx set
  starts at `-vol1.docx` (2 volumes, `vol1`/`vol2`). Candidate theory: the
  crawler/parser assumes volume numbering always starts at `-vol0.docx` and
  silently produces an empty body when that assumption doesn't hold. Flagged
  for separate investigation, out of scope for this plan.
- 16 remaining Acts — genuine long-tail, one-off historical DOCX formats with
  no single addressable pattern. Full list in
  `corpus/reports/legacy-residual-post-phase1a-names.txt`.

## Step 1 spot-check findings

Hand-inspected 4 of the 16 long-tail Acts (one more than the brief's minimum
of 3, to strengthen confidence given the borderline stopping-rule threshold),
printing the first ~15 non-empty paragraphs' `(style, text)` pairs from each
`-vol0.docx`:

- `aboriginal-and-torres-strait-islander-commission-amendment-act-1996` —
  uses `Body text (12)`, `Body text (2)`, `Body text (4)`, `Body text (10)`,
  `Body text (6)`, `Body text (11)`, and `Body Text8` (no space) for its
  section body paragraphs. No `Heading 5` anywhere in the sampled range.
- `constitution-alteration-(senate-elections)-1906` — pre-Federation-era
  1907 amendment Act, uses a completely different style family:
  `0_Chapter title`, `Style3`, `0_Subtitle`, `Style5`, `Style6`, `Style7`,
  `0_1 list`, `0_2 list`. Shares nothing with either the `ActHead*` legacy
  shape or the other three sampled Acts.
- `customs-tariff-(miscellaneous-amendments)-act-1996` — uses
  `Body text (16)`, `Body text (2)`, `Body text (3)`, `Normal`,
  `Body text (4)`, `Body Text9` (no space), `Body text (13)`. Overlaps
  loosely with the ATSIC Act's numbering convention but uses different
  specific style names (`Body Text9` vs `Body Text8`; `Body text (16)` vs
  `Body text (12)`) — not a shared, machine-matchable style.
- `vocational-education-and-training-funding-laws-amendment-act-1996` —
  uses `Normal`, `Body text (2)`, `Body text (4)`, `Body text (5)`,
  `Body text (6)`, `Body text (7)`, `Body Text2` (no space). Again a
  distinct numbering from all three above.

**Assessment:** each Act carries its own ad hoc, per-document set of
numbered Word styles (`Body text (N)`, `Body TextN` with no space, or
entirely bespoke pre-Federation style names like `Style3`/`Style7`). These
are consistent with independent digitisation/export events over decades,
not a shared machine-detectable "third shape" the way `Heading 5` was.
No 3+ Acts among the sampled set share a common recognisable style name or
paragraph-numbering scheme. This confirms the plan's original characterisation
of the long tail as fragmented one-offs, not a second addressable pattern.

## Decision

Original long-tail estimate: ~16 Acts. Post-Task-3 residual: 16 genuine
long-tail Acts (unchanged — the Heading-5 fix in Task 2 targeted only the
118-Act third-shape group and correctly left the long tail untouched).

Per the spec's Phase 1b stopping rule: the rule triggers when post-Task-3
residual resolves fewer than half of the original ~16-Act long-tail estimate
(i.e. residual stays above ~8). Actual residual is 16 of 16 — 0% resolved,
well above the ~8-Act threshold.

**Decision: stop iterating.** Do not write bespoke per-Act parsing code for
the long tail. The Step 1 spot-check (4 Acts, not just the required 3) found
no shared addressable pattern — each Act uses its own ad hoc style set, which
is exactly the "no single addressable pattern" condition the stopping rule
anticipates. Document the 16 as a Known Limitation in `README.md`. The
17th Act (`superannuation-industry-(supervision)-regulations-1994`) is a
separate, non-legacy issue and is flagged as its own follow-up, not part of
this Known Limitation.

Phase 1 Gate check: residual (17) is under the ~15-20 target range from the
plan's Phase 1 Gate criterion, and every Act in it is individually documented
here and in the source name list. Phase 1 is closed.
