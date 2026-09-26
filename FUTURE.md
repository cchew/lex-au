# FUTURE

Known-but-deferred issues. Each entry states what is wrong, what is currently true in the corpus, and why it wasn't fixed at the time it was found. Created 2026-08-16 while landing the static-site FRBR path collision fix — earlier notes referenced a `FUTURE.md` that had never actually been committed, so anything dated before then was reconstructed from the design spec, not carried over.

## `frbr_work_uri` / `frbr_expression_uri` carry the same `(year, number)` collision the site paths just fixed

`ActMetadata.frbr_work_uri` and `frbr_expression_uri` (`src/lexau/models.py:20-35`) are built by `_cobalt_uri` from `doc_type` / `year` / `number` only. `Corpus.all_metadata()` (`src/lexau/corpus.py:58-73`) never restores `doc_type` — it isn't persisted in `corpus/index.json` at all — so every loaded Act falls back to the dataclass default `doc_type="act"`, collapsing the Act-vs-Regulation distinction that would otherwise separate some of these URIs.

Result: all three colliding pairs produce identical work URIs. Superannuation Industry (Supervision) Regulations 1994 and Training Guarantee (Administration) Amendment Act 1994 both emit `/akn/au/act/1994/57`, even though they now render at distinct site paths (`.../57-f1996b00580-ba01e2a0/` and `.../57-c2004a04733-f086ea4d/`). Same for `(1974, 41)` and `(1988, 86)`.

Deferred explicitly by the design spec's Non-goals (`docs/superpowers/specs/2026-08-16-site-frbr-path-collision-design.md` in the EA project wrapper, Non-goals, final bullet): the site fix derives its own paths at generate-time and never reads a stored FRBR URI, so the two are independent. This one is not: `act_frbr_uri` is the identifier lex-au-graph's MCP tools take as input, so the collision likely affects graph-side Act identity too, and a fix has to cross repos. Tracked as a known bug, not an identifier that has been confirmed safe.

## Two Acts are ingested twice — same composition, old and new title (RESOLVED v0.8.2)

Fixed 2026-08-21: `Crawler.fetch_metadata()` now returns the API's canonical name instead of the caller's raw query string (`src/lexau/crawler.py`), and `Corpus.save()` enforces `title_id` uniqueness at write time, merging into the existing entry and retaining the superseded name in a new `ActMetadata.aliases` field (`src/lexau/corpus.py`) instead of creating a duplicate. `scripts/dedupe_renamed_acts.py` collapsed the 2 known live pairs below, dropping the corpus to 3,076 entries and leaving `(1994, 57)` as the sole remaining genuine `(year, number)` collision (see the entry above). Full design: `docs/superpowers/specs/2026-08-21-duplicate-act-ingest-dedup-design.md` (EA project wrapper).

Original write-up, preserved for context:

Two pairs in the 3,078-Act corpus are the *same* legislative composition stored under two different Act names. Verified against `corpus/index.json` on 2026-08-16:

| Entry | `title_id` | `comp_id` | `comp_num` | Effective |
|---|---|---|---|---|
| Human Services (Medicare) Act 1973 | `C2004A00100` | `C2025C00609` | 51 | 2025-11-01 |
| Health Insurance Commission Act 1973 | `C2004A00100` | `C2025C00609` | 51 | 2025-11-01 |
| Fair Work (Registered Organisations) Act 2009 | `C2004A03679` | `C2024C00345` | 88 | 2024-08-23 |
| Workplace Relations Act 1996 | `C2004A03679` | `C2024C00345` | 88 | 2024-08-23 |

Every metadata field except `name` is identical within each pair, and the rendered pages differ only by title (83,156 vs 83,160 bytes for the first pair, in table order; 692,626 vs 692,592 for the second). The Health Insurance Commission Act 1973 was renamed to the Human Services (Medicare) Act 1973, and the Workplace Relations Act 1996 to the Fair Work (Registered Organisations) Act 2009 — legislation.gov.au serves one composition under the current title, and the crawler has captured both the superseded and current names as separate corpus entries.

