# DOCX-to-AKN Fidelity Audit: Summary

Generated: 2026-09-02T07:54:06+1000
Wall-clock: 403.4s

- Acts scanned: 3076
- Acts skipped (no docx, no xml, or read error): 0
- Acts with at least one non-minor divergence: 2931

> How to read this. Both sides are paragraph text: DOCX `<w:p>` runs
> against AKN `<p>`, `<heading>` and `<td>`. `reorder` (same tokens, new
> order) is the one clean signal: it isolates the `_process_p`
> cross-reference bug. `drop_text`, `drop_para` and `spurious_para` are NOT
> resolvable from these totals and must not be read as a conversion-loss
> count. Each combines, in unknown proportion: genuine loss; whole schedules
> the AKN omits (in the worst-20 the tariff, appropriation, supply and
> repeal Acts lose their entire operative schedule this way, and `<td>`
> inclusion does not recover them because the cells are absent from the XML,
> not just uncompared); AKN front-matter and per-volume residue repeated as
> `spurious_para`; and difflib splitting one moved paragraph into a delete
> plus an insert. AKN content with no paragraph or cell text (nested tables,
> `<foreign>`, math) stays invisible to the diff. Per-Act genuineness needs
> the per-Act JSON plus an XML content probe; the audit report carries that
> read for the worst-20.

## DOCX resolution modes (scanned acts)

- comp-vol: 40 acts
- legacy-vol: 3036 acts

## Paragraph totals by mode

Paragraphs affected, summed across acts (wider side of each divergence).

- reorder: 20096 paragraphs
- drop_text: 115344 paragraphs
- drop_para: 342983 paragraphs
- spurious_para: 114042 paragraphs
- minor: 34680 paragraphs

## Acts affected by mode

- reorder: 1868 acts
- drop_text: 2397 acts
- drop_para: 2491 acts
- spurious_para: 1891 acts
- minor: 1579 acts

## Worst 20 acts (non-minor divergent paragraphs)

| rank | slug | non-minor paras | reorder | drop_text | drop_para | spurious_para | docx mode |
|---|---|---|---|---|---|---|---|
| 1 | customs-tariff-act-1995 | 53892 | 23 | 3979 | 48530 | 1360 | comp-vol |
| 2 | migration-regulations-1994 | 20189 | 68 | 1659 | 11064 | 7398 | comp-vol |
| 3 | social-security-act-1991 | 13607 | 166 | 10721 | 382 | 2338 | comp-vol |
| 4 | family-law-(superannuation)-regulations-2025 | 12534 | 24 | 499 | 11934 | 77 | legacy-vol |
| 5 | income-tax-assessment-act-1997 | 12077 | 1275 | 5992 | 654 | 4156 | comp-vol |
| 6 | customs-tariff-amendment-(regional-comprehensive-economic-partnership-agreement-implementation)-act-2021 | 10834 | 0 | 15 | 10814 | 5 | legacy-vol |
| 7 | customs-tariff-amendment-(thailand-australia-free-trade-agreement-implementation)-act-2004 | 10801 | 5 | 38 | 10728 | 30 | legacy-vol |
| 8 | corporations-act-2001 | 10198 | 329 | 1948 | 2348 | 5573 | comp-vol |
| 9 | civil-aviation-safety-regulations-1998 | 8069 | 32 | 4157 | 133 | 3747 | comp-vol |
| 10 | taxation-administration-act-1953 | 7657 | 218 | 2273 | 3210 | 1956 | comp-vol |
| 11 | corporations-regulations-2001 | 6171 | 67 | 2674 | 1648 | 1782 | comp-vol |
| 12 | appropriation-act-(no.-1)-2026‑2027 | 5785 | 3 | 9 | 5773 | 0 | legacy-vol |
| 13 | appropriation-act-(no.-1)-2025-2026 | 5682 | 3 | 4 | 5675 | 0 | legacy-vol |
| 14 | supply-act-(no.-1)-2025-2026 | 5612 | 3 | 7 | 5602 | 0 | legacy-vol |
| 15 | amending-acts-1901-to-1969-repeal-act-2014 | 5607 | 0 | 0 | 5607 | 0 | legacy-vol |
| 16 | appropriation-act-(no.-1)-2024-2025 | 5604 | 3 | 9 | 5592 | 0 | legacy-vol |
| 17 | income-tax-assessment-act-1936 | 5564 | 354 | 2999 | 471 | 1740 | comp-vol |
| 18 | appropriation-act-(no.-1)-2023-2024 | 5533 | 3 | 7 | 5523 | 0 | legacy-vol |
| 19 | us-free-trade-agreement-implementation-(customs-tariff)-act-2004 | 4633 | 2 | 16 | 4610 | 5 | legacy-vol |
| 20 | customs-tariff-amendment-(japan-australia-economic-partnership-agreement-implementation)-act-2014 | 4456 | 1 | 10 | 4437 | 8 | legacy-vol |
