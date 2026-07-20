# Doc-conversion 5-Act spot-check

5 Acts selected per the plan: indices 0, 3, 6, 9, 12 of the 15-entry
substantive-only ordering in `corpus/reports/doc-conversion-sample.json`'s
`sample` list (spans pre-1970 / 1970s-90s / 2000s+ eras). For each, the
generated XML at `corpus/doc_spike/spike_xml/{safe_name}.xml` (Task 3
output) was compared against the current text on legislation.gov.au
(Federal Register of Legislation), fetched live 2026-07-20.

| Act | Sections in XML | Boundaries match govt text? | Notes |
|-----|-----------------|------------------------------|-------|
| Antarctic Treaty Act 1960 | 4 (ss 1-4: Short title, Commencement, Interpretation, Provisions to give effect to the Treaty) + Schedule (the Treaty text) | yes | legislation.gov.au C2008C00398 lists identical 4 sections + Schedule in the same order and with matching headings. XML compilation date (4 Jul 2008) matches the govt compilation exactly. Section 3 has 2 subsections, section 4 has 4 subsections in the XML — consistent with the govt TOC structure (govt Details page doesn't expose subsection-level TOC, so subsection count wasn't independently cross-checked, only section-level). |
| Parliamentary Papers Act 1908 | 6 sections (ss 1, 1A, 2-6: Short title, Interpretation, Publication of Parliamentary Papers, Authority to Government Printer to publish, No action for publishing Parliamentary Papers, Application of Act, Privileges of Parliament not affected) | yes | legislation.gov.au C1908A00016 lists the identical section sequence including the 1A insertion between ss 1 and 2. Headings match verbatim. Caveat: the XML is the 1 May 1981 historical compilation (per its own `FRBRExpression` date), not the Act's current/latest compiled version on legislation.gov.au — boundary structure matches for the version compiled, but Task 3's spike source may not be pulling the current compilation for all Acts. Worth flagging for Phase 2 sourcing logic. |
| Australian National Railways Commission Sale Act 1997 | none — Task 3 conversion failed for this Act (`magic: "unknown"`, error `unrecognized format, first 4 bytes: b'{\rt'`, no XML produced) | n/a — cannot verify, no XML exists | legislation.gov.au C2004C00908 confirms the Act exists and has a simple 3-section structure (Short title, Commencement, Schedule(s), with Schedule 1 inserting Part VA into the Australian National Railways Commission Act 1983 across ~10 divisions). This is itself a genuine Task 3 finding: at least one of the 5 spot-check Acts hit a conversion failure the spike's binary magic-byte sniffing didn't handle (looks like an RTF payload mislabelled/misdetected rather than a clean legacy .doc). Flag for Task 5's go/no-go: the reported non-empty-body rate should already reflect this as a failure, but it's worth confirming this specific failure mode (RTF-in-.doc) is accounted for in the rate, not silently dropped from the denominator. |
| Seafarers Rehabilitation and Compensation Levy Act 1992 | 7 sections (ss 1-7: Short title, Commencement, Interpretation, Imposition of levy, Rate of levy, Who pays levy?, Regulations) | yes | legislation.gov.au C2004C00281 lists the identical 7-section sequence with matching headings. XML compilation date (18 Jan 1994) matches the govt compilation. Section 7 subsections (1)-(3) in the XML match the govt structure (regulation-making power, consultation requirement, non-invalidation clause). |
| Fisheries (Validation of Plans of Management) Act 2004 | 3 sections (ss 1-3: Short title, Commencement, Plans of management) | yes | legislation.gov.au C2004A01393 (current/latest text) lists the identical 3-section sequence with matching headings. Section 3 in the XML has 4 subsections (purpose statement, validation of Managing-Director-made plans, validation of amendments/revocations, validation of things done under such plans) — consistent with the Act's known short curative-validation structure; govt Details/TOC page doesn't expose subsection-level detail, so subsection count is corroborated by content plausibility rather than a second independent source. |

## Summary

4 of 5 Acts: section numbers, headings, and (where checkable) subsection
boundaries in the Task 3 XML match the current or historical
legislation.gov.au text with no discrepancies found. 1 of 5
(Australian National Railways Commission Sale Act 1997) could not be
checked because Task 3's conversion failed outright for that Act — no
XML was produced, so there is nothing to compare. This is not a "no"
boundary-match verdict in the sense of a structural mismatch; it's an
absence-of-artifact case, and is flagged separately above rather than
guessed at.

One version-currency caveat: the Parliamentary Papers Act 1908 XML
reflects an old (1981) compilation rather than the Act's current
version on legislation.gov.au. The two happen to have identical section
structure for this particular Act (the 1981-2026 gap added no further
amendments to this short Act), so the boundary-match verdict still
holds, but this shows Task 3's source .doc selection isn't guaranteed
to be the *current* compilation — worth a note for Task 5/7 if currency
matters for downstream use.
