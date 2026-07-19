# Legacy Shape Discovery Notes

## Summary

Analysis of the 550 Acts with empty AKN bodies confirms exactly two distinct text shapes, found across multiple style-signature clusters. No third shape was discovered.

### Shape 1: Separate heading + numbered body
- A bold heading-only paragraph (e.g. "Short title.") immediately followed by a plain numbered paragraph (e.g. "1.\tThis Act may be cited as...") with NO subsection marker.
- The numbered paragraph begins with a number and tab, followed by the clause text.
- Appears across all style clusters, including the dominant "(no distinguishing style)" cluster (360 acts).
- Example fixture: `loan-act-(no.-2)-1976` (Cluster 7, Body Text styles).

### Shape 2: Fused section+subsection
- A single paragraph that combines section and subsection numbers into one line: e.g. "1. (1) This Act may be cited as...".
- The paragraph text includes both `N. (M) text` pattern in a single paragraph, with no separate heading preceding it.
- Also appears within the dominant "(no distinguishing style)" cluster, not confined to styled variants.
- Confirmed present in the corpus; fixture verification pending detailed spot-check against high-fused-rate clusters.

## Key Finding: Style Signature Does NOT Cleanly Separate the Shapes

The script clusters Acts by style-signature (which styles appear in a document). However, both Shape 1 and Shape 2 can appear within the same style-signature cluster. For example:
- The dominant Cluster 0 ("(no distinguishing style)", 360 acts) contains both shapes.
- Shape 2 is NOT confined to a small subset of styled documents; it appears mixed throughout the dominant cluster too.

**Implication:** The text-shape distinction (is the paragraph a fused "N. (M) text" pattern or a separate "N.\ttext" pattern) is a per-paragraph decision, not a per-cluster or per-document one. Regexes must detect shapes at the paragraph level, not rely on style clustering to pre-filter.

## Observations

No genuinely new text shapes were found. The two shapes match the specification. Task 3/4 implementers should:
1. Write paragraph-level regexes that can detect Shape 1 and Shape 2 within any document, regardless of style signature.
2. Not assume that style clustering pre-filters the shapes; both can appear in the same cluster.
3. Prioritize Shape 1 (separate heading + numbered body) as the most recognizable pattern for initial implementation.