So 2 of the 3 `(year, number)` "collisions" aren't distinct-Act collisions at all — they're duplicate ingests. This is a crawler/ingest defect, not a site defect; out of scope for the site fix, which touches `src/lexau/site.py` only. Fixing it means deciding whether a renamed Act should be one entry under its current title (with the old title as an alias) and then deduplicating on `(title_id, comp_id)` at ingest. Doing so would drop the corpus to 3,076 entries and leave `(1994, 57)` as the only genuine collision.

## 4 site URLs broke when the v0.8.2 dedup shrank their collision groups (accepted, not fixed)

Deduping the `(1974, 41)` and `(1988, 86)` collision groups from 2 members to 1 each moved the 2 survivors (Human Services (Medicare) Act 1973, Fair Work (Registered Organisations) Act 2009) from their old digest-suffixed paths back onto bare `(year, number)` paths — `_assign_site_paths` only suffixes a path when its collision group has more than 1 member. The 4 old suffixed URLs (2 per pair — each pre-dedup entry had its own suffix) now 404, with no redirect in place. They were live for roughly 5 days (since v0.8.1, 2026-08-16) before the v0.8.2 republish on 2026-08-21.

Decided 2026-08-21: accept the churn rather than add a Netlify `_redirects` file. `_instance_suffix`'s own docstring already treats a suffix changing when an Act's collision group membership changes as an expected trade-off of deriving paths purely from live corpus state at generate-time (see `src/lexau/site.py`) — this is the same trade-off, just the group shrinking rather than growing. Revisit if external links to the old suffixed paths turn out to matter in practice.

## `lexau site` is now always a full regeneration

`SiteGenerator.generate()` calls `shutil.rmtree(self._site_dir, ignore_errors=True)` before writing (added 2026-08-16), so the output directory only ever contains pages for Acts currently in the corpus — a stale page for a removed, renamed, or re-pathed Act can no longer survive a rebuild. The trade-off is that every invocation rewrites all 3,076 Act pages and their `source.xml` copies; there is no incremental mode. Fine at the current corpus size (tens of seconds), worth revisiting if the corpus grows by an order of magnitude or the site build lands in CI on every corpus update.

## Schedule clause eIds collide — mostly `_CLAUSE_RE` false positives, not lost Part/Division grouping (corrected 2026-09-26)

Found 2026-09-05 while implementing eId-collision disambiguation in lex-au-explorer (`docs/superpowers/sdd/2026-09-04-schedule-and-figure-rendering/task-4-report.md` in the EA project wrapper). Original write-up here claimed the converter "flattens schedule Part/Division numbering" and drops "the source AKN's `<part>`/`<division>` grouping" — both framings are wrong: there is no source AKN (the source is DOCX), and that grouping never existed in the converter's output to be dropped.

Corpus-wide investigation (P1, `docs/superpowers/notes/2026-09-07-p1-schedule-structure.md` in the EA project wrapper, phase 1 of the v0.3.1 word-for-word checkpoint) replayed the real builder logic across all 385 affected Acts / 497 schedules / 2,831 colliding eIds and found the actual mechanism: **~98.7% (point estimate; band ≥92%) is `_CLAUSE_RE` / SECTION-branch false-positive fabrication** — `_build_schedule_content` promotes amendment-instruction items, embedded schedule TOC lines, and section headings inside un-wrapped quoted/inserted replacement provisions into the same flat `schedule-N__clause-<num>` namespace, because `_preprocess_quoted_structures` only runs on `body_paras` (`builder.py:930`), never on schedule groups. Genuine Part/Division boundary loss (the mechanism this entry originally named) accounts for only **~1.2% of collisions (33 of 2,831 eIds by point estimate, ≤~7%/≈200 as a hard ceiling)** — an independent instruction-reset scan finds just 8 genuine Part/Division reset events corpus-wide.

