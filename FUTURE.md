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
