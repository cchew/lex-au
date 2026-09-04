#!/usr/bin/env python3
"""Corpus-wide detector for the C1 schedule-reattachment defect.

C1 (see docs/known-limitations-schedule-and-conversion.txt entry (d)): before
commit 010482a, ``builder._build_schedule_content._content_for`` ignored its
``parent`` argument and reused a single running ``<content>`` pointer. When the
NOTE/EXAMPLE/PENALTY catch-all (which resolves ``parent`` to the current clause)
ran before a subclause-scoped BODY prose paragraph, that prose ``<p>`` was
appended to the clause-level ``<content>`` and lost its subclause ``eId``
association -- or the reverse. Only the cite-``eId`` of the affected notes /
headings / short prose lines is wrong; no operative text is lost, duplicated or
reordered in substance.

The v0.9.0 corpus XML in ``corpus/xml/`` was built by re-ingest ``a5ad3c2``,
which predates the fix. This script enumerates the FULL set of Acts whose
schedule content changes ``<content>/<p>`` parent affinity between the pre-fix
builder (``a5ad3c2``) and HEAD, so the affected Acts can be targeted for
re-conversion.

Method (only ``_content_for`` differs between the two SHAs on this path -- verified
by ``git diff a5ad3c2 HEAD -- src/lexau/builder.py``):

  1. Parse each Act's cached DOCX volumes (same loop as ``cli._build_acts``).
  2. Run HEAD ``_split_stream`` once to get the schedule paragraph groups.
  3. Call ``_build_attachments`` on the OLD builder module (loaded from
     ``git show a5ad3c2:src/lexau/builder.py``) and on the HEAD builder.
  4. Diff every schedule ``<content>/<p>`` by (parent hcontainer ``name:eId``,
     normalised paragraph text).

No network, no reflink / termlink / quantlink / endnote passes -- those run in
``build_with_report`` after ``build()`` and are identical at both SHAs, so
``_content_for`` is the only free variable.

Each Act runs in a forked child with a wall-clock timeout; a staller (e.g.
``corporations-act-2001``) is recorded as "not measured" rather than aborting
the run.

Usage:
    python scripts/detect_c1_schedule_reattach.py [--corpus-dir corpus] \
        [--timeout 90] [--limit N] [--slug SLUG] [--out PATH]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import multiprocessing as mp
import queue as _queue
import re
import subprocess
import sys
import tempfile
import time
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

from lxml import etree

# Reuse the audit's DOCX-volume resolver (comp-vol / othercomp-vol / legacy-vol
# / single), so the detector sees exactly the volumes cli._build_acts would.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from audit_conversion_fidelity import _docx_paths  # noqa: E402

from lexau import builder as builder_new  # noqa: E402
from lexau.parser import ElementType  # noqa: E402

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
_P = f"{{{AKN_NS}}}p"
_CONTENT = f"{{{AKN_NS}}}content"

OLD_SHA = "a5ad3c2"
_WS = re.compile(r"\s+")

# Loaded once in main() before the fork loop; children inherit it.
_OLD_MOD = None


def _load_old_builder(old_sha: str = OLD_SHA):
    """Import ``src/lexau/builder.py`` as it stood at ``old_sha`` as a separate module."""
    src = subprocess.run(
        ["git", "show", f"{old_sha}:src/lexau/builder.py"],
        capture_output=True, text=True, check=True,
    ).stdout
    tmp = Path(tempfile.gettempdir()) / f"lexau_builder_{old_sha}.py"
    tmp.write_text(src)
    spec = importlib.util.spec_from_file_location(f"lexau_builder_{old_sha}", tmp)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _norm(el: etree._Element) -> str:
    return _WS.sub(" ", "".join(el.itertext())).strip()


def _placements(attachments_el: etree._Element | None) -> list[tuple[str, str]]:
    """(parent-key, normalised text) for every <p> that is a direct child of a <content>.

    parent-key = "<name-or-localtag>:<eId>" of the element that owns the <content>
    (schedule / clause / subclause hcontainer, or paragraph / subparagraph).
    """
    out: list[tuple[str, str]] = []
    if attachments_el is None:
        return out
    for p_el in attachments_el.iter(_P):
        parent = p_el.getparent()
        if parent is None or parent.tag != _CONTENT:
            continue
        owner = parent.getparent()
        if owner is None:
            continue
        name = owner.get("name") or etree.QName(owner).localname
        out.append((f"{name}:{owner.get('eId', '')}", _norm(p_el)))
    return out


def _analyse(slug: str, entry: dict, corpus_dir: Path, old_mod) -> dict:
    from docx import Document
    from lexau.docx_reader import iter_paragraphs

    docx_paths, mode = _docx_paths(corpus_dir, slug, entry)
    if not docx_paths:
        return {"slug": slug, "status": "no_docx", "docx_mode": mode}

    paras = []
    for vol_idx, dp in enumerate(docx_paths):
        doc = Document(str(dp))
        for p in iter_paragraphs(doc):
            paras.append(replace(p, volume_index=vol_idx))

    _pre, _body, groups = builder_new._split_stream(paras)
    if not groups:
        return {"slug": slug, "status": "no_schedules", "docx_mode": mode}

    new_place = _placements(builder_new._build_attachments(groups)[0])
    old_place = _placements(old_mod._build_attachments(groups)[0])

    old_texts = Counter(t for _, t in old_place)
    new_texts = Counter(t for _, t in new_place)
    prose_set_same = old_texts == new_texts

    old_by_text: dict[str, Counter] = defaultdict(Counter)
    for k, t in old_place:
        old_by_text[t][k] += 1
    new_by_text: dict[str, Counter] = defaultdict(Counter)
    for k, t in new_place:
        new_by_text[t][k] += 1

    moved = 0
    directions: Counter = Counter()
    for t, ok in old_by_text.items():
        nk = new_by_text.get(t, Counter())
        lost = ok - nk
        gained = nk - ok
        moved += sum(lost.values())
        for a, b in zip(sorted(lost.elements()), sorted(gained.elements())):
            directions[f"{a.split(':', 1)[0]} -> {b.split(':', 1)[0]}"] += 1

    return {
        "slug": slug,
        "status": "ok",
        "docx_mode": mode,
        "schedules": len(groups),
        "paragraphs_total": len(new_place),
        "moved": moved,
        "prose_set_same": prose_set_same,
        "directions": dict(directions),
        "affected": bool(moved) and prose_set_same,
    }


def _worker(slug, entry, corpus_dir, q) -> None:
    try:
        old_mod = _OLD_MOD if _OLD_MOD is not None else _load_old_builder()
        q.put(_analyse(slug, entry, Path(corpus_dir), old_mod))
    except Exception as e:  # noqa: BLE001
        q.put({"slug": slug, "status": f"error:{type(e).__name__}", "detail": str(e)[:300]})


def _candidates(corpus_dir: Path) -> list[str]:
    xml_dir = corpus_dir / "xml"
    hits = []
    needle = b'name="subclause"'
    for x in sorted(xml_dir.glob("*.xml")):
        if needle in x.read_bytes():
            hits.append(x.stem)
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus-dir", type=Path, default=Path("corpus"))
    ap.add_argument("--timeout", type=float, default=90.0)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--slug", default=None)
    ap.add_argument("--out", type=Path, default=Path("corpus/reports/c1_schedule_reattach.json"))
    ap.add_argument("--progress-every", type=int, default=50)
    args = ap.parse_args()

    corpus_dir: Path = args.corpus_dir
    index = json.loads((corpus_dir / "index.json").read_text())
    acts: dict = index["acts"] if isinstance(index, dict) and "acts" in index else index

    slugs = [args.slug] if args.slug else _candidates(corpus_dir)
    if args.limit:
        slugs = slugs[: args.limit]

    # Load the pre-fix builder once; forked children inherit it.
    global _OLD_MOD
    _OLD_MOD = _load_old_builder(OLD_SHA)

    ctx = mp.get_context("fork")
    results: list[dict] = []
    not_measured: list[str] = []
    errors: list[dict] = []
    start = time.time()

    for n, slug in enumerate(slugs, 1):
        entry = acts.get(slug)
        if entry is None:
            errors.append({"slug": slug, "status": "no_index_entry"})
            continue
        q = ctx.Queue()
        p = ctx.Process(target=_worker, args=(slug, entry, str(corpus_dir), q))
        p.start()
        p.join(args.timeout)
        if p.is_alive():
            p.terminate()
            p.join()
            not_measured.append(slug)
        else:
            try:
                r = q.get_nowait()
            except _queue.Empty:
                not_measured.append(slug)
            else:
                if r.get("status", "").startswith("error"):
                    errors.append(r)
                else:
                    results.append(r)
        if args.progress_every and n % args.progress_every == 0:
            el = time.time() - start
            aff = sum(1 for r in results if r.get("affected"))
            print(f"[{n}/{len(slugs)}] affected={aff} not_measured={len(not_measured)} "
                  f"errors={len(errors)} elapsed={el:.0f}s", flush=True)

    affected = sorted((r for r in results if r.get("affected")),
                      key=lambda r: (-r["moved"], r["slug"]))
    moved_not_stable = [r for r in results if r.get("moved") and not r.get("prose_set_same")]
    clean = [r for r in results if r.get("status") == "ok" and not r.get("affected")
             and not (r.get("moved") and not r.get("prose_set_same"))]

    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "wall_clock_seconds": round(time.time() - start, 1),
        "old_sha": OLD_SHA,
        "candidates": len(slugs),
        "measured": len(results),
        "affected_count": len(affected),
        "clean_count": len(clean),
        "not_measured": not_measured,
        "errors": errors,
        "moved_not_prose_stable": moved_not_stable,
        "affected": affected,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ("affected", "not_measured", "errors", "moved_not_prose_stable")},
                     indent=2))
    print(f"affected slugs: {[r['slug'] for r in affected]}")
    print(f"not measured: {not_measured}")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