Confirmed example (kept from the original write-up; it is genuine but small): `a-new-tax-system-(family-assistance)-act-1999.xml`, `schedule-1` (107 direct clauses) has one collision — `eId="schedule-1__clause-30"` at document positions 63 ("Standard rate") and 96 (a definitions clause reached via a `_CLAUSE_RE` date-fragment false positive, not a Part/Division boundary).

**Fixed (B4, commits `b88624a..c71da41`, folded into the full corpus re-convert at `78ea173`):** `_build_schedule_content` now runs quoted-structure preprocessing over schedule groups, wraps amendment-instruction items as their own container instead of the literal instruction number, and skips schedule-TOC-styled paragraphs — collapsing the ~98.7% false-positive share. This is already live in every file under `corpus/xml/` on `main` (`78ea173` is an ancestor of `434a672`, verified via `git merge-base --is-ancestor`). Only the package version string (`pyproject.toml`, still `0.9.3`) and the `v0.10.0` git tag/release remain pending — that's Task 20, a human-gated version-numbering formality, not a code/data gap. lex-au-explorer's `build/bundle.py` `_schedule_units`/`build_toc` still need updating to walk the new nesting this fix produces — that work (Task 22) is unblocked and can start against the current corpus today; its `~N` eId-disambiguation workaround is now largely redundant (harmless to leave in place until Task 22 lands). See the P1 note's "Fix-set recommendation" (B4) for the full mechanism table; the dataset CHANGELOG note ("schedule clause eIds renumbered in v0.10.0; see B4") is applied to the published Hugging Face dataset card whenever `export-hf` next runs.

## Fidelity audit can't distinguish genuine content loss from table-segmentation noise

`scripts/audit_conversion_fidelity.py` / `src/lexau/fidelity.py`'s `drop_text`, `drop_para` and `spurious_para` metrics (98,073 / 12,942 / 58,467 paragraphs respectively as of the v0.10.0 corpus, across 2,791 of 3,084 Acts with at least one non-minor divergence) are explicitly documented in the audit's own `SUMMARY.md` caveat as unreliable as a loss count — they blend genuine content loss with (1) DOCX-paragraph-vs-AKN-`<td>`/`<th>`-cell segmentation mismatches for table content, and (2) AKN front-matter/per-volume text repeated as spurious paragraphs, "in unknown proportion."

Root cause (not a fundamental limitation): `akn_paragraphs()` (`scripts/audit_conversion_fidelity.py`) already distinguishes fine units (`<p>`/`<heading>`) from cell-ish units (`<td>`/`<th>`/`<block>`) to decide what to collect, but flattens both into a plain `list[str]` before handing them to `fidelity.compare()` — the origin tag is computed and then discarded. `compare()` never sees which paragraph came from a table cell vs body prose, so the three metrics can't be split by context.

Two ways to close this, scoped 2026-09-26:
- **Full computed split (effort M):** thread an origin tag (table-context vs body-context) through `docx_paragraphs()`/`akn_paragraphs()` and `Divergence`, then split the aggregate counters and `SUMMARY.md` rendering by that tag. The DOCX side needs new logic (no `<w:tbl>` ancestor-walk exists yet on that side); the AKN side is plumbing over data already computed and thrown away. Main cost is a corpus-wide 3,084-Act re-run to regenerate trustworthy numbers, not the code itself.
- **Sampling script (effort S):** a standalone, read-only script over data already on disk — pick N Acts from the existing worst-20/worst-drop-count ranking, load each Act's already-generated per-Act JSON (full before/after `docx_text`/`akn_text` per divergence), and heuristically classify each `drop_para`/`spurious_para`/`drop_text` entry as table-adjacent vs prose. No changes to `fidelity.py`/`audit_conversion_fidelity.py` needed; gives a confidence bound rather than an exact split, but at near-zero cost.

Neither has been started. Recommend the sampling script first — it would show whether the residual divergence is mostly noise or worth the M-effort real fix, before committing to that larger change.
