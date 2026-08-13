"""Find-or-update a labelled tracking issue via the gh CLI.

Shared by two callers with different label/title: the verify-gate
failure issue (pipeline-verify-failure, opened by the composite publish
action) and the growth-workflow unresolved-Acts issue
(growth-unresolved-acts, opened by growth-check.yml directly). Both want
the same behaviour -- update the existing open issue for that label if
one exists, otherwise create a new one -- so a recurring known failure
doesn't spam a fresh issue every run.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def find_open_issue(repo: str, label: str) -> int | None:
    result = subprocess.run(
        ["gh", "issue", "list", "--repo", repo, "--label", label,
         "--state", "open", "--json", "number", "--limit", "1"],
        capture_output=True, text=True, check=True,
    )
    issues = json.loads(result.stdout)
    return issues[0]["number"] if issues else None


def report(repo: str, label: str, title: str, body_file: Path) -> int:
    existing = find_open_issue(repo, label)
    if existing is not None:
        subprocess.run(
            ["gh", "issue", "edit", str(existing), "--repo", repo,
             "--body-file", str(body_file)],
            check=True,
        )
        print(f"Updated existing issue #{existing} (label: {label}).")
        return existing

    result = subprocess.run(
        ["gh", "issue", "create", "--repo", repo, "--title", title,
         "--label", label, "--body-file", str(body_file)],
        capture_output=True, text=True, check=True,
    )
    print(f"Created new issue (label: {label}): {result.stdout.strip()}")
    return -1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, help="owner/repo")
    parser.add_argument("--label", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--body-file", type=Path, required=True)
    args = parser.parse_args()

    report(args.repo, args.label, args.title, args.body_file)
    return 0


if __name__ == "__main__":
    sys.exit(main())
