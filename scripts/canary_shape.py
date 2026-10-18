"""Shape canary: detect structural drift in the published corpus.

Computes structural metrics over a deterministic sample of Acts and compares them to
a committed baseline. Read-only. Exit 1 on a hard failure, 0 otherwise (drift warnings
are written to the report but do not fail the run).

Why: lex-au v0.10.0 reshaped schedules and three consumers diverged with no signal for a
month. This is the lex-au side of the contract; consumers own their own tests
(see projects/lex-au/docs/contract-testing-plan.md).

Hard failures: structure_version not in SUPPORTED, an element tag or hcontainer name that
is absent from the baseline (a new shape), or empty/duplicate eIds above the baseline.
Drift warnings: any aggregate count moving more than --tolerance from the baseline.

Usage:
    python scripts/canary_shape.py --corpus-dir corpus --baseline canary-baseline.json
    python scripts/canary_shape.py --corpus-dir corpus --baseline canary-baseline.json --update
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

from lxml import etree

SUPPORTED_STRUCTURE_VERSIONS = frozenset({1, 2})
SAMPLE_SIZE = 200
AKN = "{http://docs.oasis-open.org/legaldocml/ns/akn/3.0}"
COUNT_KEYS = ("hcontainer", "tags", "words")


def sample_acts(index: dict, size: int) -> list[str]:
    """Slugs ordered by a stable hash, so the sample is identical run to run and
    survives Act additions (a new Act only displaces one member)."""
    ranked = sorted(index["acts"], key=lambda s: hashlib.sha256(s.encode()).hexdigest())
    return ranked[:size]


def _words(el: etree._Element) -> int:
    return sum(len(t.split()) for t in el.itertext())


def measure_act(path: Path) -> dict:
    root = etree.parse(str(path)).getroot()
    tags: Counter[str] = Counter()
    hcontainers: Counter[str] = Counter()
    eids: Counter[str] = Counter()
    empty_eids = 0
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        tag = el.tag.removeprefix(AKN)
        tags[tag] += 1
        if tag == "hcontainer":
            hcontainers[el.get("name", "")] += 1
        eid = el.get("eId")
        if eid is not None:
            if eid == "":
                empty_eids += 1
            eids[eid] += 1
    attachment_words = sum(_words(a) for a in root.iter(f"{AKN}attachment"))
    return {
        "tags": tags,
        "hcontainer": hcontainers,
        "words": Counter(attachment=attachment_words),
        "empty_eids": empty_eids,
        "duplicate_eids": sum(c - 1 for c in eids.values() if c > 1),
    }


def measure(corpus_dir: Path, size: int) -> dict:
    index = json.loads((corpus_dir / "index.json").read_text())
    agg = {"tags": Counter(), "hcontainer": Counter(), "words": Counter()}
    empty = dup = 0
    slugs = sample_acts(index, size)
    for slug in slugs:
        m = measure_act(corpus_dir / index["acts"][slug]["xml_path"])
        for k in agg:
            agg[k].update(m[k])
        empty += m["empty_eids"]
        dup += m["duplicate_eids"]
    return {
        "structure_version": index.get("structure_version"),
        "sample_size": len(slugs),
        "tags": dict(sorted(agg["tags"].items())),
        "hcontainer": dict(sorted(agg["hcontainer"].items())),
        "words": dict(agg["words"]),
        "empty_eids": empty,
        "duplicate_eids": dup,
    }


def compare(current: dict, baseline: dict, tolerance: float) -> tuple[list[str], list[str]]:
    hard: list[str] = []
    warn: list[str] = []
    version = current["structure_version"]
    if version is None:
        warn.append("index.json has no structure_version (HF export predates the stamp)")
    elif version not in SUPPORTED_STRUCTURE_VERSIONS:
        hard.append(f"structure_version {version!r} not in {sorted(SUPPORTED_STRUCTURE_VERSIONS)}")
    for key in ("tags", "hcontainer"):
        new = sorted(set(current[key]) - set(baseline[key]))
        if new:
            hard.append(f"new {key} not in baseline: {new}")
    for key in ("empty_eids", "duplicate_eids"):
        if current[key] > baseline[key]:
            hard.append(f"{key} rose {baseline[key]} -> {current[key]}")
    for key in COUNT_KEYS:
        for name, base in baseline[key].items():
            now = current[key].get(name, 0)
            if base and abs(now - base) / base > tolerance:
                warn.append(f"{key}[{name}] {base} -> {now} ({(now - base) / base:+.1%})")
    return hard, warn


def render(hard: list[str], warn: list[str], current: dict) -> str:
    lines = [
        "# Shape canary",
        "",
        f"Sample: {current['sample_size']} Acts. structure_version: {current['structure_version']}.",
        "",
    ]
    for title, items in (("Hard failures", hard), ("Drift warnings", warn)):
        lines.append(f"## {title}")
        lines += [f"- {i}" for i in items] if items else ["- none"]
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-dir", type=Path, required=True)
    ap.add_argument("--baseline", type=Path, required=True)
    ap.add_argument("--sample-size", type=int, default=SAMPLE_SIZE)
    ap.add_argument("--tolerance", type=float, default=0.10)
    ap.add_argument("--report", type=Path, help="Write the markdown report here")
    ap.add_argument("--update", action="store_true", help="Rewrite the baseline and exit 0")
    args = ap.parse_args()

    current = measure(args.corpus_dir, args.sample_size)
    if args.update:
        args.baseline.write_text(json.dumps(current, indent=2) + "\n")
        print(f"Baseline written to {args.baseline}")
        return 0

    baseline = json.loads(args.baseline.read_text())
    hard, warn = compare(current, baseline, args.tolerance)
    report = render(hard, warn, current)
    print(report)
    if args.report:
        args.report.write_text(report)
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())
