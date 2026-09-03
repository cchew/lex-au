# DOCX-to-AKN Fidelity Audit: Summary

Generated: 2026-09-03T19:06:17+1000
Wall-clock: 310.2s

- Acts scanned: 3076
- Acts skipped (no docx, no xml, or read error): 0
- Acts with at least one non-minor divergence: 2861

> How to read this. Both sides are paragraph text: DOCX `<w:p>` runs
> against AKN `<p>`, `<heading>` and `<td>`. `reorder` (same tokens, new
> order) is the one clean signal: it isolates the `_process_p`
> cross-reference relocation bug, now fixed, so this total is small and is
> dominated by a difflib artefact (a moved-and-lightly-edited paragraph
> split into a delete plus an insert, and DOCX `<w:p>` runs segmented at a
> different granularity from the AKN `<td>` cells they map to), not by
> genuine out-of-order text. `drop_text`, `drop_para` and `spurious_para`
> are NOT resolvable from these totals and must not be read as a
> conversion-loss count. Schedule tables are now rendered into the AKN, so
> the tariff, appropriation, supply and repeal Acts that previously showed
> a wholesale schedule omission here (their operative rate and item tables
> absent from the XML) no longer do: `customs-tariff-act-1995` alone moved
> from ~3.8k AKN body paragraphs to ~46k, and its `drop_para` fell from
> ~48.5k to ~0.7k. What remains in these three modes still combines, in
> unknown proportion: genuine loss; DOCX-run vs AKN-cell segmentation
> mismatch across the now-compared table content; AKN front-matter and
> per-volume residue repeated as `spurious_para`; and difflib split of a
> moved paragraph. AKN content with no paragraph or cell text (nested
> tables, `<foreign>`, math) stays invisible to the diff. Per-Act
> genuineness needs the per-Act JSON plus an XML content probe; the audit
> report carries that read for the worst-20.

## DOCX resolution modes (scanned acts)

- comp-vol: 2968 acts
- legacy-vol: 108 acts

## Paragraph totals by mode

Paragraphs affected, summed across acts (wider side of each divergence).

- reorder: 939 paragraphs
- drop_text: 109075 paragraphs
- drop_para: 51268 paragraphs
- spurious_para: 70996 paragraphs
- minor: 70979 paragraphs

## Acts affected by mode

- reorder: 82 acts
- drop_text: 2353 acts
- drop_para: 2481 acts
- spurious_para: 1678 acts
- minor: 1263 acts

## Worst 20 acts (non-minor divergent paragraphs)

| rank | slug | non-minor paras | reorder | drop_text | drop_para | spurious_para | docx mode |
|---|---|---|---|---|---|---|---|
| 1 | superannuation-industry-(supervision)-regulations-1994 | 13691 | 0 | 7051 | 6487 | 153 | comp-vol |
| 2 | social-security-act-1991 | 13182 | 2 | 10657 | 269 | 2254 | comp-vol |
| 3 | income-tax-assessment-act-1997 | 10802 | 131 | 4928 | 663 | 5080 | comp-vol |
| 4 | civil-aviation-safety-regulations-1998 | 7987 | 0 | 4107 | 133 | 3747 | comp-vol |
| 5 | corporations-act-2001 | 7426 | 9 | 1802 | 296 | 5319 | comp-vol |
| 6 | customs-tariff-amendment-(thailand-australia-free-trade-agreement-implementation)-act-2004 | 5826 | 0 | 5511 | 8 | 307 | comp-vol |
| 7 | migration-regulations-1994 | 4955 | 7 | 915 | 1534 | 2499 | comp-vol |
| 8 | corporations-regulations-2001 | 4787 | 16 | 2477 | 233 | 2061 | comp-vol |
| 9 | income-tax-assessment-act-1936 | 4353 | 66 | 2741 | 180 | 1366 | comp-vol |
| 10 | customs-tariff-act-1995 | 3742 | 7 | 1666 | 679 | 1390 | comp-vol |
| 11 | competition-and-consumer-act-2010 | 3323 | 0 | 786 | 301 | 2236 | comp-vol |
| 12 | taxation-administration-act-1953 | 3033 | 19 | 454 | 549 | 2011 | comp-vol |
| 13 | social-security-(international-agreements)-act-1999 | 2876 | 0 | 382 | 1311 | 1183 | comp-vol |
| 14 | fair-work-act-2009 | 2868 | 0 | 808 | 137 | 1923 | comp-vol |
| 15 | offshore-petroleum-and-greenhouse-gas-storage-act-2006 | 2646 | 33 | 735 | 307 | 1571 | comp-vol |
| 16 | customs-tariff-amendment-act-(no.-2)-1987 | 2492 | 0 | 506 | 141 | 1845 | comp-vol |
| 17 | criminal-code-act-1995 | 2206 | 0 | 1340 | 42 | 824 | comp-vol |
| 18 | veterans'-entitlements-act-1986 | 1858 | 4 | 520 | 188 | 1146 | comp-vol |
| 19 | customs-act-1901 | 1835 | 0 | 404 | 102 | 1329 | comp-vol |
| 20 | telecommunications-act-1997 | 1624 | 0 | 231 | 181 | 1212 | comp-vol |
