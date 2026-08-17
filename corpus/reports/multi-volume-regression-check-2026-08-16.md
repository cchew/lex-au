# Multi-Volume Regression Check (2026-08-16)

Primary fix: Superannuation Industry (Supervision) Regulations 1994,
**447** body sections (target: 447). Confirmed via `lexau build --acts
"Superannuation Industry (Supervision) Regulations 1994" --type regulation
--corpus-dir corpus --force` followed by the section-count script in the
task brief. Exact match to target.

## 37-Act regression check

Live count of multi-volume Acts (`ls corpus/docx/*-vol1.docx`, deduped for
a stray pre-existing duplicate cache artifact — see Notes) is **37**,
unchanged from the spec's last verification. All 37 were rebuilt with
`lexau build --acts "<name>" --type <act|regulation> --corpus-dir corpus
--force` (regulation type used for the 4 Acts whose `comp_id` has an `F`
prefix: Civil Aviation Safety Regulations 1998, Corporations Regulations
2001, Migration Regulations 1994, Superannuation Industry (Supervision)
Regulations 1994). No errors or tracebacks in the rebuild log.

**Note on git-tracking**: `corpus/` is entirely `.gitignore`d (not
git-tracked at all — `git show HEAD:corpus/index.json` fails with "exists
on disk, but not in HEAD"), so the brief's `git diff --stat corpus/xml/` /
`git show HEAD:corpus/index.json` recovery method for the pre-rebuild
state does not apply here. Instead, section counts and `comp_num` values
for all 37 Acts were captured from the live corpus files immediately
before Step 2's rebuild ran, and diffed against the post-rebuild state.

### 19 Acts with a section-count and/or comp_num change

| Act | Sections (pre → post) | comp_num (pre → post) |
|---|---|---|
| A New Tax System (Family Assistance) (Administration) Act 1999 | 489 → 489 | 130 → 131 |
| Australian Securities and Investments Commission Act 2001 | 555 → 574 | 106 → 108 |
| Competition and Consumer Act 2010 | 1647 → 1648 | 164 → 165 |
| Corporations Act 2001 | 4160 → 4174 | 145 → 147 |
| Customs Tariff Act 1995 | 57 → 58 | 98 → 99 |
| Environment Protection and Biodiversity Conservation Act 1999 (**fixture**) | 1103 → 1104 | 69 → 69 (index.json) |
| Fair Work Act 2009 | 1498 → 1501 | 71 → 73 |
| Fringe Benefits Tax Assessment Act 1986 | 294 → 294 | 96 → 97 |
| Health Insurance Act 1973 | 496 → 499 | 133 → 135 |
| Income Tax Assessment Act 1936 | 764 → 764 | 191 → 192 |
| Income Tax Assessment Act 1997 (**fixture**) | 4639 → 4649 | 265 → 266 |
| Migration Regulations 1994 | 397 → 397 | 287 → 288 |
| National Consumer Credit Protection Act 2009 | 543 → 523 | 50 → 52 |
| Social Security Act 1991 | 1473 → 1473 | 231 → 232 |
| Superannuation Act 1976 | 365 → 365 | 66 → 67 |
| Superannuation Industry (Supervision) Act 1993 | 644 → 645 | 129 → 131 |
| Taxation Administration Act 1953 | 200 → 200 | 223 → 225 |
| Veterans' Entitlements Act 1986 (**fixture**) | 1015 → 914 | 199 → 199 (index.json) |
| Water Act 2007 | 470 → 494 | 36 → 37 |

Remaining 18 of 37 multi-volume Acts: unchanged sections and unchanged
`comp_num`.

### Named fixtures: PASS

**Income Tax Assessment Act 1997** — `comp_num` in `corpus/index.json`
changed (265 → 266), which per the Global Constraints directly explains
the +10 section change as a genuine legislative recompilation. Sanity
check: the pre-rebuild cached DOCX's own embedded "Compilation No." text
read **264** (not 265 — the index.json metadata was already one
compilation ahead of the cached DOCX content), and the freshly rebuilt
DOCX reads **266**, consistent with the corpus catching up across two real
recompilations between the stale cache and today. PASS.

**Environment Protection and Biodiversity Conservation Act 1999** and
**Veterans' Entitlements Act 1986** both showed `comp_num` reported as
*unchanged* in `corpus/index.json` (69→69 and 199→199 respectively) while
their section counts moved (EPBC +1, VEA −101). Per the Global Constraints
this is the hard-stop condition on its face, so before treating it as a
regression I opened both the old (stale) cached DOCX files and the
freshly-rebuilt ones and read the "Compilation No." text embedded on each
DOCX's own title page (ground truth, independent of `index.json`):

- EPBC 1999: old cached DOCX (all 3 volumes) reads **Compilation No. 68**;
  freshly rebuilt DOCX reads **Compilation No. 69**, matching the current
  `comp_num`.
- VEA 1986: old cached DOCX (all 4 volumes) reads **Compilation No. 198**;
  freshly rebuilt DOCX reads **Compilation No. 199**, matching the current
  `comp_num`.

Root cause: this repo has an old convention where cached DOCX files were
named without the `comp_num` suffix (`{safe_name}-vol{N}.docx`), and
`fetch_docx_volumes`'s exists-check now looks for
`{safe_name}-c{comp_num}-vol{N}.docx` (a pre-existing fix, unrelated to
this plan, guarded by a code comment in `crawler.py` explaining exactly
this class of bug: "a docx cached from an earlier compilation collides
with a later one on disk and this exists-check silently serves the stale
bytes under new metadata"). For these two Acts, the old-style DOCX files on
disk had never been re-fetched since that fix landed, so they held content
from the *previous* compilation (68/198) even though `corpus/index.json`
had already been refreshed to reflect the newer metadata (69/199) from an
earlier, metadata-only build. This --force rebuild fetched the correct,
current-compilation DOCX content for the first time, which is why the
section counts moved. This is a genuine legislative recompilation
correctly reflected for the first time — not a Task 1 code regression.
It is a real, pre-existing corpus-hygiene issue independent of this plan,
worth a follow-up ticket to audit the corpus for other Acts still on the
old-style stale cache filenames, but out of scope for this task.

**Verdict: PASS for all 3 named fixtures** — every section-count change is
fully explained by a genuine legislative recompilation, verified against
DOCX-embedded ground truth, not just `index.json`'s (sometimes-lagging)
`comp_num` field.

None of the 19 changed Acts show a section-count change with an
unexplained (non-recompilation) cause. `National Consumer Credit
Protection Act 2009` had the largest non-fixture drop (543 → 523, −20
sections) alongside a 2-step `comp_num` bump (50 → 52); not a named
fixture so it doesn't trigger the hard-stop, and a 2-step recompilation
plausibly explains a 20-section change for an Act of this size.

## Residual edge case (schedule spanning a volume boundary)

Ran the brief's Step 4 scan against the final post-rebuild `corpus/docx/`
state (74 `*-vol1.docx` files — 37 unique Acts, each present as both the
old-style and new `comp_num`-suffixed cache copy). **Zero Acts flagged.**
No volume-1 DOCX opens with clause-shaped text lacking an `ActHead*`
style. The residual edge case (a schedule spanning a volume boundary with
no repeated "Schedule N" heading at the next volume's start) remains
theoretical, not observed in the current corpus.

## Change-2 decision

**Decision: STOP here. Do not proceed to Task 3. Document the preface
over-capture as a Known Limitation.**

Inspected `corpus/xml/superannuation-industry-(supervision)-regulations-
1994.xml`'s `<preface>` element directly: it contains 52 `<p>` elements.
The first 26 (indices 0–25) are genuine preface content — title,
Statutory Rules number, enabling Act, compilation number/date, the
standard "About this compilation" boilerplate (compilation summary,
uncommenced amendments, application/saving/transitional provisions,
editorial changes, presentational changes, modifications, self-repealing
provisions). This is correctly-classified preface material.

Paragraph 26 onward is a **Table of Contents index** for the DOCX's
front matter: "Contents" (index 26), followed by 20 entries (indices
27–46) each of the form `Schedule N—<title>\t<page>` or
`Part N—<title>\t<page>` — one line per Schedule/Part with its printed
page number — and finally 5 more ToC entries for the Endnotes (indices
47–51: "Endnotes", "Endnote 1—About the endnotes", etc.).

This is exactly the class of content the spec's Background section 2
describes: the 20 Schedule/Part ToC lines match the `_is_schedule_heading`
pattern used by the volume-0 preface-cut logic
(`min(first_structural, first_schedule)`), pulling the whole ToC block
into `<preface>` because it sits before the first real Part/Division/
Section heading in volume 1.

**Is it load-bearing?** No. Cross-checked the actual schedule content:
all 12 `<attachment>` elements (the AKN structure this codebase uses for
schedules) are present and populated with real substantive content
(1 to 277 `<p>` elements each, matching the parse report's "Sched: 12"
count), with correct headings ("AAA—Approved auditors—professional
organisations", "Pension valuation factors", etc.). The preface's 21
schedule/part-shaped lines are pure title-plus-page-number index entries
— duplicative of the real headings that correctly appear on their own
`<attachment>` elements elsewhere in the document. No legal substance
(no clause text, no numbers, no cross-references) is lost, misplaced, or
duplicated into the wrong structural position. The over-capture is
cosmetic: a ToC index sitting in `<preface>` instead of being dropped
entirely (this codebase doesn't model a `<toc>` element, so the ToC lines
have to land somewhere pre-body regardless of which fix is applied).

Per the spec's stated recommendation ("change 2 is only built if change 1
alone leaves SIS Regs 1994 with a materially incomplete result"): change 1
(Task 1) already delivers the exact target outcome — 447 body sections,
zero regressions across the 37-Act corpus, all 12 schedules fully and
correctly populated. The only residual defect is 21 cosmetic ToC lines
sitting in `<preface>` instead of being excluded — no legal content is
missing, duplicated, or misclassified into the wrong document part.
Task 3's riskier leading-Schedule preface-cut change is not warranted by
this evidence.

## Known Limitation (recorded per the above decision)

SIS Regs 1994's `<preface>` (and, by the same code path, any single- or
multi-volume Act whose volume-1 DOCX contains a Schedule/Part-shaped
Table-of-Contents block before the first real structural heading) may
retain that ToC block's title+page-number lines inside `<preface>` rather
than excluding them. This is cosmetic only — it does not affect body
section counts, does not omit or duplicate any legal content, and no
instance of it caused a body-section-count discrepancy across the 37-Act
regression check in this report.

## Full test suite

`python3 -m pytest -q` → **3449 passed** (Task 1's ending baseline,
unchanged — no source code was modified in this task).
