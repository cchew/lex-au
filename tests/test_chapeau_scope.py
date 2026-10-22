"""Scope of local definitions read from the chapeau ("In this item:", "In this Act:", ...)."""
from lxml import etree

from lexau.termlinks import _find_chapeau, inject_local_terms, inject_scope_phrase_terms, inject_terms

NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
A = {"a": NS}


def _act(body: str = "", schedules: str = "") -> etree._Element:
    return etree.fromstring(
        f'<akomaNtoso xmlns="{NS}"><act><body>{body}</body>'
        f"<attachments><attachment>{schedules}</attachment></attachments></act></akomaNtoso>"
    )


def _section(inner: str, eid: str = "part-2__sec-5", heading: str = "Protection of information") -> str:
    return f'<section eId="{eid}"><num>5</num><heading>{heading}</heading>{inner}</section>'


def _body_part(sections: str) -> str:
    return f'<part eId="part-2"><num>2</num><heading>Part 2</heading>{sections}</part>'


def _item(eid: str, inner: str, name: str = "item") -> str:
    return f'<hcontainer name="{name}" eId="{eid}"><num>1</num><heading>Transitional</heading>{inner}</hcontainer>'


def _schedule(inner: str, eid: str = "schedule-1") -> str:
    return f'<hcontainer name="schedule" eId="{eid}"><num>Schedule 1</num><heading>Transitional</heading>{inner}</hcontainer>'


def _defn(term: str, body: str = "a thing.") -> str:
    return f"<p><b><i>{term}</i></b> means {body}</p>"


def _run(root: etree._Element, stats: dict[str, int] | None = None) -> dict[str, str]:
    reg, _ = inject_terms(root)
    inject_scope_phrase_terms(root, reg)
    inject_local_terms(root, reg, stats=stats)
    return reg


def _refs(root: etree._Element) -> list[str]:
    return [t.get("refersTo") for t in root.xpath("//a:term", namespaces=A)]


def _ref_of(root: etree._Element, term: str) -> list[str]:
    return [t.get("refersTo") for t in root.xpath("//a:term", namespaces=A) if "".join(t.itertext()) == term]


# --- Schedule items, clauses, Parts, Divisions ---------------------------------------------------


def test_in_this_item_scopes_to_the_item_not_the_schedule() -> None:
    item = _item(
        "schedule-1__item-5",
        '<subsection eId="schedule-1__item-5__subsec-1"><content><p>(1) The old law continues to apply.</p></content></subsection>'
        '<subsection eId="schedule-1__item-5__subsec-2"><content><p>In this item:</p></content>'
        f"<content>{_defn('old law', 'the Act as in force before commencement.')}</content></subsection>",
    )
    root = _act(schedules=_schedule(item))
    _run(root)
    assert _refs(root) == ["#term-old-law--schedule-1__item-5"]


def test_chapeau_in_a_sibling_subclause_before_the_term_content() -> None:
    # Real shape (Primary Industries C&T Act 2024 Sch 3 item 9): the term's <content> sits after the
    # subclause holding "In this item:", not inside it.
    clause = _item(
        "schedule-3__clause-9",
        '<hcontainer name="subclause" eId="schedule-3__clause-9__subclause-4"><num>4</num>'
        "<content><p>In this item:</p></content></hcontainer>"
        f"<content>{_defn('former Collection Act')}</content>",
        name="clause",
    )
    root = _act(schedules=_schedule(clause, eid="schedule-3"))
    _run(root)
    assert _refs(root) == ["#term-former-collection-act--schedule-3__clause-9"]


def test_in_this_part_in_a_schedule_with_two_parts_uses_that_part() -> None:
    part1 = (
        '<hcontainer name="part" eId="schedule-2__part-1"><num>Part 1</num><heading>One</heading>'
        + _item("schedule-2__part-1__item-1", "<content><p>Plain words.</p></content>")
        + "</hcontainer>"
    )
    part2 = (
        '<hcontainer name="part" eId="schedule-2__part-2"><num>Part 2</num><heading>Two</heading>'
        + _item(
            "schedule-2__part-2__item-1",
            f"<content><p>In this Part, unless the contrary intention appears:</p>{_defn('Secretary')}</content>",
        )
        + "</hcontainer>"
    )
    root = _act(schedules=_schedule(part1 + part2, eid="schedule-2"))
    _run(root)
    assert _refs(root) == ["#term-secretary--schedule-2__part-2"]


