"""Migration Regulations 1994 Schedule 2: "Subclass NNN" Parts, Migration Divisions/Subdivisions,
bare-number clauses, and the volume-3 continuation (front matter + repeated Schedule 2 heading).

Shapes are trimmed from migration-regulations-1994-c288-vol2/vol3.docx.
"""
from dataclasses import replace
from datetime import date

from lexau.builder import AknBuilder
from lexau.models import ActMetadata
from lexau.parser import parse_paragraph

AKN = {"a": "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"}

SCHED2 = "Schedule\xa02—Provisions with respect to the grant of Subclasses of visas"

BODY_VOL = [
    ("ActHead 2", "Part\xa01—Preliminary"),
    ("ActHead 5", "1.01  Name of Regulations"),
    ("subsection", "These Regulations are the Migration Regulations 1994."),
    ("ActHead 1", "Schedule\xa01—Classes of visa"),
    ("ActHead 2", "Part\xa01—Permanent visas"),
]

SCHED2_VOL = [
    ("toc 2", "Subclass 801—Partner\t440"),
    ("ActHead 1", SCHED2),
    ("ActHead 2", "Subclass 010—Bridging A"),
    ("DivisionMigration", "010.1—Interpretation"),
    ("note(text)", "Note:\tThere are no interpretation provisions specific to this Part."),
    ("DivisionMigration", "010.2—Primary criteria"),
    ("SubDivisionMigration", "010.21—Criteria to be satisfied at the time of application"),
    ("ActHead 5", "010.211"),
    ("subsection", "(1)\tThe applicant meets the requirements of subclause\xa0(2)."),
    ("subsection", "(2)\tAn applicant meets the requirements of this subclause if:"),
    ("paragraph", "(a)\tthe applicant has made a valid application; and"),
    ("SubDivisionMigration", "010.22—Criteria to be satisfied at the time of decision"),
    ("ActHead 5", "010.221"),
    ("subsection", "The applicant continues to satisfy the criterion set out in clause\xa0010.211."),
    ("DivisionMigration", "010.3—Secondary criteria:   Nil."),
    ("ActHead 2", "Subclass 070—Bridging (Removal Pending)"),
    ("DivisionMigration", "070.1—Interpretation"),
    ("ActHead 5", "070.111"),
    ("subsection", "In this Part:"),
    ("Definition", "serious offence means an offence against a law of the Commonwealth."),
    ("DivisionMigration", "070.2—Primary criteria"),
    ("DivisionMigration", "070.21—Common criteria"),
    ("ActHead 5", "070.211A"),
    ("subsection", "(1)\tThe applicant is in Australia."),
]

# Volume 3: title page and its own table of contents, then Schedule 2 repeated.
CONT_VOL = [
    ("ShortT", "Migration Regulations\xa01994"),
    ("Normal", "This compilation is in 4 volumes"),
    ("toc 1", SCHED2 + "\t1"),
    ("toc 2", "Subclass 802—Child\t1"),
    ("toc 5", "1301  Operation of Schedule 1\t500"),
    ("Header", ""),
    ("ActHead 1", SCHED2),
    ("ActHead 2", "Subclass 802—Child"),
    ("DivisionMigration", "802.1—Interpretation"),
    ("ActHead 5", "802.111"),
    ("subsection", "In this Part:"),
    ("Definition", "child means a person who is under 18."),
    ("ActHead 1", "Schedule\xa03—Additional criteria applicable to unlawful non-citizens"),
    ("ActHead 5", "3001  Criteria"),
    ("subsection", "(1)\tThe criteria are met."),
]


def _build(volumes: list[list[tuple[str, str]]]):
    meta = ActMetadata(name="Migration Regulations 1994", title_id="t", comp_id="t", comp_num="1",
                       year=1994, number=268, effective_date=date(2026, 7, 1))
    b = AknBuilder(meta)
    for vi, vol in enumerate(volumes):
        for style, text in vol:
            b.add(replace(parse_paragraph(style, text), volume_index=vi))
    return b.build_with_report({}, last_volume_path=None)


def _eids(xml, name: str) -> list[str]:
    return xml.xpath(f"//a:hcontainer[@name='{name}']/@eId", namespaces=AKN)


