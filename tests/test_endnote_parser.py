from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from lexau.endnote_parser import (
    AmendmentEvent,
    EndnoteResult,
    LegislationHistoryEntry,
    parse_endnotes,
)


# ---------------------------------------------------------------------------
# Helpers: build mock DOCX-like objects
# ---------------------------------------------------------------------------

def _make_para(text: str, style_name: str) -> MagicMock:
    para = MagicMock()
    para.text = text
    para.style.name = style_name
    return para


def _make_cell(text: str) -> MagicMock:
    cell = MagicMock()
    cell.text = text
    return cell


def _make_row(texts: list[str]) -> MagicMock:
    row = MagicMock()
    row.cells = [_make_cell(t) for t in texts]
    return row


def _make_table(rows: list[list[str]]) -> MagicMock:
    table = MagicMock()
    table.rows = [_make_row(r) for r in rows]
    return table


def _make_doc(blocks: list) -> MagicMock:
    """Build a mock Document whose iter_inner_content() returns *blocks*."""
    doc = MagicMock()
    doc.iter_inner_content.return_value = iter(blocks)
    return doc


# ---------------------------------------------------------------------------
# Block-type sentinels: endnote_parser uses isinstance checks, so we need
# the mock objects to pass isinstance(block, Paragraph) and isinstance(block, Table).
# We patch at the module level by injecting real docx types via spec.
# ---------------------------------------------------------------------------

from docx.text.paragraph import Paragraph
from docx.table import Table


def _make_para_typed(text: str, style_name: str) -> MagicMock:
    para = MagicMock(spec=Paragraph)
    para.text = text
    para.style.name = style_name
    return para


def _make_table_typed(rows: list[list[str]]) -> MagicMock:
    table = MagicMock(spec=Table)
    table.rows = [_make_row(r) for r in rows]
    return table


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestParseLegislationHistory:
    def test_parse_legislation_history(self):
        """2-row table yields 2 LegislationHistoryEntry objects."""
        table = _make_table_typed([
            ["Act", "Number and year", "Assent", "Commencement"],  # header
            ["Privacy Act 1988", "119, 1988", "14 Dec 1988", "14 Dec 1988"],
            ["Privacy Amendment Act 2000", "70, 2000", "1 Jun 2000", "1 Jul 2000"],
        ])
        blocks = [
            _make_para_typed("Endnotes", "ENotesHeading 1"),
            _make_para_typed("Endnote 3—Legislation history", "ENotesHeading 2"),
            table,
        ]
        doc = _make_doc(blocks)
        result = parse_endnotes(doc)

        assert len(result.legislation_history) == 2
        assert isinstance(result.legislation_history[0], LegislationHistoryEntry)
        assert result.legislation_history[0].act_name == "Privacy Act 1988"
        assert result.legislation_history[0].act_number == 119
        assert result.legislation_history[0].act_year == 1988
        assert result.legislation_history[1].act_name == "Privacy Amendment Act 2000"
        assert result.legislation_history[1].act_number == 70
        assert result.legislation_history[1].act_year == 2000


class TestContinuationRow:
    def test_continuation_row(self):
        """A row with empty col1 inherits the current_provision from the previous row."""
        table = _make_table_typed([
            ["provision affected", "how affected"],  # header
            ["s 6", "am No 70, 2000"],
            ["", "am No 116, 2001"],  # continuation — same provision
        ])
        blocks = [
            _make_para_typed("Endnotes", "ENotesHeading 1"),
            _make_para_typed("Endnote 4—Amendment history", "ENotesHeading 2"),
            table,
        ]
        doc = _make_doc(blocks)
        result = parse_endnotes(doc)

        assert len(result.amendment_events) == 2
        assert result.amendment_events[0].provision == "s 6"
        assert result.amendment_events[1].provision == "s 6"


class TestStructuralMarkerSkipped:
    def test_structural_marker_skipped(self):
        """A 'Part I' row with empty col2 produces no AmendmentEvent."""
        table = _make_table_typed([
            ["provision affected", "how affected"],
            ["Part I", ""],
            ["s 6", "am No 70, 2000"],
        ])
        blocks = [
            _make_para_typed("Endnotes", "ENotesHeading 1"),
            _make_para_typed("Endnote 4—Amendment history", "ENotesHeading 2"),
            table,
        ]
        doc = _make_doc(blocks)
        result = parse_endnotes(doc)

        provisions = [e.provision for e in result.amendment_events]
        assert "Part I" not in provisions
        assert len(result.amendment_events) == 1


