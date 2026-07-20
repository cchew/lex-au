#!/usr/bin/env python3
"""Phase 1 decision: apply the spec's go/no-go threshold table to the spike
results. Table (docs/superpowers/specs/2026-07-20-legacy-doc-format-parsing-design.md):

  >=90% non-empty <body>, no single failure pattern >10% of sample -> GO
  70-89%                                                            -> PARTIAL GO
  <70%, or a systematic corruption pattern found                    -> NO-GO

Usage:
    python scripts/decide_doc_conversion_gate.py [--corpus-dir corpus]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-dir", default="corpus", type=Path)
    args = ap.parse_args()

    results_path = args.corpus_dir / "reports" / "doc-conversion-spike-results.json"
    data = json.loads(results_path.read_text())

    total = data["sample_size"]
    rate = data["non_empty_body_rate"]
    error_counts = data["error_counts"]
    max_error_share = (max(error_counts.values()) / total) if error_counts and total else 0.0

    if rate >= 0.90 and max_error_share <= 0.10:
        verdict = "GO"
        rationale = "Non-empty <body> rate >= 90% with no single failure pattern exceeding 10% of the sample."
    elif rate >= 0.70:
        verdict = "PARTIAL GO"
        rationale = "Non-empty <body> rate in the 70-89% band -- ingest only individually-validated Acts, no blanket batch."
    else:
        reason = "rate below 70%" if rate < 0.70 else "a single failure pattern exceeds 10% of the sample"
        verdict = "NO-GO"
        rationale = f"Structural conversion does not clear the bar ({reason})."

    lines = [
        f"Verdict: {verdict}",
        "",
        f"Sample size: {total}",
        f"Non-empty <body> rate: {data['non_empty_body_count']}/{total} ({rate:.1%})",
        f"Largest single failure-pattern share: {max_error_share:.1%}",
        "",
        f"Rationale: {rationale}",
        "",
        "Error breakdown:",
    ]
    for err, count in sorted(error_counts.items(), key=lambda kv: -kv[1]):
        lines.append(f"  {count:>3}  {err}")

    out_path = args.corpus_dir / "reports" / "doc-conversion-go-no-go.md"
    out_path.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nWritten to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
