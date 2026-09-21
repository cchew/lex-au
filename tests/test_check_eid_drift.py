import subprocess
import sys
from pathlib import Path

from scripts.check_eid_drift import eid_drift

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"

# Minimal synthetic AKN doc: one unchanged body <section>, one body <section>
# under test, and one schedule clause under test inside <attachments>. Mirrors
# the real builder's shape (<meta> eventRefs, <body>, sibling <attachments>
# containing <attachment>/<hcontainer name="schedule">) without touching the
# real corpus.
_DOC_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<akomaNtoso xmlns="{ns}">
  <act name="act">
    <meta>
      <identification source="#lex-au">
        <FRBRWork><FRBRthis value="/akn/au/act/1999/1/!main"/></FRBRWork>
      </identification>
      <lifecycle source="#parliament">
        <eventRef date="1999-01-01" type="generation" eId="{meta_eid}" source="#x"/>
      </lifecycle>
    </meta>
    <body>
      <section eId="sec_1">
        <content><p>Unchanged body text.</p></content>
      </section>
      <section eId="{sec5_eid}">
        <content><p>Body text under test.</p></content>
      </section>
      {extra_body}
    </body>
    <attachments>
      <attachment eId="att_1">
        <hcontainer name="schedule" eId="schedule-1">
          <hcontainer name="{sched_name}" eId="{sched_eid}">
            <content><p>Schedule text under test.</p></content>
          </hcontainer>
        </hcontainer>
      </attachment>
    </attachments>
  </act>
</akomaNtoso>
"""


def _write_doc(
    path: Path, *, sec5_eid: str, sched_name: str, sched_eid: str, meta_eid: str = "evt-creation",
    extra_body: str = "",
) -> None:
    path.write_text(
        _DOC_TEMPLATE.format(
            ns=AKN_NS, sec5_eid=sec5_eid, sched_name=sched_name, sched_eid=sched_eid,
            meta_eid=meta_eid, extra_body=extra_body,
        )
    )


def _dirs(tmp_path: Path) -> tuple[Path, Path]:
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    return old_dir, new_dir


def test_schedule_eid_rename_is_allowed(tmp_path: Path):
    """schedule-1__clause-3 -> schedule-1__item-3: allowed schedule renumber
    (Tasks 6/13 family B4 + family C), must not be flagged as a body move."""
    old_dir, new_dir = _dirs(tmp_path)

    _write_doc(
        old_dir / "example-act-1999.xml",
        sec5_eid="sec_5", sched_name="clause", sched_eid="schedule-1__clause-3",
    )
    _write_doc(
        new_dir / "example-act-1999.xml",
        sec5_eid="sec_5", sched_name="item", sched_eid="schedule-1__item-3",
    )

    result = eid_drift(old_dir, new_dir)

    assert result["body_moved"] == []
    assert result["schedule_moved"] == [
        {
            "act": "example-act-1999.xml",
            "old_eid": "schedule-1__clause-3",
            "new_eid": "schedule-1__item-3",
        },
    ]


def test_body_eid_rename_is_flagged(tmp_path: Path):
    """sec_5 -> sec_5A: a body eId move, which lex-au-graph's 110,969 node
    keys can never tolerate. Must show up in body_moved."""
    old_dir, new_dir = _dirs(tmp_path)

    _write_doc(
        old_dir / "example-act-1999.xml",
        sec5_eid="sec_5", sched_name="clause", sched_eid="schedule-1__clause-3",
    )
    _write_doc(
        new_dir / "example-act-1999.xml",
        sec5_eid="sec_5A", sched_name="clause", sched_eid="schedule-1__clause-3",
    )

    result = eid_drift(old_dir, new_dir)

    assert result["body_moved"] == [
        {"act": "example-act-1999.xml", "old_eid": "sec_5", "new_eid": "sec_5A"},
    ]
    assert result["schedule_moved"] == []


def test_identical_corpora_report_no_drift(tmp_path: Path):
    old_dir, new_dir = _dirs(tmp_path)

    _write_doc(
        old_dir / "example-act-1999.xml",
        sec5_eid="sec_5", sched_name="clause", sched_eid="schedule-1__clause-3",
    )
    _write_doc(
        new_dir / "example-act-1999.xml",
        sec5_eid="sec_5", sched_name="clause", sched_eid="schedule-1__clause-3",
    )

    assert eid_drift(old_dir, new_dir) == {"body_moved": [], "schedule_moved": []}


def test_meta_only_eid_changes_are_ignored(tmp_path: Path):
    """@eId churn inside <meta> (e.g. eventRef ids) is not structural and must
    not be reported as either a body or schedule move."""
    old_dir, new_dir = _dirs(tmp_path)

    _write_doc(
        old_dir / "example-act-1999.xml",
        sec5_eid="sec_5", sched_name="clause", sched_eid="schedule-1__clause-3",
        meta_eid="evt-creation",
    )
    _write_doc(
        new_dir / "example-act-1999.xml",
        sec5_eid="sec_5", sched_name="clause", sched_eid="schedule-1__clause-3",
        meta_eid="evt-creation-renumbered",
    )

    assert eid_drift(old_dir, new_dir) == {"body_moved": [], "schedule_moved": []}


def test_new_body_eid_not_hidden_by_concurrent_schedule_rename(tmp_path: Path):
    """Regression: a legitimate schedule rename (schedule-1__clause-3 ->
    schedule-1__item-3) landing in the SAME Act as an unrelated, genuinely
    new body eId (sec_NEW_BUG, added with nothing removed) must not let the
    new body eid get cross-paired against the schedule rename and vanish
    into schedule_moved. <body> precedes <attachments> in document order, so
    naive positional pairing of the raw old-only/new-only lists lines up a
    schedule-kind old eid with a body-kind new eid whenever the body-only
    counts on each side differ -- exactly this shape. The new body eid must
    surface in body_moved, and the schedule rename must still report cleanly.
    """
    old_dir, new_dir = _dirs(tmp_path)

    _write_doc(
        old_dir / "example-act-1999.xml",
        sec5_eid="sec_5", sched_name="clause", sched_eid="schedule-1__clause-3",
    )
    _write_doc(
        new_dir / "example-act-1999.xml",
        sec5_eid="sec_5", sched_name="item", sched_eid="schedule-1__item-3",
        extra_body='<section eId="sec_NEW_BUG"><content><p>New body text.</p></content></section>',
    )

    result = eid_drift(old_dir, new_dir)

    assert result["body_moved"] == [
        {"act": "example-act-1999.xml", "old_eid": None, "new_eid": "sec_NEW_BUG"},
    ]
    assert result["schedule_moved"] == [
        {
            "act": "example-act-1999.xml",
            "old_eid": "schedule-1__clause-3",
            "new_eid": "schedule-1__item-3",
        },
    ]


def test_acts_present_in_only_one_dir_are_skipped(tmp_path: Path):
    """Only Acts with a matching filename in both dirs are compared -- an
    Act missing from one side entirely is not this gate's concern."""
    old_dir, new_dir = _dirs(tmp_path)

    _write_doc(
        old_dir / "only-in-old-act-1999.xml",
        sec5_eid="sec_5", sched_name="clause", sched_eid="schedule-1__clause-3",
    )
    _write_doc(
        new_dir / "only-in-new-act-1999.xml",
        sec5_eid="sec_5A", sched_name="clause", sched_eid="schedule-1__clause-3",
    )

    assert eid_drift(old_dir, new_dir) == {"body_moved": [], "schedule_moved": []}


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/check_eid_drift.py", *args],
        capture_output=True, text=True,
    )


