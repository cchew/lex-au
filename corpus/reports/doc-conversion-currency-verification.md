# Doc-Conversion Currency Verification (Phase 3, closed 2026-07-22)

Sampled 18 of 130 `.doc`-converted Acts (evenly spaced, step 7), cross-checked
local `comp_num` against the live `isLatest eq true` Versions endpoint at
`https://api.prod.legislation.gov.au/v1`.

Note: the population is 130, not the plan's stated 124 — 124 original +
2 RTF Acts (Task 2) + 4 residual Acts (Task 3), some of which also turned
out to be `.doc`-format.

Result: all OK. 18/18 sampled Acts match the live `isLatest` compilation
record. Several sampled Acts show `local=None live=None` — these are
legitimate original-compilation Acts (no numbered compilation series);
confirmed genuine matches (not a null-vs-null false positive) by checking
that `registerId`/`comp_id` also agree between local and live records
(e.g. `flags-act-1953`: local `comp_id=C2008C00376`, live
`registerId=C2008C00376`).

The Parliamentary Papers Act 1908 concern raised in
`corpus/reports/doc-conversion-spotcheck.md` (1981-dated compilation) is
closed as a legitimate old compilation — the `isLatest eq true` filter in
`crawler.py`'s `fetch_metadata` works correctly by construction, as
confirmed by this broader sample showing no mismatches.

## Sample detail

| Result | Act | local comp_num | live comp_num |
|---|---|---|---|
| OK | a-new-tax-system-(family-assistance-and-related-measures)-act-2000 | 2 | 2 |
| OK | a-new-tax-system-(goods-and-services-tax-imposition—general)-act-1999 | None | None |
| OK | a-new-tax-system-(wine-equalisation-tax-imposition—excise)-act-1999 | 0 | 0 |
| OK | anti-terrorism-act-(no.-2)-2004 | 0 | 0 |
| OK | australian-passports-(application-fees)-act-2005 | 0 | 0 |
| OK | coastal-waters-(northern-territory-powers)-act-1980 | None | None |
| OK | commonwealth-places-windfall-tax-(imposition)-act-1998 | 0 | 0 |
| OK | fairer-private-health-insurance-incentives-(medicare-levy-surcharge)-act-2012 | 0 | 0 |
| OK | flags-act-1953 | None | None |
| OK | heard-island-and-mcdonald-islands-act-1953 | None | None |
| OK | jurisdiction-of-courts-(family-law)-act-2006 | 0 | 0 |
| OK | migration-(sponsorship-fees)-act-2007 | 0 | 0 |
| OK | northern-territory-acceptance-act-1910 | None | None |
| OK | petroleum-resource-rent-tax-(imposition—customs)-act-2012 | 0 | 0 |
| OK | protection-of-the-sea-(imposition-of-contributions-to-oil-pollution-compensation-funds—customs)-act-1993 | None | None |
| OK | seat-of-government-acceptance-act-1909 | None | None |
| OK | superannuation-contributions-tax-(application-to-the-commonwealth)-act-1997 | 2 | 2 |
| OK | us-free-trade-agreement-implementation-(customs-tariff)-act-2004 | 0 | 0 |

18/18 OK, 0 mismatches. Currency concern closed. Phase 4 (publish) is not
blocked by this check.

## Structural pass (Step 5)

`python scripts/spot_check.py --only-source-format doc-converted` against
the full 130-Act population: header "Checking 130 Acts", "Acts with zero
`<section>` elements: 0 / 130".

304 non-fatal check failures across the 130 Acts, all in four categories:
`temporalData in meta` (130), `lifecycle in meta` (130), `date elements
present` (29), `Subsections present` (15). These are pre-existing v0.5/v0.2
schema-generation gaps present corpus-wide (confirmed against the full
3074-Act corpus: same categories, 6213 failures, 17/3074 zero-section
Acts — none in the doc-converted-130 subset). None are section-heading
parse failures of the kind Task 2's RTF style-name bug produced (that bug
manifested as zero `<section>` elements, which this population does not
have). No new style-name variant bug found in this population.
