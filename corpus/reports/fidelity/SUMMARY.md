# DOCX-to-AKN Fidelity Audit: Summary

Generated: 2026-09-03T20:26:54+1000
Wall-clock: 317.9s

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
- drop_text: 108339 paragraphs
- drop_para: 45224 paragraphs
- spurious_para: 78466 paragraphs
- minor: 72385 paragraphs

## Acts affected by mode

- reorder: 0 acts
- drop_text: 2342 acts
- drop_para: 1861 acts
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
| 8 | corporations-regulations-2001 | 4698 | 0 | 2471 | 139 | 2088 | comp-vol |
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
