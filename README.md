# lex-au

Commonwealth Acts as AKN 3.0 XML.

Crawls legislation.gov.au, converts DOCX to Akoma Ntoso 3.0 XML with FRBR URIs and section-level eIds, tracks corpus state for delta updates, generates a static browsable site, and exports the corpus to Hugging Face.

**Status: v0.5.0** — dataset at [cchew/lex-au](https://huggingface.co/datasets/cchew/lex-au) on Hugging Face (CC BY 4.0).

## Versions

- **v0.5.0** — 2026-06-27: Amendment history and navigator prerequisites — `<blockList>`/`<item>`, `<date>` inline tagging, subsidiary legislation support (`--type regulation`, `list-instruments`), endnote parser, `<lifecycle>`/`<eventRef>`, `<temporalData>`, `<passiveModifications>`, `<quotedStructure>`, `<figure>`/`<img>`, `<rref>` range references. 11 Acts + TG(MD)R 2002. AKN compliance ~91-100%.
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

Acts are listed in `acts.txt`, one per line. Current corpus:

- Privacy Act 1988
- Fair Work Act 2009
- Corporations Act 2001
- Acts Interpretation Act 1901
- Criminal Code Act 1995
- Freedom of Information Act 1982
- National Disability Insurance Scheme Act 2013
- National Health Act 1953
- Social Security Act 1991
- Superannuation Industry (Supervision) Act 1993
- Income Tax Assessment Act 1997

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
