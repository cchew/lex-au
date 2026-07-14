# List-Form Definition Truncation — Cross-Repo Design

**Goal:** Fix truncated `<def>` content for list-form definitions across the AU Legislative Intelligence Stack, and fix `lex-au-graph`'s separate term-eid collision bug (the already-scoped "node_id MVP"), so term-comparison and any future stack consumer sees complete, correct definitions rather than colon-terminated fragments or silently-overwritten meanings.

**Architecture:** Two independent fixes, one shared corpus rebuild:
1. `lex-au` — complete `<def>` text at corpus-build time. Detect a colon-terminated definiens, walk forward through sibling AKN elements to find the orphaned list content, and fold it into `<def>` — stopping precisely at the next term's definition boundary (see "The naive fix doesn't work" below; this boundary condition is the real design problem here, not the detection itself).
2. `lex-au-graph` — node_id occurrence-counter disambiguation (independent of #1, can be built in parallel), plus a rebuild against the corrected corpus.

Downstream: `lex-au-search` re-ingest, `term-comparison` deploy + regression check.

**Tech stack:** Python 3.12, lxml — both repos already use this. No new dependencies.

**Repos in scope:** `lex-au`, `lex-au-graph`, `lex-au-search`, `term-comparison`.

---

## Background / Root Cause

`lex-au`'s `termlinks.py::_process_p()` matches "X means Y" (and its relational/`has the meaning given by` variants) against a single `<p>` element's flattened text only. When an Act's real structure is a colon lead-in followed by a paragraph list —

```xml
<paragraph>
  <content><p>related entity means any of the following:</p></content>
</paragraph>
<paragraph eId="...para-a"><content><p>a relative of the person;</p></content></paragraph>
<paragraph eId="...para-b"><content><p>a body corporate of which...</p></content></paragraph>
```

— `_process_p` sees only the first `<p>`'s text, matches it as a **complete** "X means Y" pair, and injects `<def>any of the following:</def>` — syntactically valid, semantically truncated. The actual list content is structurally invisible to the function; it never looks past the current `<p>`.

`lex-au-graph`'s `loader.py::_extract_defined_terms` then faithfully extracts exactly the truncated fragment it's given (`"".join(def_el.itertext()).strip()`, no forward walk).

Confirmed directly against corpus XML (`bankruptcy-act-1966.xml`, `age-discrimination-act-2004.xml`, `copyright-act-1968.xml`, others).

## Confirmed Scale (verified against live 2,944-file corpus, 2026-07-14, post-ingestion)

| Metric | Count |
|---|---|
| Files in corpus | 2,944 |
| Files with any `<term refersTo>` tagging | 806 (the other 2,138 are 84% amendment/repeal/statute-law-revision Acts with no Dictionary content of their own — expected, out of scope) |
| Colon-terminated `<def>` fragments (`def_el.itertext()` ends in `:`) | 3,139 |
| — of which have a genuine following list at *some* ancestor level (real fix target) | **3,136** |
| — of which qualify at the immediate `<content>` sibling level (level 0) | 487 |
| — of which require walking up one more level to the enclosing `<paragraph>`'s siblings (level 1) | **2,649** — the majority shape, not the minority |
| — genuinely no following list at any level (leave as-is, not a bug) | 3 |
| `<term>` with no `<def>` at all (separate, already-correctly-structured `inject_list_defs` output, invisible to the graph's XPath) | 168 — **out of scope**, see below |
| Term-eid collisions (raw, same eid 2+ times in one Act) | 746, across 107 Acts (up from 65 previously-verified pairs, pre-ingestion) |

The level-0/level-1 split matters: `inject_list_defs`'s existing sibling-detection code only checks level 0. Reusing it as-is would silently miss 85% of real cases (2,649 of 3,136).

## Design — `lex-au` (`termlinks.py`)

### The naive fix doesn't work

The obvious approach — walk forward from the `<content>` wrapping the truncated `<p>`, collect all following `<paragraph>`/`<blockList>` siblings, stop at the first non-list sibling — fails on real data. Confirmed case, `bankruptcy-act-1966.xml`, `related-entity` definition: after 9 list items (`para-a` through `para-i`), `para-i`'s `<paragraph>` element contains **two** `<content>` children — the last list item ("a member of a partnership...") **and** the start of the *next* term's definition (`<p><b><i>relative</i></b>, in relation to a person, means:</p>`), followed immediately by **more** `<paragraph>` siblings reusing the exact same eId suffixes (`para-a`, `para-b`, ...) for `relative`'s own list. This is not a one-off: the same shape recurs in `copyright-act-1968.xml` (`collective-work`'s last list paragraph carries a second `<content>` starting `deliver`'s definition).

This is an existing corpus/DOCX-parsing artifact — `builder.py` attaches a trailing definitional paragraph to the nearest preceding numbered paragraph when it has no list marker of its own, rather than giving it a fresh paragraph. It predates this fix and isn't itself being changed here.

A boundary rule of "stop at the first non-paragraph/blockList sibling" would swallow `relative`'s entire list into `related entity`'s `definition_text`. A boundary rule of "stop at the first sibling `<paragraph>`" is also wrong, because the next term can start **mid-paragraph**, as a second `<content>` inside the same `<paragraph>` as the last real list item.

### Correct design: term-boundary-aware forward walk

Two-part algorithm, both parts required:

1. **Qualifying-level walk-up** (find where the list actually lives): starting from the truncated `<p>`'s `<content>` parent, check its immediate following siblings for a `<paragraph>`/`<blockList>`. If none, walk up to the parent's parent and repeat, capped at the enclosing `<section>` boundary. Use the first level where a following list element is found. (This matches the verified level-0/level-1 split above — a level-2+ case has not been observed in the corpus but the walk isn't artificially capped at 1.)

2. **Term-boundary-aware collection** (find where the list ends): walk forward through the siblings found in step 1, in document order. For each sibling `<paragraph>`, inspect its `<content>` children in order — not just the paragraph as a whole. Append each `<content>`'s rendered text (preserving nested inline markup — `<ref>`, `<i>`, etc. — by copying child nodes, not flattening to a string) to the accumulated `<def>` content, **until** a `<content>` is found whose `<p>` contains a `<term refersTo>` element. Stop there, excluding that `<content>` and everything after — it's the start of the next definition, not more list content for this one.

Result: `_inject()`'s `definiens` argument becomes the lead-in text plus the collected, boundary-respecting list content, and `<def>` is built the same way it is today (no new element nesting, no AKN schema question — this was considered and rejected: nesting a `<blockList>` inside `<def>` has an open, unresolved schema-validity question from v0.6.0, and the term-boundary problem above would apply to that shape too, just with more structural complexity to get wrong). `<def>` already carries nested inline elements elsewhere in the corpus today (e.g. `<ref>` in `Commissioner`'s definition in `age-discrimination-act-2004.xml`), so this is consistent with existing usage, not a new pattern.

**Test fixture:** the `related-entity` → `relative` back-to-back pair in `bankruptcy-act-1966.xml` is a ready-made regression case — any implementation must correctly bound `related-entity`'s definition_text to its 9 list items and correctly start fresh for `relative`, despite the reused `para-a`...`para-i` eId suffixes across both.

**Out of scope for this fix, noted but not touched:** the reused-eId-suffix pattern itself (same `paragraph eId` value appearing twice within one section, for two different terms' lists) is a pre-existing corpus quality issue, independent of this bug. Not actioned here.

## Design — `lex-au-graph`

### node_id MVP (independent fix, already scoped 2026-07-13)

`_add_act_nodes()` (`graph.py:68`) calls `self.graph.add_node(term.node_id, ...)` per extracted definition; `DefinedTermNode.node_id` (`models.py:37`) has no occurrence disambiguator, so same-Act same-slug definitions silently overwrite each other — only the last-processed survives. Fix: give `node_id` an occurrence counter computed during `_add_act_nodes`'s iteration. `find_all_definitions()` (what term-comparison's `/definitions` endpoint actually calls) already returns one result per surviving node — no term-comparison schema change needed.

### Rebuild

Once `lex-au`'s fix ships and the corpus rebuilds, `_extract_defined_terms`'s existing XPath (`.//p[term][def]`) needs no change — it already takes whatever `<def>` contains via `itertext()`. The fix is fully upstream; this repo only needs a rebuild + verification pass.

**Verification targets:**
- Sample of the 3,136 previously-truncated defs now return complete text (spot-check against the `related-entity`/`relative` pair specifically, since it's the hardest case)
- 746 raw collision candidates: after the node_id fix, each genuinely-different-meaning pair returns >1 result from `find_all_definitions`

## Design — `lex-au-search`

Re-ingest required — chunk content changes (longer, complete definitions). Pure pipeline re-run, no code change. Depends on `lex-au`'s corpus rebuild shipping first; can run in parallel with `lex-au-graph`'s rebuild.

## Design — `term-comparison`

No schema change expected — `DefinitionOut`/`ComparisonResponse` are already list-shaped and occurrence-scoped (confirmed 2026-07-12). Deploy + regression check: definitions are now materially longer and some terms will show multiple meanings per Act for the first time (node_id fix). Worth confirming card layout/truncation UI holds under longer text, and that the LLM summariser (`summarise_differences()`) behaves sensibly when handed multiple same-Act meanings — this touches the already-logged "Summary-field grounding gap" (Task 12 of the IM2026 major-extension plan) but doesn't require re-scoping it; that task already assumes verified, complete quote text, which this fix is what actually provides for the previously-truncated 3,136 cases.

## Sequencing & Dependencies

```
lex-au (fix + rebuild + HuggingFace export)
   |
   +---> lex-au-graph (node_id MVP — independent, can start immediately/in parallel)
   |         |
   |         +---> lex-au-graph rebuild (needs lex-au's corpus)
   |                   |
   +---> lex-au-search re-ingest (needs lex-au's corpus; parallel to lex-au-graph rebuild)
             |
             +---> term-comparison deploy + verify (needs lex-au-graph's rebuild)
```

## Revised Estimate

| Repo | Work | Estimate |
|---|---|---|
| lex-au | Term-boundary-aware forward-walk implementation (materially trickier than initially assumed — see "naive fix doesn't work" above) + multi-Act test incl. the `related-entity`/`relative` regression fixture | ~2-3 days |
| lex-au | Full corpus rebuild (2,944 files) + HuggingFace re-export | ~0.5-1 day compute/verification |
| lex-au-graph | node_id MVP (`models.py` + `graph.py`) | ~0.5-1 day |
| lex-au-graph | Rebuild + verify (746 raw collision candidates, sample of 3,136 previously-truncated defs) | ~0.5 day |
| lex-au-search | Re-ingest | ~0.5-1 day |
| term-comparison | Deploy + regression check | ~0.25-0.5 day |
| **Total** | | **~4.25-6.5 days**, spread across 4 repos |

This is higher than the pre-investigation estimate (~3.5-5.5 days) because the term-boundary-aware collection logic is a genuinely harder problem than "reuse `inject_list_defs`'s existing sibling check" — that reuse was the original assumption and it does not hold on real data.

## Out of Scope

- **The 168 `<term>`-with-no-`<def>` cases.** Already-correct `inject_list_defs` output (`<intro>` + following list, no `<def>` element) — structurally valid AKN, just invisible to `lex-au-graph`'s XPath today (requires both `term` and `def` present). A different, quieter gap (silently missing vs. visibly truncated). Not touched by this fix; would need its own XPath variant in `_extract_defined_terms` to recognize the `<intro>` shape. Worth a follow-up FUTURE.md item, not bundled here.
- **Full term-registry scoping problem** (locally-scoped in-section definitions, ~434 instances, scope-aware graph model, term-comparison UX for Act-wide vs section-scoped meanings). Already explicitly deferred past IM2026 submission per the 2026-07-13 decision log entry — unaffected by this spec.
- **Reused-eId-suffix corpus artifact** noted above — pre-existing, not actioned.

---

**For agentic workers:** REQUIRED SUB-SKILL: once this spec is approved, use superpowers:writing-plans to produce one implementation plan per repo (`lex-au`, `lex-au-graph`, `lex-au-search`, `term-comparison`), each saved to that repo's own `docs/superpowers/plans/`, sequenced per the dependency graph above.