def test_division_subdivision_and_clause_chapeaus_in_a_schedule() -> None:
    def clause(eid: str, chapeau: str, term: str) -> str:
        return _item(eid, f"<content><p>{chapeau}</p>{_defn(term)}</content>", name="clause")

    sub = (
        '<hcontainer name="subDivision" eId="schedule-1__part-5__dvs-4__subdvs-A"><num>A</num><heading>S</heading>'
        + clause("schedule-1__part-5__dvs-4__subdvs-A__clause-39", "In this Subdivision, unless the contrary intention appears:", "permitted provision")
        + clause("schedule-1__part-5__dvs-4__subdvs-A__clause-49", "In this Division:", "disclose")
        + clause("schedule-1__part-5__dvs-4__subdvs-A__clause-59", "In this clause:", "agency")
        + "</hcontainer>"
    )
    sched = _schedule(
        '<hcontainer name="part" eId="schedule-1__part-5"><num>Part 5</num><heading>P</heading>'
        '<hcontainer name="division" eId="schedule-1__part-5__dvs-4"><num>4</num><heading>D</heading>'
        + sub
        + "</hcontainer></hcontainer>"
    )
    root = _act(schedules=sched)
    _run(root)
    assert _ref_of(root, "permitted provision") == ["#term-permitted-provision--schedule-1__part-5__dvs-4__subdvs-A"]
    assert _ref_of(root, "disclose") == ["#term-disclose--schedule-1__part-5__dvs-4"]
    assert _ref_of(root, "agency") == ["#term-agency--schedule-1__part-5__dvs-4__subdvs-A__clause-59"]


def test_in_this_schedule_scopes_to_the_schedule() -> None:
    item = _item("schedule-7__item-1", f"<content><p>In this Schedule:</p>{_defn('System Governor')}</content>")
    root = _act(schedules=_schedule(item, eid="schedule-7"))
    _run(root)
    assert _refs(root) == ["#term-system-governor--schedule-7"]


def test_same_term_in_three_items_gets_three_ids() -> None:
    items = "".join(
        _item(f"schedule-3__item-{n}", f"<content><p>In this item:</p>{_defn('former Collection Act')}</content>")
        for n in (9, 11, 12)
    )
    root = _act(schedules=_schedule(items, eid="schedule-3"))
    reg = _run(root)
    assert _refs(root) == [
        "#term-former-collection-act--schedule-3__item-9",
        "#term-former-collection-act--schedule-3__item-11",
        "#term-former-collection-act--schedule-3__item-12",
    ]
    assert len([k for k in reg if k.startswith("term-former-collection-act--")]) == 3


def test_schedule_term_without_chapeau_defaults_to_its_item() -> None:
    item = _item("schedule-1__item-4", f"<content>{_defn('quarter')}</content>")
    root = _act(schedules=_schedule(item))
    _run(root)
    assert _refs(root) == ["#term-quarter--schedule-1__item-4"]


def test_schedule_term_with_no_item_or_clause_is_not_tagged() -> None:
    stats: dict[str, int] = {}
    root = _act(schedules=_schedule(f"<content>{_defn('quarter')}</content>"))
    _run(root, stats)
    assert _refs(root) == []
    assert stats.get("skipped_no_scope_in_schedule") == 1


# --- Ordinary sections -----------------------------------------------------------------------------


def test_in_this_section_and_in_this_regulation_scope_to_the_section() -> None:
    root = _act(
        body=_body_part(
            _section(f"<content><p>In this section:</p>{_defn('premises')}</content>")
            + _section(f"<content><p>In this regulation:</p>{_defn('radioactive source')}</content>", eid="part-2__sec-6")
        )
    )
    _run(root)
    assert _refs(root) == ["#term-premises--part-2__sec-5", "#term-radioactive-source--part-2__sec-6"]