class TestSingleAmendment:
    def test_single_amendment(self):
        """'am No 70, 2009' → AmendmentEvent(effect='am', act_number=70, act_year=2009)."""
        table = _make_table_typed([
            ["provision affected", "how affected"],
            ["s 6", "am No 70, 2009"],
        ])
        blocks = [
            _make_para_typed("Endnotes", "ENotesHeading 1"),
            _make_para_typed("Endnote 4—Amendment history", "ENotesHeading 2"),
            table,
        ]
        doc = _make_doc(blocks)
        result = parse_endnotes(doc)

        assert len(result.amendment_events) == 1
        ev = result.amendment_events[0]
        assert isinstance(ev, AmendmentEvent)
        assert ev.effect == "am"
        assert ev.act_number == 70
        assert ev.act_year == 2009
        assert ev.provision == "s 6"


class TestMultipleNumsAnd:
    def test_multiple_nums_and(self):
        """'am. Nos. 83 and 172, 1999' → 2 AmendmentEvents, both effect='am'."""
        table = _make_table_typed([
            ["provision affected", "how affected"],
            ["s 6", "am. Nos. 83 and 172, 1999"],
        ])
        blocks = [
            _make_para_typed("Endnotes", "ENotesHeading 1"),
            _make_para_typed("Endnote 4—Amendment history", "ENotesHeading 2"),
            table,
        ]
        doc = _make_doc(blocks)
        result = parse_endnotes(doc)

        assert len(result.amendment_events) == 2
        assert result.amendment_events[0].effect == "am"
        assert result.amendment_events[0].act_number == 83
        assert result.amendment_events[0].act_year == 1999
        assert result.amendment_events[1].effect == "am"
        assert result.amendment_events[1].act_number == 172
        assert result.amendment_events[1].act_year == 1999


class TestSemicolonSeparated:
    def test_semicolon_separated(self):
        """'am No 74, 1991; No 116, 1991' → 2 AmendmentEvents."""
        table = _make_table_typed([
            ["provision affected", "how affected"],
            ["s 7", "am No 74, 1991; No 116, 1991"],
        ])
        blocks = [
            _make_para_typed("Endnotes", "ENotesHeading 1"),
            _make_para_typed("Endnote 4—Amendment history", "ENotesHeading 2"),
            table,
        ]
        doc = _make_doc(blocks)
        result = parse_endnotes(doc)

        assert len(result.amendment_events) == 2
        assert result.amendment_events[0].act_number == 74
        assert result.amendment_events[0].act_year == 1991
        assert result.amendment_events[1].act_number == 116
        assert result.amendment_events[1].act_year == 1991


class TestEffectCarryForward:
    def test_effect_carry_forward(self):
        """Second segment 'No 116, 1991' inherits 'am' from first segment."""
        table = _make_table_typed([
            ["provision affected", "how affected"],
            ["s 7", "am No 74, 1991; No 116, 1991"],
        ])
        blocks = [
            _make_para_typed("Endnotes", "ENotesHeading 1"),
            _make_para_typed("Endnote 4—Amendment history", "ENotesHeading 2"),
            table,
        ]
        doc = _make_doc(blocks)
        result = parse_endnotes(doc)

        assert len(result.amendment_events) == 2
        assert result.amendment_events[0].effect == "am"
        assert result.amendment_events[1].effect == "am"


class TestNotAppliedFlag:
    def test_not_applied_flag(self):
        """'(amdt never applied ...)' sets applied=False on AmendmentEvent."""
        raw = "am No 70, 2009 (amdt never applied due to s 44)"
        table = _make_table_typed([
            ["provision affected", "how affected"],
            ["s 8", raw],
        ])
        blocks = [
            _make_para_typed("Endnotes", "ENotesHeading 1"),
            _make_para_typed("Endnote 4—Amendment history", "ENotesHeading 2"),
            table,
        ]
        doc = _make_doc(blocks)
        result = parse_endnotes(doc)

        assert len(result.amendment_events) == 1
        assert result.amendment_events[0].applied is False
        assert result.amendment_events[0].raw_text == raw


class TestNoEndnotesSection:
    def test_no_endnotes_section(self):
        """A doc with no ENotesHeading 1 yields an empty EndnoteResult."""
        para = _make_para_typed("Some random paragraph", "Normal")
        doc = _make_doc([para])
        result = parse_endnotes(doc)

        assert isinstance(result, EndnoteResult)
        assert result.legislation_history == []
        assert result.amendment_events == []
        assert result.parse_errors == []


class TestPeriodStripped:
    def test_period_stripped(self):
        """'am.' normalises to effect='am'."""
        table = _make_table_typed([
            ["provision affected", "how affected"],
            ["s 6", "am. No. 109, 2004"],
        ])
        blocks = [
            _make_para_typed("Endnotes", "ENotesHeading 1"),
            _make_para_typed("Endnote 4—Amendment history", "ENotesHeading 2"),
            table,
        ]
        doc = _make_doc(blocks)
        result = parse_endnotes(doc)

        assert len(result.amendment_events) == 1
        assert result.amendment_events[0].effect == "am"
        assert result.amendment_events[0].act_number == 109
        assert result.amendment_events[0].act_year == 2004
