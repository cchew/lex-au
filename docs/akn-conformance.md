# AKN 3.0 Element Conformance

Every AKN element lex-au emits, grouped by the [OASIS Akoma Ntoso spec](https://docs.oasis-open.org/legaldocml/akn-core/v1.0/os/part1-vocabulary/akn-core-v1.0-os-part1-vocabulary.html)'s own chapter structure, not by AU DOCX convention. Section references below are approximate signposts into that spec, not exact citations — follow the link for the authoritative text.

This is the backing detail for the "AKN compliance ~96-100% of applicable elements (self-assessed)" claims in the version history: applicable elements are the ones below, catalogued manually against what AU Commonwealth Acts actually contain (AKN defines a much larger vocabulary — bills, judgments, debate records — most of which has no AU-compiled-Act equivalent and is out of scope here).

For how each element maps to a specific DOCX style or citation pattern in AU legislation, see [AU Legislative Conventions](au-legislative-conventions.md) — this document answers "does lex-au support AKN element X," that one answers "how does lex-au recognise it in the source."

---

## Identification & metadata (spec §4.1.3, §5.9)

| Element | Populated | Since |
|---|---|---|
| `FRBRWork`, `FRBRExpression`, `FRBRManifestation` | Yes — all three levels | v0.1.0 (partial), v0.4.0 (complete) |
| `FRBRthis`, `FRBRuri` | Yes, per level | v0.1.0 |
| `FRBRdate`, `FRBRauthor` | Yes, per level (ISO date format) | v0.2.0 |
| `FRBRcountry`, `FRBRsubtype`, `FRBRnumber`, `FRBRname` | Yes | v0.4.0 |
| `FRBRprescriptive`, `FRBRauthoritative` | Yes | v0.4.0 |
| `FRBRlanguage` | Yes (`eng`, Expression level only) | v0.4.0 |
| `identification` | Yes (`source="#lex-au"`) | v0.1.0 |
| `classification`, `keyword` | Yes | v0.4.0 |

## Lifecycle & amendments (spec §5.7, §5.10.2–5.10.3)

| Element | Populated | Since |
|---|---|---|
| `lifecycle`, `eventRef` | Yes — generation + amendment events from Endnote 3-4 | v0.5.0 |
| `temporalData` | Yes | v0.5.0 |
| `passiveModifications` | Yes | v0.5.0 |
| `activeModifications` | No — not applicable to compiled (point-in-time) Acts | — |
| `quotedStructure` | Yes — single-provision amendment inserts | v0.5.0 |

## Hierarchical structure (spec §6.3)

| Element | Populated | Since |
|---|---|---|
| `chapter`, `part`, `division`, `subDivision` | Yes | v0.1.0 |
| `section` | Yes, with `eId` | v0.1.0 |
| `subsection`, `paragraph`, `subparagraph` | Yes, with nested `eId` | v0.2.0–v0.3.0 |
| 4th nesting level `(A)(B)(C)` | Yes, as `hcontainer name="level4"` | v0.3.0 |
| `attachments`, `attachment` (schedules) | Yes | v0.2.0 |
| `hcontainer` (schedule clause/subclause, example, penalty) | Yes | v0.2.0–v0.3.0 |
| `preface`, `toc`, `tocItem` | Yes | v0.2.0 |
| `longTitle` | Yes | v0.4.0 |
| `preamble`, `formula` | Yes | v0.4.0 |

## Content & inline formatting (spec §5.4)

| Element | Populated | Since |
|---|---|---|
| `p`, `content` | Yes | v0.1.0 |
| `b`, `i`, `sup`, `sub` | Yes, from DOCX run formatting | v0.6.0 |
| `u`, `span` | No — not observed in AU Commonwealth Act source formatting | — |

## Definitions & shared elements (spec §5.5)

| Element | Populated | Since |
|---|---|---|
| `term`, `def` | Yes — quoted and unquoted `"X" means Y` / `X means:` forms, recovered from prose | v0.4.0 (quoted), v0.6.0 (list-form) |
| `TLCTerm` (registry) | Yes | v0.4.0 |
| `quantity` | Yes — penalty units, custodial sentences, statutory deadlines | v0.4.0 |
| `role` | Yes — known Commonwealth officeholders (Minister, Secretary, Commissioner, etc.) | v0.4.0 |
| `TLCRole` (registry) | Yes | v0.4.0 |
| `date` | Yes — statutory dates and time expressions | v0.5.0 |
| `person`, `organization` | No — not distinguished from `role` in current extraction | — |

## References (spec §5.8, §3.6)

| Element | Populated | Since |
|---|---|---|
| `ref` | Yes — same-Act section/subsection, cross-Act FRBR URIs, subsidiary legislation | v0.2.0 |
| `rref` | Yes — section range references (e.g. "ss 6-9") | v0.5.0 |

## Notes & media (spec §5.2, §5.10.11)

| Element | Populated | Since |
|---|---|---|
| `authorialNote` | Yes — `placement="end"`, from `Note:`/`Example:`/`Penalty:` style paragraphs | v0.3.0 |
| `noteRef` | Yes — `[note N]` bracket markers only; superscript and `(note N)` forms not handled | v0.5.0 |
| `figure`, `img` | Yes — embedded images | v0.5.0 |

## Lists (spec §5.12)

| Element | Populated | Since |
|---|---|---|
| `blockList`, `item` | Yes — unnumbered list structures | v0.5.0 |

---

## Out of scope

Elements that exist in the AKN vocabulary but have no equivalent in compiled AU Commonwealth Acts, so are not tracked against the compliance percentage: `bill`-specific elements (`amendment`, `debate`), `judgment`-specific elements (`judgmentBody`, `motivation`), and `doc`-level generic document elements. AKN defines these for other document types the standard covers (bills, judgments, debate records); lex-au only ingests compiled, in-force Acts.
