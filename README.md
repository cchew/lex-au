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

Crawls [legislation.gov.au](https://www.legislation.gov.au), converts DOCX to AKN 3.0 XML with [FRBR URIs](https://interoperable-europe.ec.europa.eu/sites/default/files/news/2019-11/FRBR-ShortIntro.pdf) and section-level eIds, tracks corpus state for delta updates, generates a [static browsable site](https://lex-au.netlify.app), and exports the corpus to Hugging Face.

**If you just need Commonwealth legislation as structured data**, get it from the [Hugging Face dataset](https://huggingface.co/datasets/cchew/lex-au). Clone and run this repo only if you're adding new Acts or changing the AKN mapping logic.

**Status: v0.7.4** (unpublished) - 3,078 Acts + 2 Regulations locally; published dataset at [cchew/lex-au](https://huggingface.co/datasets/cchew/lex-au) on Hugging Face (CC BY 4.0) is still v0.7.3 (2,942 Acts + 2 Regulations) pending re-export; live corpus browser at [lex-au.netlify.app](https://lex-au.netlify.app) likewise pending redeploy.

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

- **v0.7.4** (unpublished) - Legacy `.doc` (pre-OOXML) Act conversion via LibreOffice headless, gated on a 30-Act spike (90% non-empty-`<body>` rate, GO). 124 of a 128-Act relevance-skimmed batch converted and ingested (76.6%→ now 3,066 Acts + 2 Regulations locally); `source_format: doc-converted` provenance tracked in `index.json`. 4 conversion failures, 82 relevance-skimmed drops, and ~1,586 low-value titles remain unconverted.
- **v0.7.3** - Style-agnostic legacy-Act parsing for DOCX with no `ActHead*` style: 422 of 551 previously-empty-body Acts now parse (76.6%). 129 residual (58 with an additional unimplemented paragraph shape, 71 fragmented one-off historical formats) documented as future work.
- **v0.7.2** - List-form definition completeness: folds orphaned list content into truncated `<def>` elements (~3,125 defs fixed corpus-wide).
- **v0.7.1** - Corpus expansion to 2,942 Acts + 2 Regulations, 28,662 terms. List-def false-positive guard, italic-run anchoring for definienda.
- **v0.7.0** - Term/def extraction recall: broadened definiendum character class, relational definitions, asterisk-marked term usages, Dictionary heading recognition, false-positive guards. list-acts/list-instruments crawler fix.
- **v0.6.3** - Corpus expansion to 539 Acts + 2 Regulations. Three crawler fixes: OData escaping for titles with an apostrophe plus a parenthesised clause, a WAF false-positive retry via progressively-trimmed title fragments, and F-prefixed instrument ID parsing.
- **v0.6.2** - Corpus expansion to 71 Acts + 2 Regulations
- **v0.6.1** - Corpus expansion to 20 Acts + TG(MD)R 2002. Two parser bug fixes: schedule-boundary misclassification, OData apostrophe escaping. 269 tests.
- **v0.6.0** - Inline formatting (`<b>/<i>/<sup>/<sub>`) and list-form term/def injection. AKN compliance ~96-100% of applicable elements (self-assessed, see [this](docs/akn-conformance.md)).
- **v0.5.0** - Amendment history and navigator prerequisites: `<blockList>`, subsidiary legislation support, `<lifecycle>`/`<temporalData>`, `<quotedStructure>`, `<figure>`/`<img>`, range references. 11 Acts + TG(MD)R 2002.
- **v0.4.0** - AKN semantic layer: `<term>`/`<def>`/`<TLCTerm>`, full FRBR, `<quantity>`, `<role>`/`<TLCRole>`.
- **v0.3.0** - Schedule clause hierarchy, DOCX tables, notes/examples/penalties, 4th nesting level.
- **v0.2.0** - Intra-section hierarchy, `<ref>` cross-references, `<preface>`/TOC, schedules, multi-volume Acts, ISO FRBRdate. 11 Acts.
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

Opens `site/index.html` for local browsing, or see the hosted copy at [lex-au.netlify.app](https://lex-au.netlify.app). <!-- TODO: no CI hook yet - Netlify site was deployed manually via `netlify deploy --prod`; wire up a rebuild on every corpus update alongside the GitHub tag and HF republish -->

### Export to Hugging Face

Create the dataset repo first (one-time, via HF web UI), then:

```bash
lexau export-hf --repo cchew/lex-au --corpus-dir corpus/
```

Raw DOCX files are excluded from the upload (`docx/` directory is ignored).

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

- Defined terms are missed when the definiendum is bold/italic-formatted (e.g. `<b><i>ABN (Australian Business Number)</i></b> for an *entity means ...` in A New Tax System (Australian Business Number) Act 1999 s.41)
- Asterisk-prefixed terms (`*entity`, `*Australian Business Register` - the OPC drafting convention marking a word as having its own Dictionary entry elsewhere in the Act) are preserved as literal `*` characters; not converted to a cross-reference or otherwise interpreted.
- `<ref>` cross-references are pattern-matched; nested or unusual citation forms may be missed.
- Role dictionary is global (not Act-specific); "the Minister" refers to different ministers in different Acts.
- `<noteRef>` injection handles `[note N]` bracket markers only; superscript and `(note N)` patterns are not handled.
- Formatting inside a definiens is flattened to plain text when the source paragraph is mixed content (e.g. `<b>` inside a `means` definition); the `<term>`/`<def>` split itself is still detected correctly.
- ~1,668 in-force Acts are deliberately excluded — legislation.gov.au serves a legacy `.doc` (pre-OOXML) compilation for them instead of `.docx`, and both the automatic low-value filter (1,586 titles, e.g. amendment/consequential/transitional/repeal Acts) and the individually-reviewed drop list (82 titles, e.g. spent one-off Acts) were independently re-verified live against the legislation.gov.au API on 2026-07-22 and confirmed safe to exclude. Full breakdown, per-title reasoning, and re-check policy: `docs/references/corpus-exclusions.md` in the EA project wrapper. The 4 titles that previously failed to fetch from the 128-Act "keep" batch (Cybercrime Act 2001, Financial Agreements (Commonwealth Liability) Act 1932, International Development Association Act 1960, University of Canberra Act 1989) were a transient network issue, not a format gap — re-fetched and ingested cleanly 2026-07-22.
- 17 Acts (of 3078+) still have an empty `<body>`: 16 are a fragmented long tail of one-off historical DOCX formats with no single addressable pattern (see `corpus/reports/legacy-residual-final-triage.md` for the full list); 1 (`superannuation-industry-(supervision)-regulations-1994`) has a root-caused, understood `_split_stream` schedule/body-ordering bug — a fix was attempted and reverted 2026-07-22 after it regressed section counts on other Acts (see `FUTURE.md`'s "`_split_stream` mis-splits when a Regulation's schedules precede its body" entry before attempting again).
