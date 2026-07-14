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
pretty_name: lex-au - Commonwealth Acts as AKN 3.0 XML
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train.jsonl
---

# lex-au

**Commonwealth Acts as Akoma Ntoso (AKN) 3.0 XML** - open civic infrastructure for Australian legislative data.

Australia's [legislation.gov.au](https://legislation.gov.au) provides DOCX and PDF downloads. This dataset provides structured XML, section-level addressing and AKN for Commonwealth Acts in force.

**Version: v0.7.2** - 2,942 Acts + 2 Regulations ([full Act list](https://github.com/cchew/lex-au/blob/main/acts.txt)).

See [github.com/cchew/lex-au](https://github.com/cchew/lex-au) for source code and CLI (if you want to change the AKN mapping), version history and known limits.

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

Every section, subsection, and schedule clause carries a stable `eId` (e.g. `sec-6__subsec-1__para-a`) for citation-level addressing - see "What's in this dataset" below for the full element reference.

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

Full element-by-element conformance detail, organised by AKN 3.0 spec chapter: [`docs/akn-conformance.md`](https://github.com/cchew/lex-au/blob/main/docs/akn-conformance.md) in the source repo.

## Licence

CC BY 4.0. Source legislation is Crown copyright - Commonwealth of Australia; reproduction permitted for non-commercial and research purposes under the [PSI Framework](https://www.legislation.gov.au/Help/Copyright).

## What's built on this dataset

- [lex-au-search](https://github.com/cchew/lex-au-search) - hybrid dense + BM25 search API and MCP server
- [lex-au-graph](https://github.com/cchew/lex-au-graph) - cross-reference graph and definition resolution across Acts
- [ClauseKit](https://github.com/cchew/clause-kit) - LLM extraction of evaluatable rules (JSON Logic) from Acts

## Related

- [github.com/cchew/lex-au](https://github.com/cchew/lex-au) - source code and CLI
- [lex-au.netlify.app](https://lex-au.netlify.app) - browsable preview of the corpus, rendered from this XML
- [Open Australian Legal Corpus](https://huggingface.co/datasets/umarbutler/open-australian-legal-corpus) - complementary plain-text corpus
