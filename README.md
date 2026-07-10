# lex-au

Commonwealth Acts as AKN 3.0 XML.

Crawls legislation.gov.au, converts DOCX to Akoma Ntoso 3.0 XML with FRBR URIs and section-level eIds, tracks corpus state for delta updates, generates a static browsable site, and exports the corpus to Hugging Face.

**Status: v0.6.2** — 71 Acts + 2 Regulations; dataset at [cchew/lex-au](https://huggingface.co/datasets/cchew/lex-au) on Hugging Face (CC BY 4.0) pending republish.

## Versions

- **v0.6.2** — 2026-07-10: Corpus expansion to 71 Acts + 2 Regulations (from 20 + 1). 49 Acts + 1 Regulation added, sourced from a lex-au-graph cross-Act citation-candidate scan (Acts cited 5+ times from within the existing corpus but not yet ingested). 1 candidate ("Family Court Act 1997") skipped — not found on legislation.gov.au, a state Act rather than Commonwealth.
- **v0.6.1** — 2026-07-09: Corpus expansion to 20 Acts + TG(MD)R 2002 — Social Security (Administration) Act 1999, Veterans' Entitlements Act 1986, Aged Care Act 2024, Family Law Act 1975 (Bereavement Navigator prerequisites); A New Tax System (GST) Act 1999, Competition and Consumer Act 2010, Migration Act 1958, Copyright Act 1968 (adoption breadth). Two bug fixes: `_split_stream` schedule-boundary misclassification (a stray "Schedule N to the..." sentence in body prose could misfile an entire Act's sections as schedule clauses — found via GST Act, now requires an actual schedule-heading style); `_odata_escape` apostrophe handling (the live legislation.gov.au API rejects the OData-spec doubled-quote escaping — found via Veterans' Entitlements Act). 269 tests.
- **v0.6.0** — 2026-07-01: Inline formatting (`<b>/<i>/<sup>/<sub>`) from DOCX runs; list-form term/def injection (`X means:` + `<intro>` conversion). AKN compliance ~96-100% of applicable elements (self-assessed) — closes the inline-formatting gap deferred from v0.5.0.
- **v0.5.0** — 2026-06-27: Amendment history and navigator prerequisites — `<blockList>`/`<item>`, `<date>` inline tagging, subsidiary legislation support (`--type regulation`, `list-instruments`), endnote parser, `<lifecycle>`/`<eventRef>`, `<temporalData>`, `<passiveModifications>`, `<quotedStructure>`, `<figure>`/`<img>`, `<rref>` range references. 11 Acts + TG(MD)R 2002. AKN compliance ~91-96% of applicable elements (self-assessed; inline formatting excluded, deferred to v0.6.0).
- **v0.4.0** — 2026-06-23: AKN semantic layer — `<term>`/`<def>`/`<TLCTerm>`, FRBR completeness (country/subtype/number/name/prescriptive/authoritative), `<longTitle>`, `<classification>/<keyword>`, `<preamble>`/`<formula>`, `<quantity>` (penalty units/imprisonment/deadlines), `<role>`/`<TLCRole>`, `<authorialNote>` eIds, `<noteRef>`. 11 Acts. AKN compliance ~68-72%.
- **v0.3.0** — 2026-06-23: Schedule clause hierarchy, DOCX tables, notes/examples/penalties, 4th nesting level `(A)(B)(C)`, extended `<ref>` patterns. 11 Acts.
- **v0.2.0** — 2026-06-22: Intra-section hierarchy (`<subsection>`, `<paragraph>`, `<subparagraph>` with nested eIds), `<ref>` cross-reference markup, `<preface>`/TOC, schedules as `<attachments>`, multi-volume Acts (Corporations 7 vols, Fair Work 4, Criminal Code 3), ISO FRBRdate. 11 Acts. Parse report per Act.
- **v0.1.0** — 2026-06-19: Structural skeleton (part/division/section, basic FRBR). 8 Acts.

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

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

Opens `site/index.html` for local browsing.

### Export to Hugging Face

Create the dataset repo first (one-time, via HF web UI), then:

```bash
lexau export-hf --repo cchew/lex-au --corpus-dir corpus/
```

Raw DOCX files are excluded from the upload (`docx/` directory is ignored).

## Acts

Acts are listed in [`acts.txt`](acts.txt), one per line — 71 Acts as of v0.6.2, plus 2 Regulations (TG(MD)R 2002, Superannuation Industry (Supervision) Regulations 1994) built separately with `--type regulation`.

## Corpus layout

```
corpus/
  index.json          # metadata index
  xml/                # AKN 3.0 XML, one file per Act
  reports/            # ParseReport JSON per Act (v0.2.0+)
  docx/               # raw DOCX downloads (excluded from HF export)
```

## Documentation

- [AU Legislative Conventions](docs/au-legislative-conventions.md) — DOCX style map, nesting hierarchy, notes/examples/penalties, schedule patterns, citation forms, FRBR URI construction.

## Known limits (v0.5.0)

- `<ref>` cross-references are pattern-matched; nested or unusual citation forms may be missed.
- Role dictionary is global (not Act-specific); "the Minister" refers to different ministers in different Acts.
- `<noteRef>` injection handles `[note N]` bracket markers only; superscript and `(note N)` patterns are not handled.
