import os
import stat
import subprocess
import sys
from pathlib import Path

FAKE_GH_NO_ISSUE = """#!/usr/bin/env python3
import sys
args = sys.argv[1:]
with open({log_path!r}, "a") as f:
    f.write(" ".join(args) + "\\n")
if args[:2] == ["issue", "list"]:
    print("[]")
elif args[:2] == ["issue", "create"]:
    print("https://github.com/owner/repo/issues/42")
"""

FAKE_GH_EXISTING_ISSUE = """#!/usr/bin/env python3
import sys
args = sys.argv[1:]
with open({log_path!r}, "a") as f:
    f.write(" ".join(args) + "\\n")
if args[:2] == ["issue", "list"]:
    print('[{{"number": 7}}]')
"""


def _install_fake_gh(tmp_path: Path, template: str) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log_path = tmp_path / "gh-calls.log"
    gh_path = bin_dir / "gh"
    gh_path.write_text(template.format(log_path=str(log_path)))
    gh_path.chmod(gh_path.stat().st_mode | stat.S_IEXEC)
    return bin_dir, log_path


def test_creates_new_issue_when_none_open(tmp_path: Path):
    bin_dir, log_path = _install_fake_gh(tmp_path, FAKE_GH_NO_ISSUE)
    body_file = tmp_path / "body.md"
    body_file.write_text("Something broke.")

    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
    result = subprocess.run(
        [sys.executable, "scripts/report_pipeline_issue.py",
         "--repo", "owner/repo", "--label", "pipeline-verify-failure",
         "--title", "Corpus pipeline: verify gate failing",
         "--body-file", str(body_file)],
        capture_output=True, text=True, env=env,
    )

    assert result.returncode == 0, result.stderr
    calls = log_path.read_text().splitlines()
    assert calls[0].startswith("issue list --repo owner/repo --label pipeline-verify-failure")
    assert calls[1].startswith("issue create --repo owner/repo")
    assert "Created new issue" in result.stdout


def test_updates_existing_open_issue_instead_of_creating(tmp_path: Path):
    bin_dir, log_path = _install_fake_gh(tmp_path, FAKE_GH_EXISTING_ISSUE)
    body_file = tmp_path / "body.md"
    body_file.write_text("Still broken.")

    env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
    result = subprocess.run(
        [sys.executable, "scripts/report_pipeline_issue.py",
         "--repo", "owner/repo", "--label", "growth-unresolved-acts",
         "--title", "Growth workflow: unresolved Acts",
         "--body-file", str(body_file)],
        capture_output=True, text=True, env=env,
    )

    assert result.returncode == 0, result.stderr
    calls = log_path.read_text().splitlines()
    assert calls[1].startswith("issue edit 7 --repo owner/repo")
    assert "Updated existing issue #7" in result.stdout
