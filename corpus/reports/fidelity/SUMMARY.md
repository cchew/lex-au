# DOCX-to-AKN Fidelity Audit: Summary

Generated: 2026-09-25T17:37:54+1000
Wall-clock: 432.9s

- Acts scanned: 3084
- Acts skipped (no docx, no xml, or read error): 0
- Acts with at least one non-minor divergence: 2791

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

- comp-vol: 2977 acts
- legacy-vol: 107 acts

## Paragraph totals by mode

Paragraphs affected, summed across acts (wider side of each divergence).

- reorder: 0 paragraphs
- drop_text: 98073 paragraphs
- drop_para: 12942 paragraphs
- spurious_para: 58467 paragraphs
- minor: 71396 paragraphs

## Acts affected by mode

- reorder: 0 acts
- drop_text: 2279 acts
- drop_para: 676 acts
- spurious_para: 2326 acts
- minor: 1121 acts

## Worst 20 acts (non-minor divergent paragraphs)

| rank | slug | non-minor paras | reorder | drop_text | drop_para | spurious_para | docx mode |
|---|---|---|---|---|---|---|---|
| 1 | superannuation-industry-(supervision)-regulations-1994 | 13614 | 0 | 7044 | 6443 | 127 | comp-vol |
| 2 | social-security-act-1991 | 13115 | 0 | 10560 | 178 | 2377 | comp-vol |
| 3 | income-tax-assessment-act-1997 | 11041 | 0 | 4958 | 301 | 5782 | comp-vol |
| 4 | civil-aviation-safety-regulations-1998 | 7993 | 0 | 4079 | 53 | 3861 | comp-vol |
| 5 | corporations-act-2001 | 7280 | 0 | 1738 | 120 | 5422 | comp-vol |
| 6 | customs-tariff-amendment-(thailand-australia-free-trade-agreement-implementation)-act-2004 | 5813 | 0 | 5509 | 0 | 304 | comp-vol |
| 7 | corporations-regulations-2001 | 4377 | 0 | 2356 | 26 | 1995 | comp-vol |
| 8 | income-tax-assessment-act-1936 | 3919 | 0 | 2546 | 22 | 1351 | comp-vol |
| 9 | competition-and-consumer-act-2010 | 3234 | 0 | 659 | 470 | 2105 | comp-vol |
| 10 | fair-work-act-2009 | 2784 | 0 | 790 | 38 | 1956 | comp-vol |
| 11 | customs-tariff-act-1995 | 2484 | 0 | 1662 | 7 | 815 | comp-vol |
| 12 | offshore-petroleum-and-greenhouse-gas-storage-act-2006 | 2395 | 0 | 753 | 45 | 1597 | comp-vol |
| 13 | customs-tariff-amendment-act-(no.-2)-1987 | 2330 | 0 | 604 | 17 | 1709 | comp-vol |
| 14 | criminal-code-act-1995 | 2210 | 0 | 1329 | 28 | 853 | comp-vol |
| 15 | taxation-administration-act-1953 | 2103 | 0 | 322 | 6 | 1775 | comp-vol |
| 16 | migration-regulations-1994 | 2006 | 0 | 849 | 16 | 1141 | comp-vol |
| 17 | customs-act-1901 | 1835 | 0 | 365 | 101 | 1369 | comp-vol |
| 18 | veterans'-entitlements-act-1986 | 1585 | 0 | 458 | 41 | 1086 | comp-vol |
| 19 | environment-protection-and-biodiversity-conservation-act-1999 | 1352 | 0 | 255 | 18 | 1079 | comp-vol |
| 20 | telecommunications-act-1997 | 1322 | 0 | 215 | 10 | 1097 | comp-vol |

## Within-paragraph classification (§7)

`replace` opcodes are classified per aligned paragraph pair. Equal-length blocks pair positionally (Phase 1). Unequal-length blocks are best-match aligned within the block by casefolded \w-token overlap; any paragraph left unmatched on the longer side reports `wp_word_drop` (DOCX) or `wp_word_insert` (AKN) with the whole paragraph as the token list. A block whose paragraph count exceeds the pairwise-alignment cap on either side skips per-pair alignment and reports one whole-block `wp_block_skipped` classification instead, so a pathological block cannot blow up audit runtime.

