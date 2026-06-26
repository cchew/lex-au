---
license: cc-by-4.0
language:
- en
tags:
- law
- legislation
- australia
- akn
- xml
- akoma-ntoso
pretty_name: lex-au — Commonwealth Acts as AKN 3.0 XML
---

# lex-au

**Commonwealth Acts as Akoma Ntoso 3.0 XML** — open civic infrastructure for Australian legislative data.

Australia's [legislation.gov.au](https://legislation.gov.au) provides DOCX and PDF downloads but no structured XML, no section-level addressing, and no AKN. This dataset fills that gap for Commonwealth Acts in force.

**Version: v0.4.0** — 11 Acts, published 2026-06-26. Source code and CLI at [github.com/cchew/lex-au](https://github.com/cchew/lex-au).

## Versions

- **v0.4.0** — 2026-06-26: AKN semantic layer — `<term>`/`<def>`/`<TLCTerm>`, FRBR completeness (country/subtype/number/name/prescriptive/authoritative), `<longTitle>`, `<classification>/<keyword>`, `<preamble>`/`<formula>`, `<quantity>` (penalty units/imprisonment/deadlines), `<role>`/`<TLCRole>`, `<authorialNote>` eIds, `<noteRef>`. 11 Acts. AKN compliance ~68-72%.
- **v0.3.0** — 2026-06-23: Schedule clause hierarchy, DOCX tables, notes/examples/penalties, 4th nesting level `(A)(B)(C)`, extended `<ref>` patterns. 11 Acts.
- **v0.2.0** — 2026-06-22: Intra-section hierarchy, `<ref>` cross-references, `<preface>`/TOC, schedules, multi-volume Acts, ISO FRBRdate. 11 Acts.
- **v0.1.0** — 2026-06-19: Structural skeleton (part/division/section, basic FRBR). 8 Acts.

## What's in this dataset

Each Act is a single AKN 3.0 XML file with:

- FRBR URIs (`/akn/au/act/{year}/{slug}/aus/{comp_id}`)
- Structural hierarchy: parts, divisions, subdivisions, sections
- Intra-section hierarchy: `<subsection>`, `<paragraph>`, `<subparagraph>` with nested eIds (e.g. `sec-6__subsec-1__para-a`)
- `<ref>` elements for same-Act section/subsection references and cross-Act FRBR URIs
- `<preface>` with `<toc>`/`<tocItem>` and compilation notices
- Schedules as `<attachments><attachment><hcontainer name="schedule">`
- `<term refersTo="#term-X">` and `<def>` in definition sections; `<TLCTerm>` registry in `<references>`
- `<quantity refersTo="#penaltyUnit|#custodialSentence|#deadline">` for penalty units, imprisonment terms, and statutory deadlines
- `<role refersTo="#commissioner|#minister|...">` for known Commonwealth officeholders; `<TLCRole>` registry
- FRBR completeness: `FRBRcountry`, `FRBRsubtype`, `FRBRnumber`, `FRBRname`, `FRBRprescriptive`, `FRBRauthoritative`
- Corpus index at `index.json`; parse report per Act in `reports/`

## Current corpus (v0.4.0)

| Act | Year | Compilation |
|---|---|---|
| Acts Interpretation Act | 1901 | C2026C00117 |
| National Health Act | 1953 | C2026C00164 |
| Freedom of Information Act | 1982 | C2026C00020 |
| Privacy Act | 1988 | C2026C00227 |
| Social Security Act | 1991 | C2026C00160 |
| Criminal Code Act | 1995 | C2026C00098 |
| Superannuation Industry (Supervision) Act | 1993 | C2026C00212 |
| Income Tax Assessment Act | 1997 | C2026C00218 |
| Corporations Act | 2001 | C2026C00058 |
| Fair Work Act | 2009 | C2026C00141 |
| National Disability Insurance Scheme Act | 2013 | C2026C00181 |

## Known limits

- `<ref>` cross-references are pattern-matched; nested or unusual citation forms may be missed.
- Role dictionary is global, not Act-specific; "the Minister" refers to different ministers in different Acts.
- `<noteRef>` injection handles `[note N]` bracket markers only; superscript and `(note N)` patterns are not handled.

## Licence

CC BY 4.0. Source legislation is Crown copyright — Commonwealth of Australia; reproduction permitted for non-commercial and research purposes under the [PSI Framework](https://www.legislation.gov.au/Help/Copyright).

## Related

- [github.com/cchew/lex-au](https://github.com/cchew/lex-au) — source code and CLI
- [Open Australian Legal Corpus](https://huggingface.co/datasets/umarbutler/open-australian-legal-corpus) — complementary plain-text corpus
