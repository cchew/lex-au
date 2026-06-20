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

**Version: v0.1.0** — 8 Acts, published 2026-06-19. Source code and CLI at [github.com/cchew/lex-au](https://github.com/cchew/lex-au).

## What's in this dataset

Each Act is a single AKN 3.0 XML file with:

- FRBR URIs (`/akn/au/act/{year}/{slug}/aus/{comp_id}`)
- Section-level `eId` attributes (e.g., `part-II__dvs-1__sec-6`)
- Structural hierarchy: parts, divisions, subdivisions, sections
- Corpus index at `index.json`

## Current corpus (v0.1.0)

| Act | Year | Compilation |
|---|---|---|
| Acts Interpretation Act | 1901 | C2026C00117 |
| National Health Act | 1953 | C2026C00164 |
| Freedom of Information Act | 1982 | C2026C00020 |
| Privacy Act | 1988 | C2026C00227 |
| Criminal Code Act | 1995 | C2026C00098 |
| Corporations Act | 2001 | C2026C00058 |
| Fair Work Act | 2009 | C2026C00141 |
| National Disability Insurance Scheme Act | 2013 | C2026C00181 |

## Known limitations (v0.1.0)

- **Intra-section structure not parsed**: subsections `(1)`, `(2)` and paragraphs `(a)`, `(b)` are emitted as flat `<p>` elements. The smallest addressable unit is a section. Subsection hierarchy is v0.2.0 scope.
- **Multi-volume Acts**: Corporations Act and Criminal Code fetch volume 0 only. Volume merging is v0.2.0 scope.
- **No `<ref>` cross-reference markup**: legislative cross-references appear as plain text.
- **Pre-body content**: cover page and table of contents land in `<body>` rather than `<preface>`.
- **Schedules unstructured**: schedule content (e.g., Privacy Act Schedule 1 — Australian Privacy Principles) is not tagged as `<hcontainer name="schedule">`.

## Licence

CC BY 4.0. Source legislation is Crown copyright — Commonwealth of Australia; reproduction permitted for non-commercial and research purposes under the [PSI Framework](https://www.legislation.gov.au/Help/Copyright).

## Related

- [github.com/cchew/lex-au](https://github.com/cchew/lex-au) — source code and CLI
- [Open Australian Legal Corpus](https://huggingface.co/datasets/umarbutler/open-australian-legal-corpus) — complementary plain-text corpus