def test_in_this_act_chapeau_in_an_ordinary_section_is_act_wide() -> None:
    stats: dict[str, int] = {}
    root = _act(
        body=_body_part(
            _section(
                '<subsection eId="part-2__sec-5__subsec-5"><num>5</num><content><p>In this Act:</p></content>'
                f"<content>{_defn('foreign whaling vessel')}</content>"
                '<paragraph eId="part-2__sec-5__subsec-5__para-a"><num>a</num><content><p>killing; or</p></content></paragraph>'
                f'<paragraph eId="part-2__sec-5__subsec-5__para-b"><num>b</num><content><p>taking.</p>{_defn("master", "the person in command.")}</content></paragraph>'
                "</subsection>"
            )
        )
    )
    reg = _run(root, stats)
    assert _refs(root) == ["#term-foreign-whaling-vessel", "#term-master"]
    assert reg == {"term-foreign-whaling-vessel": "foreign whaling vessel", "term-master": "master"}
    assert stats.get("act_wide_via_chapeau") == 2


def test_in_this_part_chapeau_in_an_ordinary_section_scopes_to_the_part() -> None:
    root = _act(body=_body_part(_section(f"<content><p>(4) In this Part:</p>{_defn('aircraft stores')}</content>")))
    _run(root)
    assert _refs(root) == ["#term-aircraft-stores--part-2"]


def test_subsection_chapeaus_are_not_tagged() -> None:
    stats: dict[str, int] = {}
    root = _act(
        body=_body_part(
            _section(
                f"<content><p>(7) In subsection (6):</p>{_defn('wares')}"
                f"<p>For the purposes of subsection (1):</p>{_defn('damage')}"
                f"<p>In subsections (1) and (2):</p>{_defn('Commonwealth')}</content>"
            )
        )
    )
    _run(root, stats)
    assert _refs(root) == []
    assert stats.get("skipped_subsection_scope") == 3


def test_formula_variables_are_not_tagged() -> None:
    stats: dict[str, int] = {}
    root = _act(
        body=_body_part(
            _section(
                "<content><p>For the purposes of this Act, the amount is worked out using the formula:</p>"
                "<p>A × B</p><p>where:</p>"
                f"{_defn('base quarter index number')}{_defn('March quarter')}</content>"
            )
        )
    )
    _run(root, stats)
    assert _refs(root) == []
    assert stats.get("skipped_formula") == 2


def test_unrecognised_chapeau_is_not_tagged() -> None:
    stats: dict[str, int] = {}
    item = _item("schedule-2__item-2", f"<content><p>In the transitional Schedules:</p>{_defn('FWA member')}</content>")
    root = _act(schedules=_schedule(item, eid="schedule-2"))
    _run(root, stats)
    assert _refs(root) == []
    assert stats.get("skipped_unrecognised_chapeau") == 1


def test_fifth_entry_under_the_chapeau_still_resolves() -> None:
    entries = (
        _defn("ATSIC Act")
        + "<p>Commission means a body.</p>"
        + _defn("Commissioner")
        + "<p>Note: See also item 3.</p>"
        + _defn("Regional Council", "a council.")
    )
    item = _item("schedule-3__part-3__item-1", f"<content><p>In this Part, unless the contrary intention appears:</p>{entries}</content>")
    sched = _schedule(
        '<hcontainer name="part" eId="schedule-3__part-3"><num>Part 3</num><heading>P</heading>' + item + "</hcontainer>",
        eid="schedule-3",
    )
    root = _act(schedules=sched)
    _run(root)
    assert _ref_of(root, "Regional Council") == ["#term-regional-council--schedule-3__part-3"]
    assert _ref_of(root, "Commissioner") == ["#term-commissioner--schedule-3__part-3"]


def test_definition_list_items_between_chapeau_and_term_are_skipped() -> None:
    root = _act(
        body=_body_part(
            _section(
                '<subsection eId="part-2__sec-5__subsec-2"><num>2</num><content><p>In this Part:</p>'
                "<p><b><i>assets</i></b> means:</p></content>"
                '<paragraph eId="part-2__sec-5__subsec-2__para-a"><num>a</num><content><p>choses in action; and</p></content></paragraph>'
                '<paragraph eId="part-2__sec-5__subsec-2__para-b"><num>b</num><content><p>rights.</p></content></paragraph>'
                f"<content>{_defn('liability')}</content></subsection>"
            )
        )
    )
    _run(root)
    assert _ref_of(root, "liability") == ["#term-liability--part-2"]


