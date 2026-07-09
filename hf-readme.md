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

**Version: v0.6.1** — 20 Acts + 1 regulation, published 2026-07-09. Source code and CLI at [github.com/cchew/lex-au](https://github.com/cchew/lex-au).

## Quick example

Extract a single section's text and defined terms with `lxml`:

```python
from huggingface_hub import hf_hub_download
from lxml import etree

path = hf_hub_download(repo_id="cchew/lex-au", filename="xml/privacy-act-1988.xml", repo_type="dataset")
AKN = "{http://docs.oasis-open.org/legaldocml/ns/akn/3.0}"
root = etree.parse(path).getroot()

section = root.find(f".//{AKN}section[@eId='sec-6']")
print("".join(section.itertext())[:300])

for term in root.findall(f".//{AKN}TLCTerm"):
    print(term.get("eId"), "->", term.get("showAs"))
```

Every section, subsection, and schedule clause carries a stable `eId` (e.g. `sec-6__subsec-1__para-a`) for citation-level addressing — see "What's in this dataset" below for the full element reference.

## Why this exists alongside the Open Australian Legal Corpus

[Isaacus](https://isaacus.com)'s Open Australian Legal Corpus (229K documents, 1.4B tokens, plain-text JSONL) is the larger, more complete Australian legal text corpus, and their Kanon 2 models are benchmark-leading on Australian legal retrieval. lex-au is a different, complementary layer: it is AKN 3.0 structured XML with section/subsection-level `eId` addressing and FRBR identifiers, not plain text — the citation granularity a plain-text corpus can't provide by construction. It is smaller (12 Commonwealth Acts vs 229K documents), openly licensed for self-hosting (CC BY 4.0, MIT-licensed tooling), and designed for point citation ("under s.26WA(1)(a)") rather than passage retrieval. Use the Open Australian Legal Corpus for breadth; use lex-au where you need addressable, machine-verifiable structure over a smaller, curated set of Acts.

## Versions

- **v0.6.1** — 2026-07-09: Corpus expansion to 20 Acts + TG(MD)R 2002 regulation — Social Security (Administration) Act 1999, Veterans' Entitlements Act 1986, Aged Care Act 2024, Family Law Act 1975 (Bereavement Navigator prerequisites); A New Tax System (GST) Act 1999, Competition and Consumer Act 2010, Migration Act 1958, Copyright Act 1968 (adoption breadth). Two parser bug fixes found during this expansion: (1) `_split_stream` was misfiling an entire Act's body as schedule content when body prose contained a stray sentence starting "Schedule N to the..." (found via GST Act, which had ~600 sections misfiled as schedule clauses before the fix — now requires an actual schedule-heading style, not just matching text); (2) OData `$filter` apostrophe-escaping was breaking lookups for any Act name containing an apostrophe (found via Veterans' Entitlements Act — the live API doesn't accept the spec's doubled-quote escaping). 269 tests.
- **v0.6.0** — 2026-07-01: Inline formatting (`<b>`/`<i>`/`<sup>`/`<sub>` from DOCX runs) and list-form term/def injection (`X means:` + `<intro>` conversion). AKN compliance ~96-100% of applicable elements (self-assessed) — closes the inline-formatting gap deferred from v0.5.0.
- **v0.5.2** — 2026-07-01: Added Therapeutic Goods Act 1989 (12 Acts).
- **v0.5.0** — 2026-06-27: Navigator prerequisites — `<blockList>`/`<item>`, `<date>`, subsidiary legislation support, amendment history (`<lifecycle>`, `<temporalData>`, `<passiveModifications>`), `<quotedStructure>`, `<figure>`/`<img>`, `<rref>` range references. 225 tests. AKN compliance ~91-96% of applicable elements (self-assessed against the AKN 3.0 element types applicable to compiled Acts; inline formatting excluded, deferred to v0.6.0).
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
- `<date>` elements for statutory dates and time expressions
- `<blockList>`/`<item>` for unnumbered list structures
- `<lifecycle>`, `<temporalData>`, `<passiveModifications>` populated from Endnote 3-4 amendment history
- `<quotedStructure>` for single-provision amendment inserts; `<figure>`/`<img>` for embedded images; `<rref>` for section range references
- Corpus index at `index.json`; parse report per Act in `reports/`

## Current corpus (v0.6.1)

| Act | Year | Compilation |
|---|---|---|
| Acts Interpretation Act 1901 | 1901 | C2026C00117 |
| National Health Act 1953 | 1953 | C2026C00164 |
| Migration Act 1958 | 1958 | C2026C00232 |
| Copyright Act 1968 | 1968 | C2026C00138 |
| Family Law Act 1975 | 1975 | C2025C00341 |
| Freedom of Information Act 1982 | 1982 | C2026C00020 |
| Veterans' Entitlements Act 1986 | 1986 | C2026C00099 |
| Privacy Act 1988 | 1988 | C2026C00227 |
| Therapeutic Goods Act 1989 | 1989 | C2025C00525 |
| Social Security Act 1991 | 1991 | C2026C00160 |
| Superannuation Industry (Supervision) Act 1993 | 1993 | C2026C00212 |
| Criminal Code Act 1995 | 1995 | C2026C00243 |
| Income Tax Assessment Act 1997 | 1997 | C2026C00242 |
| Social Security (Administration) Act 1999 | 1999 | C2026C00010 |
| A New Tax System (Goods and Services Tax) Act 1999 | 1999 | C2026C00081 |
| Corporations Act 2001 | 2001 | C2026C00058 |
| Therapeutic Goods (Medical Devices) Regulations 2002 | 2002 | F2026C00240 |
| Fair Work Act 2009 | 2009 | C2026C00141 |
| Competition and Consumer Act 2010 | 2010 | C2026C00206 |
| National Disability Insurance Scheme Act 2013 | 2013 | C2026C00181 |
| Aged Care Act 2024 | 2024 | C2025C00589 |

## Known limits

- `<ref>` cross-references are pattern-matched; nested or unusual citation forms may be missed.
- Role dictionary is global, not Act-specific; "the Minister" refers to different ministers in different Acts.
- `<noteRef>` injection handles `[note N]` bracket markers only; superscript and `(note N)` patterns are not handled.

## Licence

CC BY 4.0. Source legislation is Crown copyright — Commonwealth of Australia; reproduction permitted for non-commercial and research purposes under the [PSI Framework](https://www.legislation.gov.au/Help/Copyright).

## Related

- [github.com/cchew/lex-au](https://github.com/cchew/lex-au) — source code and CLI
- [Open Australian Legal Corpus](https://huggingface.co/datasets/umarbutler/open-australian-legal-corpus) — complementary plain-text corpus