def test_cli_fails_on_typoed_directory(tmp_path: Path):
    """A mistyped/nonexistent --old-dir must not look like a clean pass:
    Path.glob on a missing directory silently returns nothing, so without a
    guard this would print body_moved=0 and exit 0 -- identical to a real
    clean run. The zero-comparison guard must catch it."""
    real_dir = tmp_path / "real"
    real_dir.mkdir()
    _write_doc(
        real_dir / "example-act-1999.xml",
        sec5_eid="sec_5", sched_name="clause", sched_eid="schedule-1__clause-3",
    )

    result = _run_cli(
        "--old-dir", str(tmp_path / "typo-does-not-exist"),
        "--new-dir", str(real_dir),
    )

    assert result.returncode == 1
    assert "acts compared: 0" in result.stdout
    assert "FAIL" in result.stdout


def test_cli_fails_on_zero_filename_overlap(tmp_path: Path):
    """Two real, existing directories that simply share no XML filenames
    must also fail the zero-comparison guard, not report a clean pass."""
    old_dir, new_dir = _dirs(tmp_path)
    _write_doc(
        old_dir / "act-a-1999.xml",
        sec5_eid="sec_5", sched_name="clause", sched_eid="schedule-1__clause-3",
    )
    _write_doc(
        new_dir / "act-b-1999.xml",
        sec5_eid="sec_5A", sched_name="clause", sched_eid="schedule-1__clause-3",
    )

    result = _run_cli("--old-dir", str(old_dir), "--new-dir", str(new_dir))

    assert result.returncode == 1
    assert "acts compared: 0" in result.stdout
    assert "FAIL" in result.stdout


def test_cli_passes_and_reports_count_on_real_overlap(tmp_path: Path):
    old_dir, new_dir = _dirs(tmp_path)
    _write_doc(
        old_dir / "example-act-1999.xml",
        sec5_eid="sec_5", sched_name="clause", sched_eid="schedule-1__clause-3",
    )
    _write_doc(
        new_dir / "example-act-1999.xml",
        sec5_eid="sec_5", sched_name="item", sched_eid="schedule-1__item-3",
    )

    result = _run_cli("--old-dir", str(old_dir), "--new-dir", str(new_dir))

    assert result.returncode == 0
    assert "acts compared: 1" in result.stdout
    assert "PASS" in result.stdout


def test_cli_min_acts_fails_below_threshold(tmp_path: Path):
    """--min-acts lets a caller (e.g. Task 17's full-corpus invocation) add a
    stronger sanity check than "at least one Act" without this script
    hardcoding the corpus's current size."""
    old_dir, new_dir = _dirs(tmp_path)
    _write_doc(
        old_dir / "example-act-1999.xml",
        sec5_eid="sec_5", sched_name="clause", sched_eid="schedule-1__clause-3",
    )
    _write_doc(
        new_dir / "example-act-1999.xml",
        sec5_eid="sec_5", sched_name="clause", sched_eid="schedule-1__clause-3",
    )

    result = _run_cli(
        "--old-dir", str(old_dir), "--new-dir", str(new_dir), "--min-acts", "2",
    )

    assert result.returncode == 1
    assert "acts compared: 1" in result.stdout
    assert "FAIL" in result.stdout