def test_definition_tail_after_its_list_does_not_end_the_search() -> None:
    # Real shape (EPBC Act Sch 1 clause 2): "approved officer means: (a) ... (b) ..." then the entry's tail
    # "who is approved under Division 4 ..." as a separate paragraph, then the next entries.
    clause = _item(
        "schedule-1__part-1__dvs-2__clause-2",
        "<content><p>In this Schedule, unless the contrary intention appears:</p><p><b><i>approved officer</i></b> means:</p></content>"
        '<paragraph eId="schedule-1__part-1__dvs-2__clause-2__para-a"><num>a</num><content><p>an authorised officer; or</p></content></paragraph>'
        f"<content><p>who is approved under Division 4.</p>{_defn('detention')}</content>",
        name="clause",
    )
    root = _act(schedules=_schedule(clause))
    _run(root)
    assert _ref_of(root, "detention") == ["#term-detention--schedule-1"]


def test_nested_sub_list_lead_in_is_not_a_chapeau() -> None:
    root = _act(
        body=_body_part(
            _section(
                '<subsection eId="part-2__sec-5__subsec-1"><num>1</num><content><p>In this Act:</p></content>'
                '<paragraph eId="part-2__sec-5__subsec-1__para-a"><num>a</num>'
                "<content><p>(a) For the purposes of this section:</p></content></paragraph>"
                f"<content>{_defn('agent')}</content></subsection>"
            )
        )
    )
    p = root.xpath("//a:p[a:b]", namespaces=A)[0]
    chapeau = _find_chapeau(p)
    assert chapeau is not None and chapeau.kind == "act"
    _run(root)
    assert _refs(root) == ["#term-agent"]


def test_prose_lead_in_ends_the_chapeau_search() -> None:
    root = _act(
        body=_body_part(
            _section(
                "<content><p>In this Act:</p><p>The Minister may make guidelines about:</p></content>"
                '<paragraph eId="part-2__sec-5__para-a"><num>a</num><content><p>(a) a person who:</p></content></paragraph>'
                f"<content>{_defn('relevant guideline')}</content>"
            )
        )
    )
    p = root.xpath("//a:p[a:b]", namespaces=A)[0]
    assert _find_chapeau(p) is None
    _run(root)
    assert _refs(root) == ["#term-relevant-guideline--part-2__sec-5"]


def test_section_term_without_chapeau_or_phrase_scopes_to_the_section() -> None:
    root = _act(body=_body_part(_section(f"<content>{_defn('disclose')}</content>")))
    _run(root)
    assert _refs(root) == ["#term-disclose--part-2__sec-5"]


def test_find_chapeau_kinds() -> None:
    cases = {
        "In this item:": "item",
        "In this clause:": "clause",
        "In this Part:": "part",
        "In this Division:": "division",
        "In this Subdivision:": "subdivision",
        "In this Chapter:": "chapter",
        "In this Schedule:": "schedule",
        "In this section:": "section",
        "In this regulation:": "regulation",
        "In this Act:": "act",
        "In this Act, unless the contrary intention appears:": "act",
        "For the purposes of this section:": "section",
        "In subsection (1):": "subsection",
        "For the purposes of subsection (1):": "subsection",
        "where:": "formula",
        "In the transitional Schedules:": "unrecognised",
    }
    for chapeau, kind in cases.items():
        root = _act(body=_body_part(_section(f"<content><p>{chapeau}</p>{_defn('thing')}</content>")))
        p = root.xpath("//a:p[a:b]", namespaces=A)[0]
        found = _find_chapeau(p)
        assert found is not None and found.kind == kind, (chapeau, found)


# --- Scope-phrase pass guards ----------------------------------------------------------------------


def test_scope_phrase_pass_skips_definitions_sections() -> None:
    root = _act(
        body=_body_part(
            _section(
                "<content><p>In this Act, except where otherwise clearly intended:</p></content>"
                '<paragraph eId="part-2__sec-5__para-a"><num>a</num><content><p>(a) words.</p></content></paragraph>'
                "<content><p>In this Act, <i>agency</i> means a body.</p></content>",
                heading="Definitions",
            )
        )
    )
    reg: dict[str, str] = {}
    inject_scope_phrase_terms(root, reg)
    assert _refs(root) == []


