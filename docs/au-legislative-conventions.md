# AU Legislative Conventions

Reference for Australian Commonwealth Act patterns and their AKN 3.0 mappings in lex-au.

Commonwealth Acts are sourced as compiled DOCX from legislation.gov.au. This document describes AU-specific document structures, DOCX style conventions, and how lex-au maps them to AKN 3.0 elements. International AKN consumers can use this as a translation guide.

---

## DOCX Style Map

legislation.gov.au compiles Acts using a fixed Word style set. lex-au uses style names as the primary signal for element classification; leading text patterns serve as a confirming guard or fallback.

| DOCX style | Element classified as | AKN element |
|---|---|---|
| `ActHead 1`–`ActHead 4` | CHAPTER / PART / DIVISION / SUBDIVISION | `<chapter>`, `<part>`, `<division>`, `<subDivision>` |
| `ActHead 5` | SECTION | `<section>` |
| `Body Text` | SUBSECTION (if `(N)` prefix) or BODY | `<subsection>` or `<p>` |
| `List Paragraph` | PARAGRAPH / SUBPARAGRAPH / LEVEL4 | `<paragraph>`, `<subparagraph>`, `<hcontainer name="level4">` |
| `Note` | NOTE | `<authorialNote placement="end">` |
| `Example` | EXAMPLE | `<hcontainer name="example">` |
| `Penalty` | PENALTY | `<hcontainer name="penalty">` |
| `TOC Heading` | (preface TOC title) | `<preface><toc>` |
| `TOC 1` / `TOC 2` / `TOC 3` | (preface TOC entry) | `<toc><tocItem>` |

Non-breaking space (`\xa0`) is used between structural keywords and numbers in compiled Acts: `Part\xa01`, `Division\xa03`. The heading regex accounts for this.

Style fallback: if a paragraph has an unknown or missing style, lex-au applies the subsection and paragraph patterns by leading text alone and logs a `style_fallback` in the parse report.

---

## Nesting Hierarchy

Commonwealth Acts use up to five nesting levels below Part/Division:

```
<part>                        Part III
  <division>                  Division 3
    <section eId="sec-16">    16  Short title
      <subsection>            (1) text...
        <paragraph>           (a) text...
          <subparagraph>      (i) text...
            <hcontainer       (A) text...
              name="level4">
```

eId convention: `part-III__sec-16__subsec-1__para-a__subpara-i__level4-a`

Level separators: `__` (double underscore). All eId components are lowercase (AKN-NC §3.5). Source DOCX uppercase `(A)(B)(C)` is normalised to lowercase in the eId.

The 4th nesting level `(A)(B)(C)` appears in the Corporations Act 2001 and Income Tax Assessment Act 1997 — not in all Acts.

---

## Notes, Examples, and Penalties

These are editorial annotation blocks that appear inline with section text. They are common across most Commonwealth Acts.

### Notes

A note qualifies, clarifies, or cross-references a provision. In the compiled DOCX they appear with `Note` style or leading `Note:` text.

AKN mapping: `<authorialNote placement="end" marker="*">`. The `placement="end"` attribute indicates the note appears at the end of the containing provision (standard for AU legislative notes). The `marker` is `"*"` by default in v0.3.0; v0.4.0 will add per-section note counters.

```xml
<section eId="sec-16">
  <num>16</num>
  <heading>Short title</heading>
  <subsection eId="sec-16__subsec-1">
    <num>1</num>
    <content><p>This Act may be cited as ...</p></content>
    <authorialNote placement="end" marker="*">
      <content><p>Note: See also section 4.</p></content>
    </authorialNote>
  </subsection>
</section>
```

### Examples

An example illustrates how a provision applies. In the DOCX they appear with `Example` style or leading `Example:` / `Examples:` text.

AKN mapping: `<hcontainer name="example"><content><p>...</p></content></hcontainer>`. AKN 3.0 has no dedicated `<example>` element; `hcontainer` with `name="example"` is the conformant approach used by legislation.gov.uk and Laws.Africa.

```xml
<hcontainer name="example">
  <content><p>Example: A person who...</p></content>
</hcontainer>
```

### Penalties

A penalty specifies the maximum criminal sanction for an offence. In the DOCX they appear with `Penalty` style or leading `Penalty:` text. The standard form is `Penalty: N penalty units.`

AKN mapping: `<hcontainer name="penalty"><content><p>...</p></content></hcontainer>`.

```xml
<hcontainer name="penalty">
  <content><p>Penalty: 60 penalty units.</p></content>
</hcontainer>
```

