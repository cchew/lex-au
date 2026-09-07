# DOCX-to-AKN Fidelity Audit: Summary

Generated: 2026-09-08T09:25:11+1000
Wall-clock: 333.7s

- Acts scanned: 3076
- Acts skipped (no docx, no xml, or read error): 0
- Acts with at least one non-minor divergence: 2837

> How to read this. Both sides are paragraph text: DOCX `<w:p>` runs
> against AKN `<p>`, `<heading>`, `<td>` and `<th>`. `reorder` means the
> two sides carry the exact same token multiset in a different order. The
> `_process_p` cross-reference relocation bug that used to inflate it is
> fixed, and the classifier no longer routes near-identical replaces
> (overlap alone, different multiset) to `reorder`, so the corpus-wide
> total is now 0. Any `reorder` that reappears is genuine out-of-order
> text and should be read as such.
>
> The remaining residual, if `reorder` is ever non-zero again, is
> `_strip_markers` enumerator asymmetry: a leading `(1)`/`(a)`/section
> number stripped from one side but not the other leaves an otherwise
> near-identical replace whose token overlap is very high, which the
> classifier now sends to `minor` rather than `reorder`.
>
> `drop_text`, `drop_para` and `spurious_para` are NOT resolvable from
> these totals and must not be read as a conversion-loss count. Two things
> move them between runs and neither is attributable to the mapping code
> alone:
>
> 1. Source-DOCX refresh. The v0.9.0 `--force` re-ingest re-fetched
>    compilation-numbered DOCX, moving ~2,900 Acts from `legacy-vol` to
>    `comp-vol` (`docx_modes` comp-vol 40 -> 2,968). The `drop_text`,
>    `spurious_para` and `minor` deltas across that re-ingest therefore
>    blend the reflinks and schedule-table code fixes with a change of
>    source document, and cannot be pinned on the code.
> 2. Schedule tables are now rendered into the AKN (as `<td>`; body-path
>    tables also promote row 0 to `<th>`), so the tariff, appropriation,
>    supply, repeal and superannuation Acts that previously showed a
>    wholesale schedule omission here no longer do: `customs-tariff-act-
>    1995` alone moved from ~3.8k AKN body paragraphs to ~46k and its
>    `drop_para` fell from ~48.5k to ~0.7k. Adding `<th>` to the compared
>    set cut corpus `drop_para` by a further ~6k, with most of that text
>    resurfacing as `spurious_para`/`minor` because header-row cells rarely
>    align 1:1 with the DOCX run that carried them.
>
> What remains in these three modes still combines, in unknown proportion:
> genuine loss; DOCX-run vs AKN-cell segmentation mismatch across the
> now-compared table content; and AKN front-matter and per-volume residue
> repeated as `spurious_para`. AKN content with no paragraph or cell text
> (nested tables, `<foreign>`, math) stays invisible to the diff.
>
> Two Acts, `industrial-relations-court-(judges'-remuneration)-act-1993`
> and `royal-australian-air-force-veterans'-residences-act-1953`, still
> carry pre-v0.9.0 XML: a `_resolve_title` apostrophe fallback stopped the
> `--force` re-ingest re-converting them, so their rows reflect the old
> pipeline, not the current one.
>
> Per-Act genuineness needs the per-Act JSON plus an XML content probe;
> the audit report carries that read for the worst-20.

## DOCX resolution modes (scanned acts)

- comp-vol: 2968 acts
- legacy-vol: 108 acts

## Paragraph totals by mode

Paragraphs affected, summed across acts (wider side of each divergence).

- reorder: 0 paragraphs
- drop_text: 108294 paragraphs
- drop_para: 45122 paragraphs
- spurious_para: 78426 paragraphs
- minor: 72380 paragraphs

## Acts affected by mode

- reorder: 0 acts
- drop_text: 2342 acts
- drop_para: 1860 acts
- spurious_para: 2367 acts
- minor: 1274 acts

## Worst 20 acts (non-minor divergent paragraphs)

