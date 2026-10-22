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


def test_formula_legend_inside_a_list_item_is_not_tagged() -> None:
    # Small Superannuation Accounts Act s 50(4)(a): the legend sits in the same list item as "where:".
    stats: dict[str, int] = {}
    root = _act(
        body=_body_part(
            _section(
                '<subsection eId="part-2__sec-5__subsec-4"><num>4</num>'
                "<content><p>If the withdrawal event comes first:</p></content>"
                '<paragraph eId="part-2__sec-5__subsec-4__para-a"><num>a</num>'
                "<content><p>the rate of accrual is the percentage worked out using the formula:</p></content>"
                '<figure><img src="x.png" alt=""/></figure>'
                "<content><p>where:</p>"
                "<p><b><i>Adjusted allocation rate</i></b> means the last allocation rate published before the accrual day; and</p>"
                "</content></paragraph></subsection>"
            )
        )
    )
    _run(root, stats)
    assert _refs(root) == []
    assert stats.get("skipped_formula") == 1


def test_formula_legend_with_multiple_entries_in_a_list_item_is_not_tagged() -> None:
    # Airports Act s 12(5)(b) (Part 19): two legend entries after "where:".
    stats: dict[str, int] = {}
    root = _act(
        body=_body_part(
            _section(
                '<subsection eId="part-2__sec-5__subsec-5"><num>5</num><content><p>If:</p></content>'
                '<paragraph eId="part-2__sec-5__subsec-5__para-b"><num>b</num>'
                "<content><p>the first level company holds the interest in a second level company;</p></content>"
                "<content><p>the person is taken to hold a percentage worked out using the formula:</p></content>"
                '<figure><img src="x.png" alt=""/></figure>'
                "<content><p>where:</p>"
                "<p><b><i>first level percentage</i></b> means the percentage held by the person.</p>"
                "<p><b><i>second level percentage</i></b> means the percentage held by the first level company.</p>"
                "</content></paragraph></subsection>"
            )
        )
    )
    _run(root, stats)
    assert _refs(root) == []
    assert stats.get("skipped_formula") == 2


def test_nested_sublist_lead_in_is_still_ignored_as_chapeau() -> None:
    root = _act(
        body=_body_part(
            _section(
                "<content><p>In this section:</p></content>"
                '<paragraph eId="part-2__sec-5__para-a"><num>a</num>'
                "<content><p>a person who:</p></content>"
                f"</paragraph><content>{_defn('widget')}</content>"
            )
        )
    )
    chapeau = _find_chapeau(root.xpath("//a:p[a:b]", namespaces=A)[0])
    assert chapeau is not None and chapeau.kind == "section"


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


# --- Task 4: scope-recovery rules C, A, D, E, F and the "In applying ..." lead-in -------------------


def _named_act(name: str, body: str = "", schedules: str = "") -> etree._Element:
    return etree.fromstring(
        f'<akomaNtoso xmlns="{NS}"><act><meta><identification><FRBRWork><FRBRname value="{name}"/></FRBRWork>'
        f"</identification></meta><body>{body}</body>"
        f"<attachments><attachment>{schedules}</attachment></attachments></act></akomaNtoso>"
    )


def _code_schedule(heading: str, clause_eid: str, chapeau: str, term: str) -> str:
    # NCCP Sch 1 cl 27 shape: the chapeau sits in a subclause hcontainer, the entries in the clause after it.
    return (
        f'<hcontainer name="schedule" eId="schedule-1"><num>Schedule 1</num><heading>{heading}</heading>'
        f'<hcontainer name="clause" eId="{clause_eid}"><num>27</num><heading>Definitions</heading>'
        f'<hcontainer name="subclause" eId="{clause_eid}__subclause-1"><num>1</num>'
        f"<content><p>{chapeau}</p></content></hcontainer>"
        f"<content>{_defn(term)}</content></hcontainer></hcontainer>"
    )


def test_rule_c_code_law_scheme_chapeau_scopes_to_the_schedule_that_names_it() -> None:
    cases = [
        ("National Credit Code", "In this Code:", "credit limit"),
        ("Marine Safety (Domestic Commercial Vessel) National Law", "In this Law:", "COAG"),
        ("The cooperative scheme", "In this scheme:", "Australian ship"),
    ]
    for heading, chapeau, term in cases:
        root = _act(schedules=_code_schedule(heading, "schedule-1__part-1__clause-27", chapeau, term))
        _run(root)
        assert _ref_of(root, term) == [f"#{'term-' + term.lower().replace(' ', '-')}--schedule-1"], (chapeau, _refs(root))