Note: `penalty units` are a statutory multiplier defined by the Crimes Act 1914. One penalty unit = AUD $313 (as of 2024). lex-au v0.4.0 will add `<quantity>` markup to capture the unit count as structured data.

---

## Schedules

Schedules appear after the main body of an Act and contain supplementary material. They are emitted as `<attachments>` in AKN 3.0.

```xml
<attachments>
  <attachment>
    <hcontainer name="schedule" eId="schedule-1">
      <heading>Schedule 1 — Australian Privacy Principles</heading>
      ...
    </hcontainer>
  </attachment>
</attachments>
```

### Schedule Clause Numbering

Most schedules use dot-separated clause numbering:

| Pattern | Example | AKN element | eId |
|---|---|---|---|
| Top-level clause | `1  Definitions` | `<hcontainer name="clause">` | `schedule-1__clause-1` |
| Subclause | `1.1  The object of this APP...` | `<hcontainer name="subclause">` | `schedule-1__clause-1__subclause-1` |
| Sub-subclause | `1.2.1  have an up-to-date...` | `<hcontainer name="subclause">` | deeper nesting |
| Paragraph | `(a) text` | `<paragraph>` | `schedule-1__clause-1__para-a` |

### Australian Privacy Principles (APP)

Privacy Act 1988 Schedule 1 uses an `APP N` prefix pattern:

| Pattern | Example |
|---|---|
| APP clause heading | `APP 1 — Open and transparent management...` |
| APP subclause | `APP 1.1  The object of this APP is...` |
| APP paragraph | `1.2  To satisfy this APP, an APP entity must...` followed by `(a)(b)` items |

lex-au detects these with `_APP_CLAUSE_RE = re.compile(r'^APP\s+(\d+(?:\.\d+)*)\s+([A-Z].*)')`.

The 13 Australian Privacy Principles are the most-queried obligations in the corpus. Correct clause-level addressing is critical for downstream rule extraction (ClauseKit) and the bereavement navigator.

---

## Multi-Volume Acts

Some large Acts are published as multiple DOCX volumes. lex-au fetches all volumes and concatenates their paragraph streams before parsing.

| Act | Volumes |
|---|---|
| Income Tax Assessment Act 1997 | 12 |
| Corporations Act 2001 | 7 |
| Fair Work Act 2009 | 4 |
| Criminal Code Act 1995 | 3 |
| Social Security Act 1991 | 6 |
| Superannuation Industry (Supervision) Act 1993 | 2 |

Volume detection: `legislation.gov.au` Documents API returns `volumeNumber` per DOCX. lex-au fetches all volumes in order and concatenates before parsing.

---

## Citation Patterns

lex-au's `reflinks.py` post-processor injects `<ref>` elements into `<p>` text. Patterns matched:

| Pattern | Example | Resolution | Kind |
|---|---|---|---|
| Section + subsection + paragraph | `s 6(1)(a)` | `#sec-6__subsec-1__para-a` | `sec_subsec_para` |
| Section + subsection | `s 16(2)` | `#sec-16__subsec-2` | `sec_subsec` |
| Section only | `section 16` or `s 16` | `#sec-16` | `sec` |
| Part intra-Act | `Part III` | `#part-III` | `part_div` |
| Division intra-Act | `Division 3` | `#dvs-3` | `part_div` |
| Definitional ref | `within the meaning of section 6` | `#sec-6` | `def_ref` |
| Subsidiary legislation | `the Privacy (Tax File Numbers) Rule 2015` | corpus lookup (unresolved if not in corpus) | `subsidiary` |
| Cross-Act | `the Privacy Act 1988` | FRBR URI from corpus index | `act` |

Quoted text is excluded from pattern matching to avoid false positives on cited Act names in quotations.

---

## FRBR URIs

lex-au constructs FRBR URIs using Laws.Africa's `cobalt` library. Format:

```
Work:       /akn/au/act/1988/119/
Expression: /akn/au/act/1988/119/eng@2024-11-15/
```

Components:
- `au` — country code (FRBR jurisdiction)
- `act` — document type
- `1988` — year of enactment
- `119` — Act number from legislation.gov.au `titleId` field (e.g., `C1988A00119` → `119`)
- `eng` — language
- `@2024-11-15` — compilation date (from legislation.gov.au `start` field)

Section addressing appends `#eId`: `/akn/au/act/1988/119/eng@2024-11-15/!main#sec-16__subsec-1`.
