#!/usr/bin/env python3
"""Audit DOCX-to-AKN text fidelity across the corpus.

Compares the visible paragraph text of each Act's source DOCX volumes against
the paragraph text of its generated Akoma Ntoso XML, using ``lexau.fidelity``.
Writes one JSON report per Act plus a corpus-wide SUMMARY.

Usage:
    python scripts/audit_conversion_fidelity.py [--corpus-dir corpus] [--limit N] [--slug SLUG]

DOCX resolution
---------------
``corpus/index.json`` records no docx->act mapping, so the source volumes for an
Act are derived from ``corpus/docx/`` filenames. The crawler
(``crawler.fetch_docx_volumes``) writes ``<slug>-c<comp_num>-vol<N>.docx``;
downloads predating comp_num-in-filename are ``<slug>-vol<N>.docx``; a small
number of Acts are a single unsuffixed ``<slug>.docx``. Preference order:

1. ``<slug>-c<comp_num>-vol<N>.docx`` for the index's current ``comp_num``
2. ``<slug>-c<any>-vol<N>.docx`` (a compilation, but not the index's)
3. ``<slug>-vol<N>.docx`` (legacy, no comp_num in filename)
4. ``<slug>.docx`` (single unsuffixed file)

Every candidate is re-checked against an anchored regex built from the escaped
slug, so a slug that is a textual prefix of a different Act's slug (for example
``fair-work-act-2009`` vs ``fair-work-(registered-organisations)-act-2009``)
cannot pull in the other Act's volumes. Volumes are ordered by their numeric
``vol`` index, not lexically, so ``vol10`` sorts after ``vol2``.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from lxml import etree

from lexau.fidelity import AKN_NS, Divergence, compare, docx_paragraphs, normalise

NON_MINOR_KINDS = ("reorder", "drop_text", "drop_para", "spurious_para")
ALL_KINDS = ("reorder", "drop_text", "drop_para", "spurious_para", "minor")
WP_KINDS = (
    "wp_clean",
    "wp_punct",
    "wp_word_drop",
    "wp_word_insert",
    "wp_word_reorder",
    "wp_garble",
    "wp_skipped",
    "wp_block_skipped",
)

_AKN_META = f"{{{AKN_NS}}}meta"
_AKN_P = f"{{{AKN_NS}}}p"
_AKN_HEADING = f"{{{AKN_NS}}}heading"
_AKN_TD = f"{{{AKN_NS}}}td"
_AKN_TH = f"{{{AKN_NS}}}th"
_AKN_BLOCK = f"{{{AKN_NS}}}block"
_AKN_COLLECT = (_AKN_P, _AKN_HEADING, _AKN_TD, _AKN_TH, _AKN_BLOCK)
_AKN_FINE = (_AKN_P, _AKN_HEADING)
_AKN_CELLISH = (_AKN_TD, _AKN_TH, _AKN_BLOCK)


def akn_paragraphs(root: etree._Element) -> list[str]:
    """Visible paragraph text of an AKN body, table cells included.

    ``lexau.fidelity.akn_paragraphs`` collects only ``<p>`` and ``<heading>``.
    Federal Register AKN also carries operative content in ``<td>`` and ``<th>``
    (rate tables, commencement tables, tariff and dose schedules; body-path
    tables promote row 0 to ``<th>``). Without them every converted table row
    scores ``drop_para`` against the DOCX whether or not the conversion kept it,
    so this audit cannot tell "table represented as cells" from "table dropped".

    Nearly every ``<td>``/``<th>``/``<block>`` in the corpus holds text directly
    with no element children; the small number that wrap a ``<p>`` or
    ``<heading>`` are skipped here so their text is taken once from the finer
    element, not twice.
    """
    out: list[str] = []
    for el in root.iter():
        if el.tag not in _AKN_COLLECT:
            continue
        if el.tag in _AKN_CELLISH and any(
            d.tag in _AKN_FINE for d in el.iterdescendants()
        ):
            continue
        anc = el.getparent()
        skip = False
        while anc is not None:
            if anc.tag == _AKN_META:
                skip = True
                break
            anc = anc.getparent()
        if skip:
            continue
        text = normalise("".join(el.itertext()))
        if text:
            out.append(text)
    return out

# --- Comparison-basis normalisation --------------------------------------------
#
# lexau.fidelity returns raw paragraph text from both sides. Two structural
# artefacts of Federal Register compilation DOCX otherwise swamp the real
# conversion divergences, so the audit strips them before diffing:
#
#   1. Front matter and endnotes. Each DOCX volume carries a "Contents"
#      table of provisions (every heading repeated with a trailing page number)
#      and, after the operative text, an endnote apparatus (legislation history,
#      amendment history) running to hundreds or thousands of paragraphs. The
#      generated AKN carries neither as operative body (it does repeat a short
#      compilation-description block). `_body_slice` drops the Contents block and
#      everything from the apparatus heading onward. The heading is a bare
#      "Endnotes" (modern format) or "Notes to the <Act>" (pre-2016); both also
#      occur in the volume list, so the real one is confirmed by its first item
#      ("Endnote 1" / "Note 1"). `_body_slice` runs once per DOCX volume, since
#      each volume has its own Contents and (for the last volume) its own
#      apparatus.
#   2. Enumerators and structural labels. The DOCX embeds "(1)", "(a)", the
#      section number ("3", "1-1", "15AB") and the "Part 1-1-", "Division 2-"
#      label in the paragraph text; AKN holds these in sibling <num> elements
#      that `akn_paragraphs` does not collect. `_strip_markers` removes the same
#      leading tokens from both sides so provisions align on their substantive
#      text.
#
# Both transforms are applied symmetrically to the DOCX and AKN paragraph lists.

_ENUM = re.compile(
    r"^(?:\((?:[0-9]{1,3}[A-Za-z]{0,3}|[a-z]{1,4}|[A-Z]{1,4}"
    r"|[ivxlcdm]{1,7}|[IVXLCDM]{1,7})\)[ \t ]+)+"
)
_LABEL = re.compile(
    r"^(?:Chapter|Part|Division|Subdivision|Schedule)\s+"
    r"[0-9A-Za-z‑–—-]+\s*[‑–—-]\s*"
)
_SECNUM = re.compile(
    r"^[0-9]{1,4}[A-Za-z]{0,3}(?:[‑–—-][0-9]{1,4}[A-Za-z]{0,3})*[ \t ]+"
)
_PAGE_TAIL = re.compile(r"[ \t ]\d{1,4}$")


def _strip_markers(s: str) -> str:
    prev = None
    while prev != s:
        prev = s
        s = _ENUM.sub("", s)
    s = _LABEL.sub("", s)
    # A bare leading section number is only stripped from heading-like paragraphs
    # (short, no terminal sentence punctuation) so body sentences that happen to
    # open with a numeral ("51 of the Constitution ...") are left intact.
    if len(s.split()) <= 10 and not s.rstrip().endswith((".", ":", ";", ",")):
        s = _SECNUM.sub("", s)
    return s.strip()


# Heading that starts the endnote apparatus at the end of a volume: a bare
# "Endnotes" (modern Federal Register format) or "Notes to the <Act title>"
# (pre-2016 format). Both also appear in the compilation front matter, where a
# bare "Endnotes" sits in the volume list; the earlier pattern also matched any
# line reading "note to the ..." (a provision such as "Notes to the accounts"),
# and a fixed 30% offset skipped the real heading in the schedules-and-endnotes
# final volume of large compilations while still catching front-matter copies.
# The real apparatus is disambiguated by its first item: "Endnote 1" / "Note 1".
_APPARATUS_HEAD = re.compile(r"(?i)^(?:endnotes|notes to the .+)$")
_APPARATUS_FIRST_ITEM = re.compile(r"(?i)^(?:endnote|note) \d")


def _body_slice(paras: list[str]) -> list[str]:
    n = len(paras)
    hi = n
    for i in range(n - 1):
        if not _APPARATUS_HEAD.match(paras[i].strip().rstrip(".")):
            continue
        j = i + 1
        while j < n and not paras[j].strip():
            j += 1
        if j < n and _APPARATUS_FIRST_ITEM.match(paras[j].strip()):
            hi = i
            break
    lo = 0
    for i in range(min(n, 400)):
        if paras[i].strip() == "Contents":
            j = i + 1
            while j < hi:
                p = paras[j].strip()
                if (
                    p
                    and not _PAGE_TAIL.search(paras[j])
                    and not p[0].islower()
                    and not re.match(r"(?i)^(endnote|notes\b|note\s)", p)
                ):
                    break
                j += 1
            lo = j
            break
    return paras[lo:hi]


def _normalise_paras(paras: list[str]) -> list[str]:
    return [t for t in (_strip_markers(p) for p in _body_slice(paras)) if t]


def _docx_body_paras(docx_paths: list[Path]) -> list[str]:
    """Normalised body paragraphs across an Act's DOCX volumes.

    Each Federal Register volume carries its own Contents block and its own
    endnote apparatus, so the front/back-matter trim in ``_body_slice`` has to
    run once per volume. Running it over the concatenation of all volumes finds
    only the first apparatus heading past the 30% mark and silently discards
    every later volume, so a 7-volume Act was being compared on volumes 1-3.
    """
    body: list[str] = []
    for p in docx_paths:
        body.extend(_body_slice(docx_paragraphs([p])))
    return [t for t in (_strip_markers(x) for x in body) if t]


def _sorted_by_vol(paths: list[Path]) -> list[Path]:
    def key(p: Path) -> tuple[int, str]:
        m = re.search(r"-vol(\d+)\.docx$", p.name)
        return (int(m.group(1)) if m else -1, p.name)

    return sorted(paths, key=key)


def _docx_paths(corpus_dir: Path, slug: str, entry: dict) -> tuple[list[Path], str]:
    """Return (ordered docx paths, resolution mode) for an Act.

    mode is one of: comp-vol, othercomp-vol, legacy-vol, single, none.
    """
    docx_dir = corpus_dir / "docx"
    esc = re.escape(slug)
    comp_num = entry.get("comp_num")

    if comp_num is not None:
        pat = re.compile(rf"^{esc}-c{re.escape(str(comp_num))}-vol\d+\.docx$")
        hits = [p for p in docx_dir.glob(f"{slug}-c*-vol*.docx") if pat.match(p.name)]
        if hits:
            return _sorted_by_vol(hits), "comp-vol"

    any_comp = re.compile(rf"^{esc}-c(\d+)-vol\d+\.docx$")
    comp_hits: dict[int, list[Path]] = {}
    for p in docx_dir.glob(f"{slug}-c*-vol*.docx"):
        m = any_comp.match(p.name)
        if m:
            comp_hits.setdefault(int(m.group(1)), []).append(p)
    if comp_hits:
        # Cache may hold volumes from several compilations; never mix them.
        # Take the single highest compilation number's volume set.
        highest = max(comp_hits)
        return _sorted_by_vol(comp_hits[highest]), "othercomp-vol"

    legacy = re.compile(rf"^{esc}-vol\d+\.docx$")
    hits = [p for p in docx_dir.glob(f"{slug}-vol*.docx") if legacy.match(p.name)]
    if hits:
        return _sorted_by_vol(hits), "legacy-vol"

    single = docx_dir / f"{slug}.docx"
    if single.exists():
        return [single], "single"

    return [], "none"


def _para_weight(d: Divergence) -> int:
    """Paragraphs affected by a divergence.

    A single difflib ``replace`` opcode can span several paragraphs on each
    side, so counting Divergence objects undercounts. Use the wider side for a
    replace; the deleted side for a drop; the inserted side for a spurious.
    """
    d_w = d.docx_span[1] - d.docx_span[0]
    a_w = d.akn_span[1] - d.akn_span[0]
    if d.kind == "drop_para":
        return d_w
    if d.kind == "spurious_para":
        return a_w
    return max(d_w, a_w)


def _audit_act(xml_path: Path, docx_paths: list[Path]) -> tuple[list[Divergence], int, int]:
    root = etree.parse(str(xml_path)).getroot()
    docx_paras = _docx_body_paras(docx_paths)
    akn_paras = _normalise_paras(akn_paragraphs(root))
    return compare(docx_paras, akn_paras), len(docx_paras), len(akn_paras)


_CAVEAT = (
    "> How to read this. Both sides are paragraph text: DOCX `<w:p>` runs\n"
    "> against AKN `<p>`, `<heading>`, `<td>` and `<th>`. `reorder` means the\n"
    "> two sides carry the exact same token multiset in a different order. The\n"
    "> `_process_p` cross-reference relocation bug that used to inflate it is\n"
    "> fixed, and the classifier no longer routes near-identical replaces\n"
    "> (overlap alone, different multiset) to `reorder`, so the corpus-wide\n"
    "> total is now 0. Any `reorder` that reappears is genuine out-of-order\n"
    "> text and should be read as such.\n"
    ">\n"
    "> The remaining residual, if `reorder` is ever non-zero again, is\n"
    "> `_strip_markers` enumerator asymmetry: a leading `(1)`/`(a)`/section\n"
    "> number stripped from one side but not the other leaves an otherwise\n"
    "> near-identical replace whose token overlap is very high, which the\n"
    "> classifier now sends to `minor` rather than `reorder`.\n"
    ">\n"
    "> `drop_text`, `drop_para` and `spurious_para` are NOT resolvable from\n"
    "> these totals and must not be read as a conversion-loss count. Two things\n"
    "> move them between runs and neither is attributable to the mapping code\n"
    "> alone:\n"
    ">\n"
    "> 1. Source-DOCX refresh. The v0.9.0 `--force` re-ingest re-fetched\n"
    ">    compilation-numbered DOCX, moving ~2,900 Acts from `legacy-vol` to\n"
    ">    `comp-vol` (`docx_modes` comp-vol 40 -> 2,968). The `drop_text`,\n"
    ">    `spurious_para` and `minor` deltas across that re-ingest therefore\n"
    ">    blend the reflinks and schedule-table code fixes with a change of\n"
    ">    source document, and cannot be pinned on the code.\n"
    "> 2. Schedule tables are now rendered into the AKN (as `<td>`; body-path\n"
    ">    tables also promote row 0 to `<th>`), so the tariff, appropriation,\n"
    ">    supply, repeal and superannuation Acts that previously showed a\n"
    ">    wholesale schedule omission here no longer do: `customs-tariff-act-\n"
    ">    1995` alone moved from ~3.8k AKN body paragraphs to ~46k and its\n"
    ">    `drop_para` fell from ~48.5k to ~0.7k. Adding `<th>` to the compared\n"
    ">    set cut corpus `drop_para` by a further ~6k, with most of that text\n"
    ">    resurfacing as `spurious_para`/`minor` because header-row cells rarely\n"
    ">    align 1:1 with the DOCX run that carried them.\n"
    ">\n"
    "> What remains in these three modes still combines, in unknown proportion:\n"
    "> genuine loss; DOCX-run vs AKN-cell segmentation mismatch across the\n"
    "> now-compared table content; and AKN front-matter and per-volume residue\n"
    "> repeated as `spurious_para`. AKN content with no paragraph or cell text\n"
    "> (nested tables, `<foreign>`, math) stays invisible to the diff.\n"
    ">\n"
    "> Two Acts, `industrial-relations-court-(judges'-remuneration)-act-1993`\n"
    "> and `royal-australian-air-force-veterans'-residences-act-1953`, still\n"
    "> carry pre-v0.9.0 XML: a `_resolve_title` apostrophe fallback stopped the\n"
    "> `--force` re-ingest re-converting them, so their rows reflect the old\n"
    "> pipeline, not the current one.\n"
    ">\n"
    "> Per-Act genuineness needs the per-Act JSON plus an XML content probe;\n"
    "> the audit report carries that read for the worst-20."
)


def _render_md(s: dict) -> str:
    def _table(pairs: list[tuple[str, int]], unit: str) -> list[str]:
        return [f"- {k}: {v} {unit}".rstrip() for k, v in pairs]

    totals = s["paragraph_totals_by_mode"]
    affected = s["acts_affected_by_mode"]
    lines = [
        "# DOCX-to-AKN Fidelity Audit: Summary",
        "",
        f"Generated: {s['generated_at']}",
        f"Wall-clock: {s['wall_clock_seconds']}s",
        "",
        f"- Acts scanned: {s['acts_scanned']}",
        f"- Acts skipped (no docx, no xml, or read error): {s['acts_skipped']}",
        f"- Acts with at least one non-minor divergence: {s['acts_with_nonminor']}",
        "",
        _CAVEAT,
        "",
        "## DOCX resolution modes (scanned acts)",
        "",
        *_table(sorted(s["docx_modes"].items()), "acts"),
        "",
        "## Paragraph totals by mode",
        "",
        "Paragraphs affected, summed across acts (wider side of each divergence).",
        "",
        *_table([(k, totals.get(k, 0)) for k in ALL_KINDS], "paragraphs"),
        "",
        "## Acts affected by mode",
        "",
        *_table([(k, affected.get(k, 0)) for k in ALL_KINDS], "acts"),
        "",
        "## Worst 20 acts (non-minor divergent paragraphs)",
        "",
        "| rank | slug | non-minor paras | reorder | drop_text | drop_para | spurious_para | docx mode |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for i, w in enumerate(s["worst_20"], 1):
        bm = w["by_mode"]
        lines.append(
            f"| {i} | {w['slug']} | {w['nonminor_paragraphs']} | "
            f"{bm.get('reorder', 0)} | {bm.get('drop_text', 0)} | "
            f"{bm.get('drop_para', 0)} | {bm.get('spurious_para', 0)} | {w['docx_mode']} |"
        )
    lines.append("")

    if "within_para" in s:
        wp = s["within_para"]
        cov = wp["coverage"]
        classified_pct = 100.0 * cov.get("classified_fraction", 0.0)
        minor_row = wp["by_outer_kind"].get("minor", {})
        lines += [
            "## Within-paragraph classification (§7)",
            "",
            "`replace` opcodes are classified per aligned paragraph pair. "
            "Equal-length blocks pair positionally (Phase 1). Unequal-length "
            "blocks are best-match aligned within the block by casefolded "
            "\\w-token overlap; any paragraph left unmatched on the longer side "
            "reports `wp_word_drop` (DOCX) or `wp_word_insert` (AKN) with the "
            "whole paragraph as the token list. A block whose paragraph count "
            "exceeds the pairwise-alignment cap on either side skips per-pair "
            "alignment and reports one whole-block `wp_block_skipped` "
            "classification instead, so a pathological block cannot blow up "
            "audit runtime.",
            "",
            f"- replace opcodes: {cov['replace_opcodes']}",
            f"- equal-length (positional pairs): {cov['equal_len']} "
            f"({cov['equal_len_para_mass']} paragraph-pairs)",
            f"- unequal-length (best-match aligned): {cov['unequal_len']} "
            f"({cov['unequal_len_para_mass']} paragraph-pairs), of which "
            f"{cov.get('unequal_len_capped', 0)} "
            f"({cov.get('unequal_len_capped_para_mass', 0)} paragraph-pairs) "
            "exceeded the alignment cap and fell back to `wp_block_skipped`",
            f"- coverage: {classified_pct:.1f}% of replace paragraph mass "
            "classified pair-by-pair (excludes capped-fallback mass)",
            "",
            "### Paragraph-pair counts by within-paragraph kind",
            "",
            *_table(sorted(wp["totals"].items()), "pairs"),
            "",
            "### Within outer kind `minor` (the headline)",
            "",
            *(_table(sorted(minor_row.items()), "pairs") or ["- (none)"]),
            "",
            "### Worst 20 acts by (wp_garble + wp_word_drop)",
            "",
            "| rank | slug | wp_garble | wp_word_drop | wp_word_insert | "
            "wp_word_reorder | wp_punct | docx mode |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for i, w in enumerate(wp.get("worst_20", []), 1):
            lines.append(
                f"| {i} | {w['slug']} | {w['wp_garble']} | {w['wp_word_drop']} | "
                f"{w.get('wp_word_insert', 0)} | {w.get('wp_word_reorder', 0)} | "
                f"{w.get('wp_punct', 0)} | {w['docx_mode']} |"
            )
        lines.append("")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus-dir", type=Path, default=Path("corpus"))
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--slug", default=None)
    ap.add_argument("--progress-every", type=int, default=100)
    ap.add_argument(
        "--no-within-para",
        action="store_false",
        dest="within_para",
        default=True,
        help=(
            "suppress only the SUMMARY within-paragraph aggregation and the "
            "SUMMARY.md §7 section; compare() still populates "
            "Divergence.within_para and the per-Act JSON still serialises it"
        ),
    )
    args = ap.parse_args()

    corpus_dir: Path = args.corpus_dir
    index = json.loads((corpus_dir / "index.json").read_text())
    acts: dict = index["acts"] if isinstance(index, dict) and "acts" in index else index
    items = sorted(acts.items())
    if args.slug:
        items = [(k, v) for k, v in items if k == args.slug]
        if not items:
            print(f"no index entry for slug {args.slug!r}")
            return 2
    if args.limit:
        items = items[: args.limit]

    out_dir = corpus_dir / "reports" / "fidelity"
    out_dir.mkdir(parents=True, exist_ok=True)

    totals: Counter = Counter()
    acts_affected: Counter = Counter()
    docx_modes: Counter = Counter()
    worst: list[dict] = []
    skipped: list[dict] = []
    scanned = 0
    acts_with_nonminor = 0
    start = time.time()

    # --- §7 within-paragraph aggregation (equal- and unequal-length replace
    # blocks; unequal-length blocks above the alignment cap fall back to one
    # wp_block_skipped classification per block, see fidelity._align_replace_block) ---
    wp_totals: Counter = Counter()               # per within_para.kind, 1 per pair
    wp_by_outer: dict[str, Counter] = {}         # outer Divergence.kind -> Counter
    wp_worst: list[dict] = []                    # per-Act, for the worst-20 table
    replace_opcode_total = 0
    replace_equal_len = 0
    replace_unequal_len = 0
    replace_equal_len_para_mass = 0
    replace_unequal_len_para_mass = 0
    replace_unequal_len_capped = 0          # unequal blocks over the alignment cap
    replace_unequal_len_capped_para_mass = 0
    _REPLACE_KINDS = ("minor", "reorder", "drop_text")

    for n, (slug, entry) in enumerate(items, 1):
        xml_rel = entry.get("xml_path", f"xml/{slug}.xml")
        xml_path = corpus_dir / xml_rel
        docx_paths, mode = _docx_paths(corpus_dir, slug, entry)

        if not xml_path.exists() or not docx_paths:
            reason = "no-xml" if not xml_path.exists() else "no-docx"
            skipped.append({"slug": slug, "reason": reason, "docx_mode": mode})
            continue

        try:
            divs, n_docx_paras, n_akn_paras = _audit_act(xml_path, docx_paths)
        except Exception as e:  # noqa: BLE001 - one unreadable Act must not abort the run
            skipped.append(
                {"slug": slug, "reason": f"error:{type(e).__name__}", "docx_mode": mode}
            )
            print(f"  ! {slug}: {type(e).__name__}: {e}", flush=True)
            continue
        scanned += 1
        docx_modes[mode] += 1

        by_mode_paras: Counter = Counter()
        for d in divs:
            by_mode_paras[d.kind] += _para_weight(d)
        for k, v in by_mode_paras.items():
            totals[k] += v
        for k in {d.kind for d in divs}:
            acts_affected[k] += 1

        nonminor_paras = sum(by_mode_paras[k] for k in NON_MINOR_KINDS)
        if nonminor_paras:
            acts_with_nonminor += 1
            worst.append(
                {
                    "slug": slug,
                    "nonminor_paragraphs": nonminor_paras,
                    "by_mode": {k: by_mode_paras[k] for k in ALL_KINDS if by_mode_paras[k]},
                    "docx_mode": mode,
                }
            )

        if args.within_para:
            act_wp: Counter = Counter()
            for d in divs:
                if d.kind not in _REPLACE_KINDS:
                    continue  # a delete/insert opcode is never a replace
                replace_opcode_total += 1
                span_mass = d.docx_span[1] - d.docx_span[0]
                equal_len = (d.docx_span[1] - d.docx_span[0]) == (
                    d.akn_span[1] - d.akn_span[0]
                )
                if equal_len:
                    replace_equal_len += 1
                    replace_equal_len_para_mass += span_mass
                else:
                    replace_unequal_len += 1
                    replace_unequal_len_para_mass += span_mass
                    # §7 (this task): unequal-length blocks over
                    # _WP_ALIGN_MAX_PARAS fall back to one whole-block
                    # wp_block_skipped classification rather than per-pair
                    # alignment. Tracked separately so `classified_fraction`
                    # can exclude that fallback mass from "classified".
                    if len(d.within_para) == 1 and d.within_para[0].kind == "wp_block_skipped":
                        replace_unequal_len_capped += 1
                        replace_unequal_len_capped_para_mass += span_mass
                # Equal-length blocks always classified positionally (Phase 1);
                # unequal-length blocks now also classify (this task, best-match
                # aligned) -- both feed the same totals/by-outer-kind/worst-20
                # aggregation. Additive: this loop body used to be nested only
                # under `if equal_len:`, so equal-length figures are unchanged.
                for w in d.within_para:
                    wp_totals[w.kind] += 1
                    wp_by_outer.setdefault(d.kind, Counter())[w.kind] += 1
                    act_wp[w.kind] += 1
            wp_score = act_wp["wp_garble"] + act_wp["wp_word_drop"]
            if wp_score:
                wp_worst.append(
                    {
                        "slug": slug,
                        "wp_garble": act_wp["wp_garble"],
                        "wp_word_drop": act_wp["wp_word_drop"],
                        "wp_word_insert": act_wp["wp_word_insert"],
                        "wp_word_reorder": act_wp["wp_word_reorder"],
                        "wp_punct": act_wp["wp_punct"],
                        "wp_clean": act_wp["wp_clean"],
                        "wp_skipped": act_wp["wp_skipped"],
                        "score": wp_score,
                        "docx_mode": mode,
                    }
                )

        (out_dir / f"{slug}.json").write_text(
            json.dumps(
                {
                    "slug": slug,
                    "xml_path": xml_rel,
                    "docx_files": [p.name for p in docx_paths],
                    "docx_mode": mode,
                    "comp_num": entry.get("comp_num"),
                    "docx_body_paragraphs": n_docx_paras,
                    "akn_body_paragraphs": n_akn_paras,
                    "divergence_count": len(divs),
                    "paragraphs_by_mode": {k: by_mode_paras[k] for k in ALL_KINDS if by_mode_paras[k]},
                    "nonminor_paragraphs": nonminor_paras,
                    "divergences": [
                        {
                            **{k: v for k, v in d.__dict__.items() if k != "within_para"},
                            "within_para": [asdict(w) for w in d.within_para],
                        }
                        for d in divs
                    ],
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        if args.progress_every and n % args.progress_every == 0:
            el = time.time() - start
            print(f"[{n}/{len(items)}] scanned={scanned} skipped={len(skipped)} elapsed={el:.0f}s", flush=True)

    worst.sort(key=lambda w: (-w["nonminor_paragraphs"], w["slug"]))
    wall = round(time.time() - start, 1)

    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "wall_clock_seconds": wall,
        "acts_in_scope": len(items),
        "acts_scanned": scanned,
        "acts_skipped": len(skipped),
        "acts_with_nonminor": acts_with_nonminor,
        "acts_clean_nonminor": scanned - acts_with_nonminor,
        "docx_modes": dict(docx_modes),
        "paragraph_totals_by_mode": {k: totals.get(k, 0) for k in ALL_KINDS},
        "acts_affected_by_mode": {k: acts_affected.get(k, 0) for k in ALL_KINDS},
        "worst_20": worst[:20],
        "skipped": skipped[:200],
    }
    if args.within_para:
        wp_worst.sort(key=lambda w: (-w["score"], w["slug"]))
        _total_replace_mass = replace_equal_len_para_mass + replace_unequal_len_para_mass
        _classified_fraction = (
            (_total_replace_mass - replace_unequal_len_capped_para_mass) / _total_replace_mass
            if _total_replace_mass
            else 0.0
        )
        summary["within_para"] = {
            "totals": {k: wp_totals.get(k, 0) for k in WP_KINDS},
            "by_outer_kind": {
                k: {wk: v[wk] for wk in sorted(v)} for k, v in sorted(wp_by_outer.items())
            },
            "coverage": {
                "replace_opcodes": replace_opcode_total,
                "equal_len": replace_equal_len,
                "unequal_len": replace_unequal_len,
                "equal_len_para_mass": replace_equal_len_para_mass,
                "unequal_len_para_mass": replace_unequal_len_para_mass,
                "unequal_len_capped": replace_unequal_len_capped,
                "unequal_len_capped_para_mass": replace_unequal_len_capped_para_mass,
                "classified_fraction": _classified_fraction,
            },
            "worst_20": wp_worst[:20],
        }
    (out_dir / "SUMMARY.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_dir / "SUMMARY.md").write_text(_render_md(summary), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in summary if k not in ("worst_20", "skipped")}, indent=2))
    print(f"worst 5: {[w['slug'] for w in worst[:5]]}")
    print(f"wrote {out_dir}/SUMMARY.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