def test_rule_c_negative_schedule_not_naming_it_and_act_body_stay_skipped() -> None:
    stats: dict[str, int] = {}
    # "In this Law:" inside a Schedule headed for a Code: the word does not match.
    root = _act(schedules=_code_schedule("National Credit Code", "schedule-1__part-1__clause-27", "In this Law:", "credit limit"))
    _run(root, stats)
    # Criminal Code s 4.1(2) shape: "In this Code:" in the Act body.
    body = _act(
        body=_body_part(
            _section(
                '<subsection eId="part-2__sec-5__subsec-2"><num>2</num><content><p>In this Code:</p></content>'
                f"<content>{_defn('conduct')}</content></subsection>"
            )
        )
    )
    _run(body, stats)
    assert _refs(root) == [] and _refs(body) == []
    assert stats.get("skipped_unrecognised_chapeau") == 2


def _schedule_clause(sched_eid: str, clause_eid: str, sub: str, heading: str = "H—Demutualisation") -> str:
    return (
        f'<hcontainer name="schedule" eId="{sched_eid}"><num>Schedule 4</num><heading>{heading}</heading>'
        f'<hcontainer name="clause" eId="{clause_eid}"><num>326-60</num><heading>Continuity test</heading>{sub}'
        "</hcontainer></hcontainer>"
    )


def test_rule_a_in_this_section_in_a_schedule_clause_scopes_to_the_clause() -> None:
    # ITAA 1936 Sch 4 cl 326-60(3): the Schedule's "sections" parse as clauses.
    clause_eid = "schedule-4__dvs-326__subdvs-326-B__clause-326-60"
    root = _act(
        schedules=_schedule_clause(
            "schedule-4",
            clause_eid,
            f'<hcontainer name="subclause" eId="{clause_eid}__subclause-3"><num>3</num>'
            f"<content><p>In this section:</p></content></hcontainer><content>{_defn('accumulated surplus')}</content>",
        )
    )
    _run(root)
    assert _refs(root) == [f"#term-accumulated-surplus--{clause_eid}"]


def test_rule_a_negative_in_this_section_in_a_schedule_item_stays_skipped() -> None:
    # Corporations Regulations Sch 21 item 24: modification text quoting s 1017D, not a section of its own.
    stats: dict[str, int] = {}
    item = _item(
        "schedule-21__part-1__item-24",
        '<subsection eId="schedule-21__part-1__item-24__subsec-16"><num>16</num><content><p>In this section:</p></content>'
        f"<content>{_defn('protected member')}</content></subsection>",
    )
    root = _act(schedules=_schedule(item, eid="schedule-21"))
    _run(root, stats)
    assert _refs(root) == []
    assert stats.get("skipped_chapeau_container_missing") == 1


def test_rule_c_negative_heading_that_merely_contains_the_word_stays_skipped() -> None:
    stats: dict[str, int] = {}
    for heading in ("Amendment of the Criminal Code Act 1995", "Code of conduct and banning orders", "Family law matters"):
        root = _act(schedules=_code_schedule(heading, "schedule-1__part-1__clause-27", "In this Code:" if "Code" in heading else "In this Law:", "conduct"))
        _run(root, stats)
        assert _refs(root) == [], heading
    ok = _act(schedules=_code_schedule("National Credit Code.", "schedule-1__part-1__clause-27", "In this Code:", "conduct"))
    _run(ok)
    assert _refs(ok) == ["#term-conduct--schedule-1"]


def _casr_section(chapeau: str) -> str:
    # CASR reg 21.041(1) shape.
    return _section(
        f'<subsection eId="part-21__sec-21.041__subsec-1"><num>1</num><content><p>{chapeau}</p></content>'
        f"<content>{_defn('type certificate')}</content></subsection>",
        eid="part-21__sec-21.041",
        heading="Type certificate—meaning",
    )


def test_rule_d_in_these_regulations_is_instrument_wide() -> None:
    for chapeau in ("In these Regulations:", "In these Regulations, unless the contrary intention appears:"):
        stats: dict[str, int] = {}
        root = _named_act("civil-aviation-safety-regulations-1998", body=_body_part(_casr_section(chapeau)))
        reg = _run(root, stats)
        assert _refs(root) == ["#term-type-certificate"], chapeau
        assert reg["term-type-certificate"] == "type certificate"
        assert stats.get("act_wide_via_chapeau") == 1


def test_rule_d_negative_in_these_regulations_outside_a_regulations_instrument_stays_skipped() -> None:
    stats: dict[str, int] = {}
    for name in ("civil-aviation-act-1988", "civil-aviation-regulations-amendment-act-1999",
                 "civil-aviation-safety-amendment-regulations-2025", "x-repeal-regulations-2025", "x-regulations-amendment-2025"):
        root = _named_act(name, body=_body_part(_casr_section("In these Regulations:")))
        _run(root, stats)
        assert _refs(root) == [], name
    no_meta = _act(body=_body_part(_casr_section("In these Regulations:")))
    _run(no_meta, stats)
    assert _refs(no_meta) == []
    assert stats.get("skipped_unrecognised_chapeau") == 6


def _atsi_schedule(chapeau: str) -> str:
    # ATSI Act 2005 Sch 1 shape: numbered paragraphs straight under the Schedule, no clause containers.
    return (
        '<hcontainer name="schedule" eId="schedule-1"><num>2</num><heading>Method of counting votes</heading>'
        f"<content><p>23.\t\tThe count continues.</p><p>{chapeau}</p>{_defn('continuing candidate')}</content></hcontainer>"
    )