def test_subclass_headings_become_schedule_parts() -> None:
    xml, _ = _build([BODY_VOL, SCHED2_VOL])
    parts = [e for e in _eids(xml, "part") if e.startswith("schedule-2")]
    assert parts == ["schedule-2__part-010", "schedule-2__part-070"]
    part = xml.xpath("//a:hcontainer[@eId='schedule-2__part-010']", namespaces=AKN)[0]
    assert part.findtext("a:num", namespaces=AKN) == "010"
    assert part.findtext("a:heading", namespaces=AKN) == "Bridging A"


def test_migration_divisions_and_subdivisions_nest_under_part() -> None:
    xml, _ = _build([BODY_VOL, SCHED2_VOL])
    assert "schedule-2__part-010__dvs-010.1" in _eids(xml, "division")
    assert "schedule-2__part-010__dvs-010.3" in _eids(xml, "division")
    assert _eids(xml, "subDivision") == [
        "schedule-2__part-010__dvs-010.2__subdvs-010.21",
        "schedule-2__part-010__dvs-010.2__subdvs-010.22",
        "schedule-2__part-070__dvs-070.2__subdvs-070.21",
    ]
    dvs = xml.xpath("//a:hcontainer[@eId='schedule-2__part-010__dvs-010.3']", namespaces=AKN)[0]
    assert dvs.findtext("a:heading", namespaces=AKN) == "Secondary criteria:   Nil."


def test_bare_number_clauses_become_clauses() -> None:
    xml, report = _build([BODY_VOL, SCHED2_VOL])
    clauses = [e for e in _eids(xml, "clause") if e.startswith("schedule-2")]
    assert clauses == [
        "schedule-2__part-010__dvs-010.2__subdvs-010.21__clause-010.211",
        "schedule-2__part-010__dvs-010.2__subdvs-010.22__clause-010.221",
        "schedule-2__part-070__dvs-070.1__clause-070.111",
        "schedule-2__part-070__dvs-070.2__subdvs-070.21__clause-070.211A",
    ]
    cl = xml.xpath(f"//a:hcontainer[@eId='{clauses[0]}']", namespaces=AKN)[0]
    assert cl.findtext("a:num", namespaces=AKN) == "010.211"
    assert cl.find("a:heading", namespaces=AKN) is None
    assert cl.xpath("a:hcontainer[@name='subclause']/@eId", namespaces=AKN) == [
        clauses[0] + "__subclause-1", clauses[0] + "__subclause-2",
    ]
    assert cl.xpath("a:paragraph/@eId", namespaces=AKN) == [clauses[0] + "__para-a"]


def test_continuation_volume_merges_into_open_schedule() -> None:
    xml, report = _build([BODY_VOL, SCHED2_VOL, CONT_VOL])
    scheds = xml.xpath("//a:hcontainer[@name='schedule']", namespaces=AKN)
    assert [(s.get("eId"), s.findtext("a:num", namespaces=AKN)) for s in scheds] == [
        ("schedule-1", "1"), ("schedule-2", "2"), ("schedule-3", "3"),
    ]
    assert "schedule-2__part-802" in _eids(xml, "part")
    text = "".join(scheds[1].itertext())
    assert "This compilation is in 4 volumes" not in text
    assert "Operation of Schedule 1" not in text
    assert not any("1301" in e for e in _eids(xml, "clause"))
    assert report.schedules_found == 3


def test_lowercase_toc_lines_dropped_from_visa_schedule() -> None:
    xml, _ = _build([BODY_VOL, [("ActHead 1", SCHED2), ("ActHead 2", "Subclass 010—Bridging A"),
                                ("toc 5", "1301  Operation of Schedule 1\t500")]])
    sched2 = xml.xpath("//a:hcontainer[@eId='schedule-2']", namespaces=AKN)[0]
    assert "Operation of Schedule 1" not in "".join(sched2.itertext())


def test_non_visa_schedule_untouched() -> None:
    """Gate: lowercase toc and repeated headings elsewhere (TAA, Customs Tariff) stay as they are."""
    other = [("ActHead 1", "Schedule\xa01—Things"), ("toc 5", "1301  Something\t5"),
             ("ActHead 5", "101.001")]
    cont = [("ShortT", "X"), ("ActHead 1", "Schedule\xa01—Things"), ("ActHead 5", "2  Clause two")]
    xml, _ = _build([BODY_VOL[:3], other, cont])
    assert [s.get("eId") for s in xml.xpath("//a:hcontainer[@name='schedule']", namespaces=AKN)] == [
        "schedule-1", "schedule-2",
    ]
    assert "schedule-1__clause-1301" in _eids(xml, "clause")
