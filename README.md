# lex-au

Commonwealth Acts as [AKN 3.0 XML](https://docs.oasis-open.org/legaldocml/akn-core/v1.0/os/part1-vocabulary/akn-core-v1.0-os-part1-vocabulary.html) - the OASIS LegalDocML standard for machine-readable legislation. 

The UK publishes its legislation the same way: every Act on [legislation.gov.uk](https://www.legislation.gov.uk) is available as AKN XML via a `/data.akn` suffix.

```xml
<!-- Privacy Act 1988, s.81 - real output, definitions recovered from plain prose -->
<section eId="part-VII__sec-81">
  <num>81</num>
  <heading>Interpretation</heading>
  <content>
    <p>In this Part, unless the contrary intention appears:</p>
    <p><term refersTo="#term-advisory-committee">Advisory Committee</term> means
       <def>the Privacy Advisory Committee established by subsection 82(1).</def></p>
    <p><term refersTo="#term-member">member</term> means
       <def>a member of the Advisory Committee.</def></p>
  </content>
</section>
```

Crawls [legislation.gov.au](https://www.legislation.gov.au), converts DOCX to AKN 3.0 XML with [FRBR URIs](https://interoperable-europe.ec.europa.eu/sites/default/files/news/2019-11/FRBR-ShortIntro.pdf) and section-level eIds, tracks corpus state for delta updates, generates a local static preview site, and exports the corpus to Hugging Face.

> [!NOTE]
> The Department of Finance's GovCMS DXP team is building the whole-of-government version of this: [search.gov.au](https://search.gov.au) (alpha) ingests all in-force AU legislation into an internal, authority-graphed corpus, and is working with OPC on a legislative XML standard in the same territory as this repo's AKN mapping. (See [Government content is AI food](https://www.youtube.com/watch?v=X5UAWFl7-FE), APS Digital Profession Innovation Month, July 2026)

**If you just need Commonwealth legislation as structured data**, get it from the [Hugging Face dataset](https://huggingface.co/datasets/cchew/lex-au). Clone and run this repo only if you're adding new Acts or changing the AKN mapping logic.

**Status: v0.13.2** - 3,085 Acts and Regulations; published dataset at [cchew/lex-au](https://huggingface.co/datasets/cchew/lex-au) on Hugging Face (CC BY 4.0) and live corpus browser at [lex-au-explorer.netlify.app](https://lex-au-explorer.netlify.app).

lex-au-explorer renders the Commonwealth corpus word-for-word for body text. Footnotes in 6 international-instrument schedules are a named carve-out (see `docs/known-limitations-schedule-and-conversion.txt`, entry (f)).

## Why AKN XML

- **Machine-readable, not just marked-up** - defined terms are extracted even where source DOCX carries no distinguishing markup (apart from italics, which is lost entirely in DOCX→text conversion) for them.
- **Point citation, not full-text dumps** - every section, subsection, and schedule clause carries a stable `eId` (e.g. `sec-54__subsec-2`), enough to cite "s.54(2)" precisely instead of returning or re-parsing a whole Act.
- **Deterministic versioning** - FRBR separates Work / Expression / Manifestation, so a citation always points at one specific compiled version of an Act, not "whatever's live today".

## Used by these projects

- [lex-au-search](https://github.com/cchew/lex-au-search) - hybrid dense + BM25 search API and MCP server over the corpus
- [lex-au-graph](https://github.com/cchew/lex-au-graph) - cross-reference graph and definition resolution across Acts
- [ClauseKit](https://github.com/cchew/clause-kit) - LLM extraction of evaluatable rules (JSON Logic) from the corpus
- term-comparison - IM2026 "Build a Bureaucrat Bot" entry comparing term definitions across Acts

## Versions

- **v0.13.2** - Restore fetches the pinned revision with one shallow git fetch plus `git lfs pull` (~4 min, measured), verifies every file, and re-fetches failures per file with 429-aware waits inside a 60-minute budget (`--budget-minutes`, `--no-git`). `export-hf` no longer counts a built Act's own xml, reports and figures against `--change-allowance`. `update --since` pages past the 50-row Versions default.
- **v0.13.1** - Fixes the 2026-10-25 dataset clobber (2,260 XML + 909 reports reverted to stale copies). `corpus/` is no longer tracked in git. `restore_corpus_from_hf.py` restores into an empty directory only, pins one remote revision and checks every file's hash against it. `export-hf` refuses to publish unless the restore stamp matches the remote head and the changed files fit the Acts built this run (`--change-allowance`, default 200; `--allow-large-change` for full re-publishes; `--skip-sync-check` for an authoritative local corpus).
- **v0.13.0** - Local definitions on by default, scoped to their section, Part, Division or Schedule. Dictionary Schedules, Migration Regulations Schedule structure, Schedule letter suffixes (Schedule 2A) kept, "Subject to" lead-ins, amending text kept out of local terms. Full corpus re-converted: 3,085 Acts, 41,559 terms of which 9,058 local. `STRUCTURE_VERSION` unchanged at 2.
- **v0.12.1** - `update --since` no longer force-rebuilds every Act legislation.gov.au reports as "modified" -- it now respects `is_current()`'s `comp_num` check like every other build path, only rebuilding when the compilation actually changed. Found live 2026-10-13: legislation.gov.au's "modified since" signal is broader than "the compilation changed" (ordinary administrative/metadata touches get reported too), so `force=True` was unconditionally re-stamping `FRBRManifestation`'s Generation date on Acts with nothing legally different -- correct per the AKN/FRBR spec (a Manifestation date is meant to track file generation, not legal change), but it made lex-au-search's raw-file-hash delta detection useless: across a handful of weekly runs since September, every one of 3,085 Acts ended up looking "changed" to `ingest-delta`, with the same result expected every future week. `Corpus.save`/new `Corpus.touch_last_checked` stamp a `last_checked` index field on both the rebuild and skip paths, so "did lex-au reconsider this Act" stays visible even when nothing legally changed and the file correctly doesn't get touched.
- **v0.12.0** - Opt-in parsing support for non-Commonwealth sources (state and territory Word templates and register XML), built for `cchew/lex-au-privacy`. Everything is off unless a `ParserProfile` enables it, so Commonwealth output is unchanged (14 sampled Cth Acts built byte-identical; a 200-Act review of the two definition flags passed). `ParserProfile` options: `style_map`, `heading_re`/`section_re`, `schedule_heading_re`, `schedule_clause_res` (principles in "Normal" text become clauses), `unnumbered_schedule_re` and `skip_styles` (ACT Dictionary as a schedule, drop endnotes), `char_def_styles`, `definitions_in_schedules`, `extended_definitions` (qualifiers, "has the meaning given in", signposts, dash lead-ins, nested list folding), `scope_phrase_definitions` ("In this Act, X means ..." outside definitions sections), `local_definitions` (formatted-term definitions local to a section, Part, Division or schedule, written as `term-<slug>--<container eId>`; quoted amendment text is skipped and asterisk markers never link to a local term). `ActMetadata.locality` namespaces the FRBR URI (`/akn/au-vic/...`) and the corpus key, and `Corpus.save` raises `NameCollisionError` for a same-named instrument in another jurisdiction.
- **v0.11.0** - Adds an optional `ParserProfile` (`lexau.profiles`) so documents authored with a non-Commonwealth Word template can use the same builder: style map, heading/section/schedule regexes, definition-section headings (including schedule dictionaries) and character-style defined terms, threaded through `iter_paragraphs`, `AknBuilder` and the term injectors. `ActMetadata.locality` namespaces the FRBR URI (`/akn/au-vic/act/...`) and the corpus key. `Corpus.save` raises `NameCollisionError` for a same-named instrument in a different jurisdiction. All additive: `profile=None` and `locality=None` reproduce existing output, 9 new tests. Motivated by `cchew/lex-au-privacy`.
- **v0.10.2** - Pins `huggingface-hub<2.0`: 2.0.0 (released 2026-09-27) removed `HfApi.upload_large_folder` entirely, breaking `lexau export-hf` on any fresh, unpinned install (growth-check's CI job installs from scratch every run and hit this the same day). No code change -- `export_hf()` still calls `upload_large_folder` for its delta-hash unchanged-file skip on the ~1.9GB corpus, now guaranteed available. Added a real (unmocked) `HfApi` sanity test so a future upstream removal fails fast in `pytest` instead of surfacing only in production.
- **v0.10.1** - Family A XSD signatures (16, deferred out-of-scope `builder.py` content-model defects that scale with corpus size) are now `fatal: false` in `docs/xsd-whitelist.json`: `gate()` still requires them to be known signatures but no longer fails `growth-check` when their count exceeds the last-calibrated ceiling. Fixes a design flaw where static absolute-count ceilings on a corpus-size-scaling deferred defect class caused `growth-check` to fail on ordinary corpus growth (e.g. 3084->3085 Acts), not just regressions. Families B, C and C-adjacent remain ceiling-enforced.
- **v0.10.0** - Fixes `<quotedStructure>` schedule quoted-structure and amendment-instruction handling, plus a family of XSD-compliance fixes across element ordering, content models and enum coverage. Adds an eId-drift gate to catch identifier instability across re-conversions. Full corpus re-converted (3,084 Acts). Closes the figure-sweep gap: 0 Acts now missing images, down from 97 Acts / 1,512 placeholders. The strict-with-whitelist XSD gate in `scripts/spot_check.py` is now fatal (was warning-only), so a build with any XSD signature outside the whitelist fails the spot-check exit code.
- **v0.9.3** - `export-hf` no longer reconciles remote deletions from an unverified local corpus. `scripts/restore_corpus_from_hf.py` now writes a `.hf-sync-stamp.json` recording the source repo and restore time; the reconcile step runs only when that stamp is present, matches `--repo`, and is under 24h old, otherwise it skips deletions with a warning while still uploading additions. `--allow-deletes` overrides. Closes the gap that let a stale local export wipe 6 freshly-ingested Acts off the dataset on 2026-09-04.
- **v0.9.2** - Documentation and cleanup patch on v0.9.1. Corrected the Hugging Face dataset card's figure-format description: raster blobs ship as PNG or JPEG (not all PNG), and the `<img src>` carries a `corpus/` prefix from the source-repo layout, so figures resolve by basename. Removed 15 orphan duplicate figure images caused by an image-blob search that over-collected a second inline image from FIGURE paragraphs in two Acts, and capped capture at the first blob per FIGURE paragraph. Added known-limitations entry (e) covering the 59 vector-bearing Acts still on placeholder figures, the static-site generator not copying `corpus/images/`, and the `<quotedStructure>` figure-numbering edge. Minor test-path and figure-counter-reset hardening.
- **v0.9.1** - Reconciles the published Hugging Face corpus with the v0.9.0 code. The reflinks document-position fix and the schedule tables were already in the v0.9.0 codebase but never reached the dataset, and are now on Hugging Face. All 45 C1-affected schedule Acts have been re-converted (the last 20 were previously deferred). DOCX figures are now extracted to `corpus/images/`: 156 raster, 376 soffice-converted (EMF/WMF to PNG) and 0 placeholder across 225 re-converted Acts, with 59 vector-bearing Acts (including 5 ITAA-scale giants) still on placeholder figures pending a follow-up sweep. The 2 apostrophe-titled Acts remain stranded on pre-v0.9.0 XML; the cause is server-side (see known-limitations (a)).
- **v0.9.0** - Cross-reference injection no longer relocates references to the end of a mixed-content paragraph (`reflinks._process_p` now splices at document position). Schedule tables are now rendered in the AKN output: 660,291 schedule `<td>` cells across 811 Acts (tariff, appropriation, supply, repeal and superannuation Acts among them) that the XML previously omitted. DOCX-to-AKN fidelity audit tooling added (`scripts/audit_conversion_fidelity.py`, `src/lexau/fidelity.py`); corpus-wide summary in `corpus/reports/fidelity/SUMMARY.md`. Against the re-ingested corpus, and with the audit's `reorder` classifier tightened to an exact same-multiset test, the audit reports 0 `reorder` paragraphs (down from ~20.1k) and ~45k `drop_para` (down from ~343k); the `drop_text` and `spurious_para` totals blend these code fixes with the `--force` source-DOCX refresh and are not a conversion-loss count.
- **v0.8.2** - Collapsed 2 Acts ingested twice under a superseded name and a renamed current name (same `title_id`); canonicalised names at fetch time, enforced `title_id` uniqueness at write time, retained superseded names as `aliases` for citation resolution. 3,076 Acts + 2 Regulations.
- **v0.8.1** - Fixed multi-volume schedule/body misclassification (closed the corpus's last empty-`<body>` gap) and static-site FRBR path collisions for 3 Acts.
- **v0.8.0** - Automated growth/freshness ingest pipeline (GitHub Actions), dynamic low-value-title exclusion filtering.
- **v0.7.5** - Doc-conversion exclusions re-verified live, RTF detection, legacy-template style normalisation. 3,078 Acts + 2 Regulations.
- **v0.7.4** - Legacy `.doc` conversion via LibreOffice headless, `source_format` provenance tracking.
- **v0.7.3** - Style-agnostic legacy-Act parsing for DOCX with no `ActHead*` style.
- **v0.7.2** - List-form definition completeness, folds orphaned list content into truncated `<def>` elements.
- **v0.7.1** - Corpus expansion to 2,942 Acts + 2 Regulations. List-def false-positive guard, italic-run anchoring.
- **v0.7.0** - Term/def extraction recall improvements, relational definitions, Dictionary heading recognition. Crawler list-acts fix.
- **v0.6.3** - Corpus expansion to 539 Acts + 2 Regulations. Three crawler fixes: OData escaping, WAF retry, instrument ID parsing.
- **v0.6.2** - Corpus expansion to 71 Acts + 2 Regulations.
- **v0.6.1** - Corpus expansion to 20 Acts + TG(MD)R 2002. Schedule-boundary and OData-escaping parser fixes.
- **v0.6.0** - Inline formatting (`<b>/<i>/<sup>/<sub>`), list-form term/def injection. AKN compliance ~96-100% (self-assessed).
- **v0.5.0** - Amendment history, `<blockList>`, subsidiary legislation, `<lifecycle>`/`<temporalData>`, `<quotedStructure>`. 11 Acts + TG(MD)R 2002.
- **v0.4.0** - AKN semantic layer: `<term>`/`<def>`/`<TLCTerm>`, full FRBR, `<quantity>`, `<role>`/`<TLCRole>`.
- **v0.3.0** - Schedule clause hierarchy, DOCX tables, notes/examples/penalties, 4th nesting level.
- **v0.2.0** - Intra-section hierarchy, `<ref>` cross-references, `<preface>`/TOC, schedules, multi-volume Acts. 11 Acts.
- **v0.1.0** - Structural skeleton (part/division/section, basic FRBR). 8 Acts.

## Install

Only needed if you're building or modifying the corpus. To just read the XML, use the [Hugging Face dataset](https://huggingface.co/datasets/cchew/lex-au) instead.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

### LibreOffice (optional, for legacy `.doc` Acts)

Some older Acts are served by legislation.gov.au as legacy `.doc` (pre-OOXML) rather than `.docx`. lex-au converts these via LibreOffice headless before parsing — install it if you're building the full corpus or any Act still on `.doc`:

```bash
brew install --cask libreoffice   # macOS
# Debian/Ubuntu, incl. GitHub Actions runners:
sudo apt-get install --no-install-recommends libreoffice
```

Verify with `soffice --version`. No Python dependency is added - `lexau` invokes the `soffice` binary directly via `subprocess`. Not required if you only build Acts already served as `.docx`.

## CLI Usage

### Generate Act list

Fetch all in-force Commonwealth Acts from legislation.gov.au and write to `acts.txt`:

```bash
lex-au list-acts -o acts.txt
```

Paginates the OData API (~5-10 requests for ~1,000 Acts). Run once before a full corpus build.

### Build corpus

Download and convert all Acts listed in `acts.txt`:

```bash
lexau build --all --corpus-dir corpus/
```

Build a single Act:

```bash
lexau build --acts "Privacy Act 1988" --corpus-dir corpus/
```

Local definitions (section/Part/Division-scoped terms and "In this Act, X means" definitions) are tagged by default for Acts. Pass `--no-local-definitions` to build without them (regulations and instruments are never affected). `lexau update` and the growth-check workflow use the default.

Force rebuild even if already current:

```bash
lexau build --all --corpus-dir corpus/ --force
```

### Incremental update

Re-fetch and re-convert Acts modified since a given date:

```bash
lexau update --since 2026-01-01 --corpus-dir corpus/
```

### Generate static site

```bash
lexau site --corpus-dir corpus/ --site-dir site/
```

Local preview only: `site/index.html` renders Act bodies and omits schedules, preface and tables. The public browser is [lex-au-explorer](https://lex-au-explorer.netlify.app); lex-au.netlify.app redirects there.

### Export to Hugging Face

Create the dataset repo first (one-time, via HF web UI), then:

```bash
lexau export-hf --repo cchew/lex-au --corpus-dir corpus/
```

Raw DOCX files are excluded from the upload (`docx/` directory is ignored).

Before uploading, `export-hf` checks that `corpus/.hf-sync-stamp.json` (written by `scripts/restore_corpus_from_hf.py`) is pinned to the dataset's current head, so nobody has published since the restore. It then compares every local file with the remote and refuses if a differing file was not written since the restore, or if more than `--change-allowance` (default 200) differing files fall outside the xml, reports and figures of the Acts built this run. Pass `--allow-large-change` for a deliberate full re-publish and `--skip-sync-check` only when the local corpus is deliberately authoritative. The restore script only writes into an empty directory, so restore into a fresh one before a manual `export-hf`.

`export-hf` also reconciles deletions: remote files with no local counterpart are removed, but only when the stamp is under 24h old. Otherwise the reconcile is skipped with a warning. Pass `--allow-deletes` to force it.

## Acts

Acts are listed in [`acts.txt`](acts.txt), one per line. Regulations built separately with `--type regulation`.

## Corpus layout

```
corpus/
  index.json          # metadata index
  xml/                # AKN 3.0 XML, one file per Act
  reports/            # ParseReport JSON per Act (v0.2.0+)
  docx/               # raw DOCX downloads (excluded from HF export)
```

## Linking to legislation.gov.au

Every `index.json` entry (and every row of the exported `train.jsonl`) carries `title_id` (e.g. `C2004A03712` for the Privacy Act, `F2002B00237` for an instrument) and `comp_id`. `title_id` is an opaque register ID from legislation.gov.au's own Titles API — it is **not** derivable from the AKN FRBR work URI (e.g. `/akn/au/act/1988/119`); the two numbering schemes are unrelated. Combine it into a working page link:

```
https://www.legislation.gov.au/{title_id}/latest/text
```

Confirmed live (2026-07-21) for both Acts and legislative instruments. Act-level only — legislation.gov.au has no stable per-section anchor scheme (the site renders Act text in a client-side EPUB view with auto-generated, unstable Word bookmark ids, not semantic `#eId`-style anchors), so there's no equivalent way to deep-link a specific section.

## Documentation

- [AU Legislative Conventions](docs/au-legislative-conventions.md) - DOCX style map, nesting hierarchy, notes/examples/penalties, schedule patterns, citation forms, FRBR URI construction.
- [AKN Element Conformance](docs/akn-conformance.md) - every AKN 3.0 element lex-au emits, grouped by spec chapter, with the OASIS section reference and where it's populated in this corpus.

## Known limits

- Unnumbered Schedule headings (e.g. "The Schedule") in 87 Acts are absorbed into the preceding Schedule.
- Table-of-contents lines leak into Schedules in 4 Acts (Corporations Regulations 2001, Customs Tariff Act 1995, Social Security (International Agreements) Act 1999, Taxation Administration Act 1953).
- Migration Regulations 1994: Schedule 8 clauses 8207 and 8208 parse as one; Schedule 2 paragraphs sit beside subclauses, leaving positional `-N` eIds.
- The Patents Act 1990 and Social Security (Administration) Act 1999 Dictionaries sit under a misparsed clause, so their `Act` definition is lost.
- Definitions sections limited to a Part or Division ("In this Part:") are tagged Act-wide; CASR Dictionary Part 3 is untagged.
- Quoted sections in some older amending Acts parse as body sections, giving 63 spurious local terms in 19 Acts.
- Endnotes trail inside the last Schedule.
- SIS Regulations 1994 and Training Guarantee (Administration) Amendment Act 1994 share the work URI `/akn/au/act/1994/57`: `doc_type` is not stored in `index.json`.
- `reports/*-v0.5.0.json` figure counters published before v0.13.0 list converted figures as placeholders (1,890); the images were correct.
- Defined terms are missed when the definiendum is bold/italic-formatted (e.g. `<b><i>ABN (Australian Business Number)</i></b> for an *entity means ...` in A New Tax System (Australian Business Number) Act 1999 s.41)
- Asterisk-prefixed terms (`*entity`, `*Australian Business Register` - the OPC drafting convention marking a word as having its own Dictionary entry elsewhere in the Act) are preserved as literal `*` characters; not converted to a cross-reference or otherwise interpreted.
- `<ref>` cross-references are pattern-matched; nested or unusual citation forms may be missed.
- Role dictionary is global (not Act-specific); "the Minister" refers to different ministers in different Acts.
- `<noteRef>` injection handles `[note N]` bracket markers only; superscript and `(note N)` patterns are not handled.
- Formatting inside a definiens is flattened to plain text when the source paragraph is mixed content (e.g. `<b>` inside a `means` definition); the `<term>`/`<def>` split itself is still detected correctly.
- ~1,668 in-force Acts are deliberately excluded — legislation.gov.au serves a legacy `.doc` (pre-OOXML) compilation for them instead of `.docx`, and both the automatic low-value filter (1,586 titles, e.g. amendment/consequential/transitional/repeal Acts) and the individually-reviewed drop list (82 titles, e.g. spent one-off Acts) were independently re-verified live against the legislation.gov.au API on 2026-07-22 and confirmed safe to exclude. Full breakdown, per-title reasoning, and re-check policy: `docs/references/corpus-exclusions.md` in the EA project wrapper. The 4 titles that previously failed to fetch from the 128-Act "keep" batch (Cybercrime Act 2001, Financial Agreements (Commonwealth Liability) Act 1932, International Development Association Act 1960, University of Canberra Act 1989) were a transient network issue, not a format gap — re-fetched and ingested cleanly 2026-07-22.
- 16 Acts (of 3078+) still have an empty `<body>`: all are a fragmented long tail of one-off historical DOCX formats with no single addressable pattern (see `corpus/reports/legacy-residual-final-triage.md` for the full list). The root-caused `superannuation-industry-(supervision)-regulations-1994` schedule/body-ordering bug was fixed in the 2026-08-16 multi-volume split redesign (Task 1, commit 3df6e71; regression verified Task 2, commit c558ddb) — now correctly extracts 447 body sections.