def test_scope_phrase_pass_rejects_chapeau_text_as_terms() -> None:
    root = _act(
        body=_body_part(
            _section(
                "<content><p>For the purposes of this Act, the following tables define:</p></content>"
                '<paragraph eId="part-2__sec-5__para-a"><num>a</num><content><p>(a) words.</p></content></paragraph>'
                "<content><p>In this Act, except where otherwise clearly intended:</p></content>"
                '<paragraph eId="part-2__sec-5__para-b"><num>b</num><content><p>(b) words.</p></content></paragraph>'
                "<content><p>In this Act, unless the contrary intention appears:</p></content>"
                '<paragraph eId="part-2__sec-5__para-c"><num>c</num><content><p>(c) words.</p></content></paragraph>',
                heading="Tables",
            )
        )
    )
    reg: dict[str, str] = {}
    inject_scope_phrase_terms(root, reg)
    assert _refs(root) == []


# --- Builder wiring: skip counts reach the ParseReport; flags off leaves them empty ------------------


def _build_report(profile):  # type: ignore[no-untyped-def]
    from datetime import date

    from lexau.builder import AknBuilder
    from lexau.models import ActMetadata
    from lexau.parser import ElementType, InlineSpan, ParsedParagraph

    meta = ActMetadata(name="T Act 2000", title_id="t", comp_id="t", comp_num="1", year=2000, number=1,
                       effective_date=date(2026, 1, 1))
    b = AknBuilder(meta, profile=profile)
    for p in [
        ParsedParagraph(ElementType.SECTION, number="5", heading="Offences"),
        ParsedParagraph(ElementType.SUBSECTION, number="1", text="In subsection (2):"),
        ParsedParagraph(
            ElementType.BODY, text="wares means goods.",
            spans=[InlineSpan("wares", bold=True, italic=True), InlineSpan(" means goods.")],
        ),
    ]:
        b.add(p)
    return b.build_with_report({}, last_volume_path=None)


def test_builder_records_local_term_scope_counts() -> None:
    from lexau.profiles import CTH_PROFILE

    root, report = _build_report(CTH_PROFILE)
    assert report.local_term_scope == {"skipped_subsection_scope": 1}
    assert root.xpath("//a:term", namespaces=A) == []


def test_builder_flags_off_leaves_local_term_scope_empty() -> None:
    _, report = _build_report(None)
    assert report.local_term_scope == {}


# --- Dictionary Schedules stay untagged (inject_terms territory; definitions_in_schedules is off) ----


def _dictionary_schedule(inner: str) -> str:
    return f'<hcontainer name="schedule" eId="schedule-1"><num>Schedule 1</num><heading>Dictionary</heading>{inner}</hcontainer>'


def test_dictionary_schedule_with_in_this_act_chapeau_is_not_tagged() -> None:
    stats: dict[str, int] = {}
    root = _act(
        schedules=_dictionary_schedule(
            f"<content><p>In this Act:</p>{_defn('agency')}{_defn('applicant')}"
            "<p>In this Act, <i>widget</i> means a thing.</p></content>"
        )
    )
    _run(root, stats)
    assert _refs(root) == []
    assert stats.get("act_wide_via_chapeau") is None


def test_dictionary_schedule_with_a_clause_level_chapeau_is_not_tagged() -> None:
    # Patents Act 1990 shape: the whole Dictionary sits in one clause hcontainer.
    clause = _item(
        "schedule-1__clause-1952",
        f"<content><p>In this Act, unless the contrary intention appears:</p>{_defn('application')}"
        "<p><b><i>application</i></b>, in Chapter 15, means a thing.</p>"
        f"{_defn('assignee')}</content>",
        name="clause",
    )
    root = _act(schedules=_dictionary_schedule(clause))
    _run(root)
    assert _refs(root) == []


def test_definitions_clause_in_an_ordinary_schedule_still_tags() -> None:
    clause = (
        '<hcontainer name="clause" eId="schedule-1__part-1__dvs-2__clause-2"><num>2</num><heading>Definitions</heading>'
        f"<content><p>In this Schedule, unless the contrary intention appears:</p>{_defn('detention')}</content></hcontainer>"
    )
    root = _act(schedules=_schedule(clause))
    _run(root)
    assert _refs(root) == ["#term-detention--schedule-1"]
