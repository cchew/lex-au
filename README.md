# lex-au

Commonwealth Acts as AKN 3.0 XML.

Crawls legislation.gov.au, converts DOCX to Akoma Ntoso 3.0 XML with FRBR URIs and section-level eIds, tracks corpus state for delta updates, generates a static browsable site, and exports the corpus to Hugging Face.

**Status: v0.1.0** — dataset at [cchew/lex-au](https://huggingface.co/datasets/cchew/lex-au) on Hugging Face (CC BY 4.0).

## Install

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## CLI Usage

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

## Corpus layout

```
corpus/
  index.json          # metadata index
  xml/                # AKN 3.0 XML, one file per Act
  docx/               # raw DOCX downloads (excluded from HF export)
```

## Known limits (v0.1.0)

- Multi-volume Acts (Corporations Act, Criminal Code): fetches volume 0 only. Volume merging is v0.2.0 scope.
- Tables and schedules in DOCX are not structured -- emitted as body text.