- replace opcodes: 78002
- equal-length (positional pairs): 58834 (67023 paragraph-pairs)
- unequal-length (best-match aligned): 19168 (89894 paragraph-pairs), of which 21 (12333 paragraph-pairs) exceeded the alignment cap and fell back to `wp_block_skipped`
- coverage: 92.1% of replace paragraph mass classified pair-by-pair (excludes capped-fallback mass)

### Paragraph-pair counts by within-paragraph kind

- wp_block_skipped: 21 pairs
- wp_clean: 2 pairs
- wp_garble: 259 pairs
- wp_punct: 12979 pairs
- wp_skipped: 10830 pairs
- wp_word_drop: 92724 pairs
- wp_word_insert: 30042 pairs
- wp_word_reorder: 0 pairs

### Within outer kind `minor` (the headline)

- wp_block_skipped: 3 pairs
- wp_clean: 2 pairs
- wp_garble: 54 pairs
- wp_punct: 11757 pairs
- wp_skipped: 2075 pairs
- wp_word_drop: 42065 pairs
- wp_word_insert: 15211 pairs

### Worst 20 acts by (wp_garble + wp_word_drop)

| rank | slug | wp_garble | wp_word_drop | wp_word_insert | wp_word_reorder | wp_punct | docx mode |
|---|---|---|---|---|---|---|---|
| 1 | customs-tariff-act-1995 | 3 | 9014 | 3150 | 0 | 0 | comp-vol |
| 2 | customs-tariff-amendment-(regional-comprehensive-economic-partnership-agreement-implementation)-act-2021 | 0 | 5283 | 1804 | 0 | 0 | comp-vol |
| 3 | civil-aviation-safety-regulations-1998 | 20 | 3468 | 394 | 0 | 0 | comp-vol |
| 4 | income-tax-assessment-act-1997 | 12 | 2851 | 948 | 0 | 8867 | comp-vol |
| 5 | customs-tariff-amendment-(japan-australia-economic-partnership-agreement-implementation)-act-2014 | 0 | 2278 | 599 | 0 | 0 | comp-vol |
| 6 | customs-tariff-amendment-(korea-australia-free-trade-agreement-implementation)-act-2014 | 0 | 2106 | 577 | 0 | 0 | comp-vol |
| 7 | corporations-act-2001 | 10 | 1781 | 407 | 0 | 0 | comp-vol |
| 8 | corporations-regulations-2001 | 14 | 1767 | 375 | 0 | 2 | comp-vol |
| 9 | us-free-trade-agreement-implementation-(customs-tariff)-act-2004 | 0 | 1656 | 833 | 0 | 0 | comp-vol |
| 10 | customs-tariff-amendment-(thailand-australia-free-trade-agreement-implementation)-act-2004 | 0 | 1542 | 1969 | 0 | 0 | comp-vol |
| 11 | customs-tariff-amendment-(china-australia-free-trade-agreement-implementation)-act-2015 | 0 | 1291 | 535 | 0 | 0 | comp-vol |
| 12 | migration-regulations-1994 | 1 | 1131 | 314 | 0 | 0 | comp-vol |
| 13 | offshore-petroleum-and-greenhouse-gas-storage-act-2006 | 8 | 1004 | 218 | 0 | 0 | comp-vol |
| 14 | criminal-code-act-1995 | 0 | 989 | 82 | 0 | 0 | comp-vol |
| 15 | customs-(prohibited-imports)-regulations-1956 | 1 | 979 | 164 | 0 | 0 | comp-vol |
| 16 | customs-tariff-amendment-(comprehensive-and-progressive-agreement-for-trans-pacific-partnership-expansion)-act-2024 | 0 | 859 | 95 | 0 | 0 | comp-vol |
| 17 | fair-work-act-2009 | 4 | 803 | 190 | 0 | 0 | comp-vol |
| 18 | customs-tariff-amendment-(growing-australian-export-opportunities-across-the-asia-pacific)-act-2019 | 0 | 726 | 298 | 0 | 0 | comp-vol |
| 19 | therapeutic-goods-regulations-1990 | 1 | 723 | 210 | 0 | 0 | comp-vol |
| 20 | social-security-act-1991 | 0 | 718 | 203 | 0 | 0 | comp-vol |