| rank | slug | non-minor paras | reorder | drop_text | drop_para | spurious_para | docx mode |
|---|---|---|---|---|---|---|---|
| 1 | superannuation-industry-(supervision)-regulations-1994 | 13731 | 0 | 7091 | 6487 | 153 | comp-vol |
| 2 | social-security-act-1991 | 13213 | 0 | 10597 | 208 | 2408 | comp-vol |
| 3 | income-tax-assessment-act-1997 | 11047 | 0 | 4967 | 302 | 5778 | comp-vol |
| 4 | civil-aviation-safety-regulations-1998 | 8015 | 0 | 4098 | 55 | 3862 | comp-vol |
| 5 | corporations-act-2001 | 7466 | 0 | 1792 | 202 | 5472 | comp-vol |
| 6 | customs-tariff-amendment-(thailand-australia-free-trade-agreement-implementation)-act-2004 | 5827 | 0 | 5511 | 7 | 309 | comp-vol |
| 7 | migration-regulations-1994 | 4931 | 0 | 910 | 1506 | 2515 | comp-vol |
| 8 | corporations-regulations-2001 | 4706 | 0 | 2471 | 143 | 2092 | comp-vol |
| 9 | income-tax-assessment-act-1936 | 4308 | 0 | 2731 | 154 | 1423 | comp-vol |
| 10 | customs-tariff-act-1995 | 3732 | 0 | 1666 | 676 | 1390 | comp-vol |
| 11 | competition-and-consumer-act-2010 | 3361 | 0 | 786 | 280 | 2295 | comp-vol |
| 12 | taxation-administration-act-1953 | 3017 | 0 | 454 | 547 | 2016 | comp-vol |
| 13 | fair-work-act-2009 | 2890 | 0 | 808 | 125 | 1957 | comp-vol |
| 14 | social-security-(international-agreements)-act-1999 | 2877 | 0 | 382 | 1310 | 1185 | comp-vol |
| 15 | offshore-petroleum-and-greenhouse-gas-storage-act-2006 | 2737 | 0 | 767 | 235 | 1735 | comp-vol |
| 16 | customs-tariff-amendment-act-(no.-2)-1987 | 2330 | 0 | 604 | 17 | 1709 | comp-vol |
| 17 | criminal-code-act-1995 | 2221 | 0 | 1340 | 28 | 853 | comp-vol |
| 18 | veterans'-entitlements-act-1986 | 1844 | 0 | 498 | 160 | 1186 | comp-vol |
| 19 | customs-act-1901 | 1836 | 0 | 403 | 100 | 1333 | comp-vol |
| 20 | telecommunications-act-1997 | 1628 | 0 | 231 | 176 | 1221 | comp-vol |

## Within-paragraph classification (§7)

Only `replace` opcodes whose two sides span an equal number of paragraphs are classified per positional pair; unequal-length blocks are still netted into one string by `compare()` and are out of scope here.

- replace opcodes: 83956
- equal-length (classified): 62727 (72127 paragraph-pairs)
- unequal-length (not classified): 21229 (94811 paragraph-pairs)
- coverage: 43.2% of replace paragraph mass

### Paragraph-pair counts by within-paragraph kind

- wp_clean: 1442 pairs
- wp_garble: 1322 pairs
- wp_punct: 12514 pairs
- wp_skipped: 6704 pairs
- wp_word_drop: 45054 pairs
- wp_word_insert: 5091 pairs

### Within outer kind `minor` (the headline)

- wp_clean: 1414 pairs
- wp_garble: 65 pairs
- wp_punct: 11463 pairs
- wp_skipped: 299 pairs
- wp_word_drop: 67 pairs
- wp_word_insert: 96 pairs

### Worst 20 acts by (wp_garble + wp_word_drop)

| rank | slug | wp_garble | wp_word_drop | wp_word_insert | wp_word_reorder | wp_punct | docx mode |
|---|---|---|---|---|---|---|---|
| 1 | civil-aviation-safety-regulations-1998 | 16 | 2901 | 67 | 0 | 0 | comp-vol |
| 2 | corporations-regulations-2001 | 7 | 1404 | 57 | 0 | 0 | comp-vol |
| 3 | corporations-act-2001 | 12 | 1299 | 97 | 0 | 0 | comp-vol |
| 4 | income-tax-assessment-act-1997 | 6 | 1075 | 80 | 0 | 8708 | comp-vol |
| 5 | criminal-code-act-1995 | 3 | 949 | 56 | 0 | 0 | comp-vol |
| 6 | agricultural-and-veterinary-chemicals-legislation-amendment-act-2013 | 0 | 624 | 1 | 0 | 0 | comp-vol |
| 7 | competition-and-consumer-act-2010 | 5 | 615 | 44 | 0 | 0 | comp-vol |
| 8 | migration-regulations-1994 | 2 | 505 | 68 | 0 | 0 | comp-vol |
| 9 | social-security-act-1991 | 10 | 494 | 37 | 0 | 0 | comp-vol |
| 10 | aviation-transport-security-regulations-2005 | 5 | 494 | 14 | 0 | 0 | comp-vol |
| 11 | fair-work-act-2009 | 0 | 423 | 16 | 0 | 0 | comp-vol |
| 12 | income-tax-assessment-act-1936 | 13 | 406 | 34 | 0 | 0 | comp-vol |
| 13 | environment-protection-and-biodiversity-conservation-act-1999 | 0 | 372 | 13 | 0 | 0 | comp-vol |
| 14 | offshore-petroleum-and-greenhouse-gas-storage-act-2006 | 1 | 344 | 36 | 0 | 0 | comp-vol |
| 15 | crimes-act-1914 | 4 | 330 | 47 | 0 | 0 | comp-vol |
| 16 | customs-act-1901 | 11 | 312 | 42 | 0 | 0 | comp-vol |
| 17 | therapeutic-goods-(medical-devices)-regulations-2002 | 1 | 314 | 9 | 0 | 0 | comp-vol |
| 18 | family-law-act-1975 | 1 | 284 | 23 | 0 | 0 | comp-vol |
| 19 | income-tax-(transitional-provisions)-act-1997 | 0 | 251 | 8 | 0 | 0 | comp-vol |
| 20 | migration-act-1958 | 3 | 248 | 23 | 0 | 0 | comp-vol |