def test_rule_e_numbered_chapeau_is_recognised() -> None:
    root = _act(schedules=_atsi_schedule("24.\t\tIn this Schedule:"))
    _run(root)
    assert _refs(root) == ["#term-continuing-candidate--schedule-1"]


def test_rule_e_negative_numbered_unrecognised_chapeau_stays_skipped() -> None:
    stats: dict[str, int] = {}
    root = _act(schedules=_atsi_schedule("24.\t\tIn this table:"))
    _run(root, stats)
    assert _refs(root) == []
    assert stats.get("skipped_unrecognised_chapeau") == 1


def test_rule_f_singular_for_the_purpose_of_this_section_scopes_to_the_section() -> None:
    # ITAA 1936 s 79B(6).
    root = _act(
        body=_body_part(
            _section(
                '<subsection eId="part-2__sec-5__subsec-6"><num>6</num><content><p>For the purpose of this section:</p></content>'
                f"<content>{_defn('locality')}</content></subsection>"
            )
        )
    )
    _run(root)
    assert _refs(root) == ["#term-locality--part-2__sec-5"]


def test_rule_f_singular_formula_lead_in_is_no_longer_tagged() -> None:
    # Social Security Act s 1061ZZCN(3): currently tagged "This section" because the plural-only regex missed it.
    stats: dict[str, int] = {}
    root = _act(
        body=_body_part(
            _section(
                '<subsection eId="part-2__sec-5__subsec-3"><num>3</num><content>'
                "<p>For the purpose of applying the formula in subsection (2) immediately before the repayment time:</p>"
                "</content>"
                f"<content>{_defn('amounts repaid')}{_defn('principal sum')}</content></subsection>"
            )
        )
    )
    _run(root, stats)
    assert _refs(root) == []
    assert stats.get("skipped_unrecognised_chapeau") == 2


def test_rule_f_negative_singular_subsection_chapeau_stays_skipped() -> None:
    # Crimes (Currency) Act s 23(2).
    stats: dict[str, int] = {}
    root = _act(
        body=_body_part(
            _section(
                '<subsection eId="part-2__sec-5__subsec-2"><num>2</num><content><p>For the purpose of subsection (1):</p></content>'
                f"<content>{_defn('Australian aircraft')}</content></subsection>"
            )
        )
    )
    _run(root, stats)
    assert _refs(root) == []
    assert stats.get("skipped_subsection_scope") == 1


def test_long_in_applying_lead_in_is_an_unrecognised_chapeau() -> None:
    # Income Tax (Transitional Provisions) Act 1997 s 40-292(2) lead-in, over the 80-char target limit.
    stats: dict[str, int] = {}
    lead = (
        "In applying section 40-290 of the new Act (including references in that section to the reduction of "
        "deductions under section 40-25 of that Act) in relation to the asset, assume that using the asset for a "
        "taxable purpose includes using it for:"
    )
    vea = (
        "For the purposes of applying the Method statement in this section to an affected amount indexed under "
        "section 198, 198A, 198D or 198F, the following expressions used in the Method statement have the meanings set out below:"
    )
    root = _act(
        body=_body_part(
            _section(
                f'<subsection eId="part-2__sec-5__subsec-2"><num>2</num><content><p>{lead}</p></content>'
                f"<content>{_defn('total decline in value')}</content></subsection>"
            )
            + _section(f"<content><p>{vea}</p>{_defn('indexed amount')}</content>", eid="part-2__sec-6")
        )
    )
    _run(root, stats)
    assert _refs(root) == []
    assert stats.get("skipped_unrecognised_chapeau") == 2


def test_long_application_of_this_section_lead_in_keeps_default_section_scope() -> None:
    # Near miss: "For the purposes of the application of this section ..." over 80 chars keeps today's section scope.
    lead = (
        "For the purposes of the application of this section in relation to a taxpayer who is a member of a "
        "partnership at the end of the year of income:"
    )
    root = _act(body=_body_part(_section(f"<content><p>{lead}</p>{_defn('net income')}</content>")))
    _run(root)
    assert _refs(root) == ["#term-net-income--part-2__sec-5"]


def test_find_chapeau_kinds_for_new_shapes() -> None:
    cases = {
        "24. In this Schedule:": "schedule",
        "3A. In this Part:": "part",
        "For the purpose of this section:": "section",
        "For the purpose of subsection (1):": "subsection",
        "In this Code:": "unrecognised",  # body: no Schedule names it
        "In these Regulations:": "unrecognised",  # no regulations instrument name
    }
    for chapeau, kind in cases.items():
        root = _act(body=_body_part(_section(f"<content><p>{chapeau}</p>{_defn('thing')}</content>")))
        p = root.xpath("//a:p[a:b]", namespaces=A)[0]
        found = _find_chapeau(p)
        assert found is not None and found.kind == kind, (chapeau, found)
