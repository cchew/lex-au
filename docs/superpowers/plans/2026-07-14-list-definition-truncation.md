# List-Form Definition Truncation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fold orphaned paragraph-list content back into truncated `<def>` elements (colon-terminated definiens with no following list content) via a new `complete_list_definitions(root)` pass added at the very end of `builder.py`'s injection pipeline.

**Architecture:** Two new helper functions plus one top-level pass in `src/lexau/termlinks.py`: `_find_qualifying_anchor` (walks up from a truncated `<def>` to the ancestor level whose following siblings include a `<paragraph>`/`<blockList>`), `_collect_and_append_list_content`/`_append_list_item_content` (walks forward from that anchor, appending list-item content to `<def>` until a `<content>` containing a `<term refersTo>` element signals the start of the next definition). Wired into `builder.py` as the last pipeline step, after `inject_note_refs`, so every downstream injection pass has already run and every definition already carries its `<term>` tag.

**Tech Stack:** Python 3.12, lxml, pytest. No new dependencies.

## Global Constraints

- Python ≥ 3.12, all type annotations required.
- Tests live in `tests/`, one file per source module. Run with `pytest` from the repo root (venv: `source .venv/bin/activate`).
- Existing tests must pass at every commit (`python -m pytest -q` from repo root) — baseline going into this plan is 3,236 passed.
- Commit after every task using `caveman-commit` conventions (Conventional Commits, imperative subject ≤50 chars).
- Full spec: `docs/superpowers/specs/2026-07-14-list-definition-truncation-design.md`.
- `complete_list_definitions` must be the **last** call in `builder.py`'s injection pipeline — after `inject_asterisk_refs`, `inject_quantities`, `inject_dates`, `inject_roles`, `inject_refs`, and `inject_note_refs`. This ordering is load-bearing: it's what makes every `<def>`'s collected list content already carry any `<ref>`/`<quantity>`/`<date>`/`<role>` tags those passes add, and what makes every sibling definition that inject_terms/inject_list_defs *did* tag already carry `<term refersTo>` by the time the term-boundary stop condition checks for it. Do not move it earlier.
- No new AKN element nesting — `<def>` accumulates flat mixed content (text + copied inline elements), matching how `<def>` already carries nested `<ref>` elsewhere in the corpus (e.g. `age-discrimination-act-2004.xml`'s `Commissioner` definition). Do not attempt to nest `<blockList>` inside `<def>` — that has an open, unresolved AKN schema-validity question from v0.6.0, out of scope here.
- **`inject_list_defs`'s "exactly one `<p>` per `<content>`" gate is a real, separate, out-of-scope gap** (confirmed 2026-07-14, found by independent plan review against `bankruptcy-act-1966.xml`): a definition lead-in sharing its `<content>` with an unrelated sentence is never tagged with `<term>` at all, regardless of pipeline position. `_looks_like_new_definition` (Task 2) exists specifically to make the term-boundary stop condition robust to this — it does NOT fix the underlying gate, and this plan does not widen `inject_list_defs` to catch these cases. If a future plan does widen that gate, `_looks_like_new_definition` becomes redundant for the cases it starts catching (harmless — it'd just never trigger for an already-tagged `<p>`, since the `<term refersTo>` check comes first) but should not be removed, since other untagged shapes may still exist.
- **Do not run `lexau export-hf`, `lexau site`, or create a git tag** — those are gated on explicit user go-ahead, past this plan's scope (see Task 5's stop point).

---

## Task 1: `_find_qualifying_anchor` — locate where the orphaned list actually lives

**Files:**
- Modify: `src/lexau/termlinks.py` (add `_DEF_TAG` constant near the existing tag constants at line 130-133; add `_find_qualifying_anchor` function after `inject_list_defs`, end of file)
- Test: `tests/test_termlinks.py`

**Interfaces:**
- Consumes: nothing new — operates on an existing `<def>` element (`etree._Element`), using the module's existing `_P_TAG`, `_CONTENT_TAG`, `_SECTION_TAG`, `_PARA_TAG`, `_BLOCKLIST_TAG` constants.
- Produces: `_find_qualifying_anchor(def_el: etree._Element) -> etree._Element | None` (new module-level function in `termlinks.py`) — returns the ancestor element whose immediate following siblings include a `<paragraph>`/`<blockList>`, or `None` if no such level exists before the enclosing `<section>`. Consumed by Task 2.

### Step 1: Write the failing tests

Add to `tests/test_termlinks.py`, after the existing `inject_list_defs` tests (after line ~686, end of file):

```python
def _make_level0_def(show_as: str, eid: str, def_text: str, list_items: list[str]) -> etree._Element:
    """Build a <section> with an already-injected <term>+<def> pair (the
    truncated shape _process_p produces today) directly followed, at the
    same tree level, by <paragraph> list items -- the level-0 shape."""
    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section", eId="sec-6")
    h = etree.SubElement(sec, f"{AKN_TAG}heading")
    h.text = "Definitions"
    subsec = etree.SubElement(sec, f"{AKN_TAG}subsection", eId="sec-6__subsec-1")
    content = etree.SubElement(subsec, f"{AKN_TAG}content")
    p = etree.SubElement(content, f"{AKN_TAG}p")
    term_el = etree.SubElement(p, f"{AKN_TAG}term")
    term_el.set("refersTo", f"#{eid}")
    term_el.text = show_as
    term_el.tail = " means "
    def_el = etree.SubElement(p, f"{AKN_TAG}def")
    def_el.text = def_text
    for i, item_text in enumerate(list_items, start=1):
        para = etree.SubElement(subsec, f"{AKN_TAG}paragraph", eId=f"sec-6__subsec-1__para-{i}")
        c = etree.SubElement(para, f"{AKN_TAG}content")
        ip = etree.SubElement(c, f"{AKN_TAG}p")
        ip.text = item_text
    return root


def test_find_qualifying_anchor_level_0():
    """When the <def>'s own <content> is immediately followed by a
    <paragraph>, that <content> itself is the anchor (level 0)."""
    from lexau.termlinks import _find_qualifying_anchor

    root = _make_level0_def(
        "collective work", "term-collective-work", "any of the following:",
        ["an encyclopaedia;", "a newspaper;"],
    )
    def_el = root.find(f".//{AKN_TAG}def")
    anchor = _find_qualifying_anchor(def_el)
    assert anchor is not None
    assert anchor.tag == f"{AKN_TAG}content"


def test_find_qualifying_anchor_level_1_nested():
    """When the <def>'s <content> is nested inside an outer <paragraph> with
    no following siblings of its own, walk up one level to find the outer
    <paragraph>'s following siblings (mirrors bankruptcy-act-1966.xml's
    'related entity' shape)."""
    from lexau.termlinks import _find_qualifying_anchor

    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section", eId="sec-5")
    h = etree.SubElement(sec, f"{AKN_TAG}heading")
    h.text = "Interpretation"
    subsec = etree.SubElement(sec, f"{AKN_TAG}subsection", eId="sec-5__subsec-1")

    outer = etree.SubElement(subsec, f"{AKN_TAG}paragraph", eId="sec-5__subsec-1__para-b")
    c1 = etree.SubElement(outer, f"{AKN_TAG}content")
    p1 = etree.SubElement(c1, f"{AKN_TAG}p")
    p1.text = "a Registrar of the Court."
    c2 = etree.SubElement(outer, f"{AKN_TAG}content")
    p2 = etree.SubElement(c2, f"{AKN_TAG}p")
    term_el = etree.SubElement(p2, f"{AKN_TAG}term")
    term_el.set("refersTo", "#term-related-entity")
    term_el.text = "related entity"
    term_el.tail = " means "
    def_el = etree.SubElement(p2, f"{AKN_TAG}def")
    def_el.text = "any of the following:"

    etree.SubElement(subsec, f"{AKN_TAG}paragraph", eId="sec-5__subsec-1__para-a")

    anchor = _find_qualifying_anchor(def_el)
    assert anchor is not None
    assert anchor.tag == f"{AKN_TAG}paragraph"
    assert anchor.get("eId") == "sec-5__subsec-1__para-b"


def test_find_qualifying_anchor_no_following_list_returns_none():
    """A colon-terminated <def> with genuinely no following list content
    anywhere returns None."""
    from lexau.termlinks import _find_qualifying_anchor

    root = _make_level0_def(
        "class", "term-class", "any of these:", [],
    )
    def_el = root.find(f".//{AKN_TAG}def")
    anchor = _find_qualifying_anchor(def_el)
    assert anchor is None
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/test_termlinks.py -k find_qualifying_anchor -v`
Expected: FAIL with `ImportError: cannot import name '_find_qualifying_anchor'`

### Step 3: Write the implementation

In `src/lexau/termlinks.py`, add the new tag constant next to the existing ones (around line 133, after `_BLOCKLIST_TAG`):

```python
_DEF_TAG       = f"{AKN_TAG}def"
```

Add the function at the end of the file, after `inject_list_defs`:

```python
def _find_qualifying_anchor(def_el: etree._Element) -> etree._Element | None:
    """Walk up from def_el's <p>'s <content> parent until a level is found
    whose immediate following siblings include a <paragraph> or <blockList>.

    Real corpus definitions nest at different depths -- some colon-terminated
    <def>s have their orphaned list content as direct siblings of their own
    <content> (level 0), others need one more level up to the enclosing
    <paragraph>'s siblings (level 1, the majority shape in the corpus --
    confirmed 2,649 of 3,136 real cases). The walk is not capped at level 1;
    it continues until it hits the enclosing <section> boundary.

    Returns the qualifying ancestor element (the node to walk forward from),
    or None if no such level exists.
    """
    p_el = def_el.getparent()
    if p_el is None or p_el.tag != _P_TAG:
        return None
    node = p_el.getparent()
    if node is None or node.tag != _CONTENT_TAG:
        return None
    while node is not None and node.tag != _SECTION_TAG:
        parent = node.getparent()
        if parent is None:
            return None
        siblings = list(parent)
        idx = siblings.index(node)
        following = siblings[idx + 1:]
        if any(c.tag in {_PARA_TAG, _BLOCKLIST_TAG} for c in following):
            return node
        node = parent
    return None
```

### Step 4: Run tests to verify they pass

Run: `python -m pytest tests/test_termlinks.py -k find_qualifying_anchor -v`
Expected: PASS (3 tests)

### Step 5: Run full suite, then commit

Run: `python -m pytest -q`
Expected: 3,239 passed (3,236 baseline + 3 new)

```bash
git add src/lexau/termlinks.py tests/test_termlinks.py
git commit -m "feat: add qualifying-anchor walk for truncated list defs"
```

---

## Task 2: `_collect_and_append_list_content` — term-boundary-aware forward walk

**Files:**
- Modify: `src/lexau/termlinks.py` (add `_append_list_item_content` and `_collect_and_append_list_content`, after `_find_qualifying_anchor`)
- Test: `tests/test_termlinks.py`

**Interfaces:**
- Consumes: `_find_qualifying_anchor` (Task 1) — the anchor element to walk forward from.
- Produces: `_collect_and_append_list_content(def_el: etree._Element, anchor_el: etree._Element) -> bool` — walks `anchor_el`'s following `<paragraph>`/`<blockList>` siblings, appending their content to `def_el`, stopping at the first `<content>` whose `<p>` contains a `<term refersTo>` element. Returns `True` if anything was appended. Consumed by Task 3.

### Step 1: Write the failing tests

Add to `tests/test_termlinks.py`:

```python
def test_collect_and_append_list_content_simple():
    """Two plain-text list items get appended to <def> in order."""
    from lexau.termlinks import _collect_and_append_list_content

    root = _make_level0_def(
        "collective work", "term-collective-work", "any of the following:",
        ["an encyclopaedia, dictionary or similar work;", "a newspaper or periodical."],
    )
    def_el = root.find(f".//{AKN_TAG}def")
    anchor = def_el.getparent().getparent()  # <content>, level 0
    result = _collect_and_append_list_content(def_el, anchor)
    assert result is True
    text = "".join(def_el.itertext())
    assert "an encyclopaedia, dictionary or similar work;" in text
    assert "a newspaper or periodical." in text
    # Order preserved
    assert text.index("encyclopaedia") < text.index("newspaper")


def test_collect_and_append_list_content_stops_at_next_term():
    """Collection stops at the first <content> whose <p> contains a
    <term refersTo> element -- it does not swallow the next definition."""
    from lexau.termlinks import _collect_and_append_list_content

    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section", eId="sec-5")
    h = etree.SubElement(sec, f"{AKN_TAG}heading")
    h.text = "Interpretation"
    subsec = etree.SubElement(sec, f"{AKN_TAG}subsection", eId="sec-5__subsec-1")

    content = etree.SubElement(subsec, f"{AKN_TAG}content")
    p = etree.SubElement(content, f"{AKN_TAG}p")
    term_el = etree.SubElement(p, f"{AKN_TAG}term")
    term_el.set("refersTo", "#term-related-entity")
    term_el.text = "related entity"
    term_el.tail = " means "
    def_el = etree.SubElement(p, f"{AKN_TAG}def")
    def_el.text = "any of the following:"

    item_a = etree.SubElement(subsec, f"{AKN_TAG}paragraph", eId="sec-5__subsec-1__para-a")
    ca = etree.SubElement(item_a, f"{AKN_TAG}content")
    pa = etree.SubElement(ca, f"{AKN_TAG}p")
    pa.text = "a relative of the person;"

    # This paragraph carries BOTH the last list item AND the start of the
    # next term's definition, in a second <content> -- the confirmed real shape.
    item_b = etree.SubElement(subsec, f"{AKN_TAG}paragraph", eId="sec-5__subsec-1__para-b")
    cb1 = etree.SubElement(item_b, f"{AKN_TAG}content")
    pb1 = etree.SubElement(cb1, f"{AKN_TAG}p")
    pb1.text = "a body corporate of which the person is a director;"
    cb2 = etree.SubElement(item_b, f"{AKN_TAG}content")
    pb2 = etree.SubElement(cb2, f"{AKN_TAG}p")
    next_term_el = etree.SubElement(pb2, f"{AKN_TAG}term")
    next_term_el.set("refersTo", "#term-relative")
    next_term_el.text = "relative"
    next_term_el.tail = " means "
    etree.SubElement(pb2, f"{AKN_TAG}def").text = "in relation to a person:"

    result = _collect_and_append_list_content(def_el, content)
    assert result is True
    text = "".join(def_el.itertext())
    assert "a relative of the person" in text
    assert "a body corporate of which the person is a director" in text
    assert "relative" not in text.replace("a relative of the person", "")


def test_collect_and_append_list_content_preserves_inline_markup():
    """Child elements (<ref>, etc.) inside a list item are deep-copied into
    <def>, not flattened to text."""
    from lexau.termlinks import _collect_and_append_list_content

    root = _make_level0_def(
        "related entity", "term-related-entity", "any of the following:", [],
    )
    subsec = root.find(f".//{AKN_TAG}subsection")
    def_el = root.find(f".//{AKN_TAG}def")
    anchor = def_el.getparent().getparent()

    item = etree.SubElement(subsec, f"{AKN_TAG}paragraph", eId="sec-6__subsec-1__para-a")
    item_content = etree.SubElement(item, f"{AKN_TAG}content")
    item_p = etree.SubElement(item_content, f"{AKN_TAG}p")
    item_p.text = "a Registrar of the Court ("
    ref_el = etree.SubElement(item_p, f"{AKN_TAG}ref", href="#dvs-2")
    ref_el.text = "Division 2"
    ref_el.tail = ")."

    result = _collect_and_append_list_content(def_el, anchor)
    assert result is True
    ref_in_def = def_el.find(f"{AKN_TAG}ref")
    assert ref_in_def is not None
    assert ref_in_def.get("href") == "#dvs-2"
    assert ref_in_def.text == "Division 2"
    assert ref_in_def.tail == ")."
    assert "a Registrar of the Court (" in (def_el.text or "")


def test_collect_and_append_list_content_no_list_returns_false():
    """anchor with no following <paragraph>/<blockList> sibling returns False,
    and def_el is left unmodified."""
    from lexau.termlinks import _collect_and_append_list_content

    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    sec = etree.SubElement(root, f"{AKN_TAG}section", eId="sec-1")
    content = etree.SubElement(sec, f"{AKN_TAG}content")
    p = etree.SubElement(content, f"{AKN_TAG}p")
    def_el = etree.SubElement(p, f"{AKN_TAG}def")
    def_el.text = "any of these:"

    result = _collect_and_append_list_content(def_el, content)
    assert result is False
    assert def_el.text == "any of these:"
    assert len(def_el) == 0


def test_collect_and_append_list_content_stops_at_untagged_lookalike():
    """Mirrors bankruptcy-act-1966.xml's REAL related-entity -> relative
    boundary: relative is never tagged with <term> at all, because its
    <content> has two <p> siblings (an unrelated sentence, then relative's
    own lead-in) -- inject_list_defs's "exactly one <p> per <content>" gate
    skips it. _looks_like_new_definition must still catch this as a
    boundary. Also exercises the multi-<p>-per-<content> iteration fix:
    the unrelated sentence and relative's lead-in are BOTH <p> children of
    the SAME <content> (ci below) -- a plain .find() would only ever see
    the first one and miss the boundary entirely."""
    from lexau.termlinks import _collect_and_append_list_content

    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section", eId="sec-5")
    h = etree.SubElement(sec, f"{AKN_TAG}heading")
    h.text = "Interpretation"
    subsec = etree.SubElement(sec, f"{AKN_TAG}subsection", eId="sec-5__subsec-1")

    content = etree.SubElement(subsec, f"{AKN_TAG}content")
    p = etree.SubElement(content, f"{AKN_TAG}p")
    term_el = etree.SubElement(p, f"{AKN_TAG}term")
    term_el.set("refersTo", "#term-related-entity")
    term_el.text = "related entity"
    term_el.tail = " means "
    def_el = etree.SubElement(p, f"{AKN_TAG}def")
    def_el.text = "any of the following:"

    item_a = etree.SubElement(subsec, f"{AKN_TAG}paragraph", eId="sec-5__subsec-1__para-a")
    ca = etree.SubElement(item_a, f"{AKN_TAG}content")
    etree.SubElement(ca, f"{AKN_TAG}p").text = "a relative of the person;"

    # Real shape: ONE <content> with TWO <p> children.
    item_i = etree.SubElement(subsec, f"{AKN_TAG}paragraph", eId="sec-5__subsec-1__para-i")
    ci = etree.SubElement(item_i, f"{AKN_TAG}content")
    etree.SubElement(ci, f"{AKN_TAG}p").text = "a member of a partnership of which the person is a member;"
    etree.SubElement(ci, f"{AKN_TAG}p").text = "relative, in relation to a person, means:"

    # relative's own following list -- must not be swallowed either.
    r_item_a = etree.SubElement(subsec, f"{AKN_TAG}paragraph", eId="sec-5__subsec-1__para-a")
    rca = etree.SubElement(r_item_a, f"{AKN_TAG}content")
    etree.SubElement(rca, f"{AKN_TAG}p").text = "the spouse of the person; or"

    result = _collect_and_append_list_content(def_el, content)
    assert result is True
    text = "".join(def_el.itertext())
    assert "a relative of the person" in text
    assert "a member of a partnership" in text
    assert "relative, in relation to a person" not in text
    assert "the spouse of the person" not in text
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/test_termlinks.py -k collect_and_append_list_content -v`
Expected: FAIL with `ImportError: cannot import name '_collect_and_append_list_content'`

### Step 3: Write the implementation

Add `import copy` to `src/lexau/termlinks.py`'s existing import block (currently just `import re` / `from lxml import etree` at the top of the file):

```python
import copy
import re
from lxml import etree
```

Add to `src/lexau/termlinks.py`, after `_find_qualifying_anchor`:

```python
def _append_list_item_content(def_el: etree._Element, p_el: etree._Element) -> None:
    """Append one list item's rendered content (mixed text + inline markup)
    to def_el, deep-copying any child elements (<ref>, <i>, etc.) so already-
    applied markup from upstream passes survives.

    No synthetic numbering ("(a) ") is added -- real corpus list items already
    carry their own trailing punctuation ("; or", "; and", ".") and some (not
    all) embed their own inline numbering, so a <num>-derived prefix risks
    doubling it. A single space separates each item from what precedes it.
    """
    children = list(def_el)
    if children:
        last = children[-1]
        last.tail = (last.tail or "") + " " + (p_el.text or "")
    else:
        def_el.text = (def_el.text or "") + " " + (p_el.text or "")
    for child in p_el:
        def_el.append(copy.deepcopy(child))


def _looks_like_new_definition(item_p: etree._Element) -> bool:
    """True if item_p's own text matches a definition-start pattern, even
    though it hasn't been tagged with <term> yet.

    Real corpus gap, confirmed 2026-07-14 against bankruptcy-act-1966.xml:
    inject_list_defs requires exactly one <p> child per <content> before it
    will convert anything. When a definition's lead-in shares its <content>
    with an unrelated preceding sentence -- confirmed real case, 'relative,
    in relation to a person, means:' sits in the same <content> as 'For the
    purposes of paragraph (c)...' -- inject_list_defs skips it entirely, and
    it's never tagged. _collect_and_append_list_content's <term refersTo>
    check alone can't see this as a boundary, so this function re-applies
    inject_terms/inject_list_defs's own patterns and false-positive guards
    here, purely as a stop signal -- nothing gets tagged by this check, nor
    does it fix the underlying inject_list_defs gap (out of scope here; see
    the plan's Global Constraints).
    """
    text = "".join(item_p.itertext()).strip()

    list_def_match = _LIST_DEF_COLON_RE.match(text)
    if list_def_match and not _is_narrative_false_positive(list_def_match.group(1).strip()):
        return True

    for pattern in _DEF_PATTERNS:
        m = pattern.match(text)
        if not m:
            continue
        prefix_before_connector = text[:m.start(2)]
        if _FALSE_CONNECTOR_TAIL_RE.search(prefix_before_connector):
            continue
        if _is_narrative_false_positive(m.group(1).strip()):
            continue
        return True

    return False


def _collect_and_append_list_content(
    def_el: etree._Element, anchor_el: etree._Element
) -> bool:
    """Walk anchor_el's following <paragraph>/<blockList> siblings in document
    order, appending each <content>'s <p> children (there can be more than
    one per <content> -- see the multi-<p> shape below) to def_el via
    _append_list_item_content, until a <p> is found that's either already
    tagged with <term refersTo> (the common case -- reliable because this
    function runs after inject_terms/inject_list_defs have swept the whole
    document, see complete_list_definitions' docstring in Task 3) OR looks
    like an untagged definition start per _looks_like_new_definition (the
    fallback for definitions inject_list_defs's own gate missed -- see that
    function's docstring).

    Iterates content_el.findall(_P_TAG), not .find() -- a single <content>
    can hold more than one <p> (confirmed real shape: bankruptcy-act-1966.xml's
    'relative' lead-in shares a <content> with an unrelated preceding
    sentence). Using .find() would silently see only the first <p> and miss
    a boundary sitting in the second.

    Returns True if any content was appended.
    """
    parent = anchor_el.getparent()
    siblings = list(parent)
    idx = siblings.index(anchor_el)
    appended = False
    for sib in siblings[idx + 1:]:
        if sib.tag not in {_PARA_TAG, _BLOCKLIST_TAG}:
            break
        stop = False
        for content_el in sib.findall(_CONTENT_TAG):
            for item_p in content_el.findall(_P_TAG):
                if item_p.find(f"{AKN_TAG}term") is not None or _looks_like_new_definition(item_p):
                    stop = True
                    break
                _append_list_item_content(def_el, item_p)
                appended = True
            if stop:
                break
        if stop:
            break
    return appended
```

### Step 4: Run tests to verify they pass

Run: `python -m pytest tests/test_termlinks.py -k collect_and_append_list_content -v`
Expected: PASS (all tests in this task, including the two new ones added below)

### Step 5: Run full suite, then commit

Run: `python -m pytest -q`
Expected: all tests pass, including the new ones added in this task

```bash
git add src/lexau/termlinks.py tests/test_termlinks.py
git commit -m "feat: add term-boundary-aware list content collection"
```

---

## Task 3: `complete_list_definitions` — top-level pass, wired into the pipeline

**Files:**
- Modify: `src/lexau/termlinks.py` (add `complete_list_definitions`, after `_collect_and_append_list_content`)
- Modify: `src/lexau/builder.py:15` (import), `src/lexau/builder.py:1067` area (call site, after `inject_note_refs`)
- Modify: `src/lexau/models.py:82-83` (add `list_defs_completed` field to `ParseReport`)
- Test: `tests/test_termlinks.py`, `tests/test_builder.py`

**Interfaces:**
- Consumes: `_find_qualifying_anchor` (Task 1), `_collect_and_append_list_content` (Task 2).
- Produces: `complete_list_definitions(root: etree._Element) -> int` — public, called from `builder.py`. Returns count of `<def>` elements completed. `ParseReport.list_defs_completed: int` — new report field, consumed by `cli.py`'s summary output (no change needed there — it already iterates `ParseReport` fields generically; verify this in Step 5).

### Step 1: Write the failing tests

Add to `tests/test_termlinks.py`:

```python
def test_complete_list_definitions_level_0():
    from lexau.termlinks import complete_list_definitions

    root = _make_level0_def(
        "collective work", "term-collective-work", "any of the following:",
        ["an encyclopaedia;", "a newspaper;"],
    )
    count = complete_list_definitions(root)
    assert count == 1
    def_el = root.find(f".//{AKN_TAG}def")
    text = "".join(def_el.itertext())
    assert "an encyclopaedia" in text
    assert "a newspaper" in text


def test_complete_list_definitions_no_following_list_left_untouched():
    from lexau.termlinks import complete_list_definitions

    root = _make_level0_def("class", "term-class", "any of these:", [])
    count = complete_list_definitions(root)
    assert count == 0
    def_el = root.find(f".//{AKN_TAG}def")
    assert def_el.text == "any of these:"


def test_complete_list_definitions_non_colon_def_untouched():
    """A <def> that doesn't end in a colon is never touched, regardless of
    what paragraphs happen to follow it."""
    from lexau.termlinks import complete_list_definitions

    root = _make_level0_def(
        "commission", "term-commission", "the Australian Human Rights Commission.",
        ["some unrelated following paragraph."],
    )
    count = complete_list_definitions(root)
    assert count == 0
    def_el = root.find(f".//{AKN_TAG}def")
    assert def_el.text == "the Australian Human Rights Commission."


def test_complete_list_definitions_stops_at_next_term_reused_eids():
    """Mirrors bankruptcy-act-1966.xml's REAL related-entity -> relative
    pair exactly, including the real (and initially surprising) fact that
    relative is NEVER tagged with <term> at all -- inject_list_defs's
    "exactly one <p> per <content>" gate skips it, because its <content>
    holds relative's lead-in alongside an unrelated preceding sentence.
    related-entity's <def> must be completed with exactly its own list
    items; relative's list must not be swallowed, and relative itself must
    NOT be spuriously completed (it has no <def> to complete -- being
    untagged is a separate, out-of-scope gap, not something this function
    fixes). Also reuses the reused-eId-suffix pattern (para-a repeats) from
    the real corpus, confirming eId collisions don't confuse the tree-
    position-based walk."""
    from lexau.termlinks import complete_list_definitions

    root = etree.Element(f"{AKN_TAG}akomaNtoso")
    act = etree.SubElement(root, f"{AKN_TAG}act")
    body = etree.SubElement(act, f"{AKN_TAG}body")
    sec = etree.SubElement(body, f"{AKN_TAG}section", eId="sec-5")
    h = etree.SubElement(sec, f"{AKN_TAG}heading")
    h.text = "Interpretation"
    subsec = etree.SubElement(sec, f"{AKN_TAG}subsection", eId="sec-5__subsec-1")

    # related-entity's truncated <term>+<def>, nested in an outer paragraph
    # alongside unrelated prior content (level-1 shape, as in Task 1/2).
    outer = etree.SubElement(subsec, f"{AKN_TAG}paragraph", eId="sec-5__subsec-1__para-b")
    c1 = etree.SubElement(outer, f"{AKN_TAG}content")
    etree.SubElement(c1, f"{AKN_TAG}p").text = "a Registrar of the Court."
    c2 = etree.SubElement(outer, f"{AKN_TAG}content")
    p2 = etree.SubElement(c2, f"{AKN_TAG}p")
    term_el = etree.SubElement(p2, f"{AKN_TAG}term")
    term_el.set("refersTo", "#term-related-entity")
    term_el.text = "related entity"
    term_el.tail = " means "
    def_el = etree.SubElement(p2, f"{AKN_TAG}def")
    def_el.text = "any of the following:"

    # related-entity's own list: one plain item, then a paragraph whose
    # <content> holds TWO <p> children -- the last list item, and relative's
    # UNTAGGED lead-in. Real shape, confirmed 2026-07-14.
    item_a = etree.SubElement(subsec, f"{AKN_TAG}paragraph", eId="sec-5__subsec-1__para-a")
    ca = etree.SubElement(item_a, f"{AKN_TAG}content")
    etree.SubElement(ca, f"{AKN_TAG}p").text = "a relative of the person;"

    item_i = etree.SubElement(subsec, f"{AKN_TAG}paragraph", eId="sec-5__subsec-1__para-i")
    ci = etree.SubElement(item_i, f"{AKN_TAG}content")
    etree.SubElement(ci, f"{AKN_TAG}p").text = "a member of a partnership of which the person is a member;"
    etree.SubElement(ci, f"{AKN_TAG}p").text = "relative, in relation to a person, means:"

    # relative's own list item, following -- reuses eId "para-a" (real
    # corpus does this too). Must not be swallowed into related-entity's def.
    r_item_a = etree.SubElement(subsec, f"{AKN_TAG}paragraph", eId="sec-5__subsec-1__para-a")
    rca = etree.SubElement(r_item_a, f"{AKN_TAG}content")
    etree.SubElement(rca, f"{AKN_TAG}p").text = "the spouse of the person; or"

    count = complete_list_definitions(root)
    assert count == 1  # only related-entity has a <def> to complete

    def_els = root.findall(f".//{AKN_TAG}def")
    assert len(def_els) == 1
    related_text = "".join(def_els[0].itertext())

    assert "a relative of the person" in related_text
    assert "a member of a partnership of which the person is a member" in related_text
    assert "relative, in relation to a person" not in related_text
    assert "the spouse of the person" not in related_text
```

### Step 2: Run tests to verify they fail

Run: `python -m pytest tests/test_termlinks.py -k complete_list_definitions -v`
Expected: FAIL with `ImportError: cannot import name 'complete_list_definitions'`

### Step 3: Write the implementation

Add to `src/lexau/termlinks.py`, after `_collect_and_append_list_content` (end of file):

```python
def complete_list_definitions(root: etree._Element) -> int:
    """Find colon-terminated <def> elements and fold in their orphaned list
    content from following AKN siblings.

    Must run as the LAST step in builder.py's injection pipeline -- after
    inject_asterisk_refs, inject_quantities, inject_dates, inject_roles,
    inject_refs, and inject_note_refs. Two reasons, both load-bearing:

    1. Those five passes skip any element that already has child nodes (how
       each detects "not yet processed" -- see quantlinks.py/reflinks.py).
       Running this pass last means the list-item content it copies into
       <def> already carries whatever markup those passes added; running it
       first would give <def> children before those passes see it, and they'd
       silently skip it.
    2. _collect_and_append_list_content's term-boundary stop condition checks
       for <term refersTo> on the *next* definition. That's only reliable for
       definitions inject_terms/inject_list_defs actually tagged, which is
       true once they've swept the whole document, but NOT true mid-sweep (a
       list-form definition immediately following another list-form
       definition would not yet be tagged if this ran inline during that
       same sweep). Some real definitions are never tagged at all, for a
       separate reason unrelated to pipeline position -- confirmed real case,
       bankruptcy-act-1966.xml's "relative" sits in a <content> alongside an
       unrelated sentence, and inject_list_defs's "exactly one <p> per
       <content>" gate skips it regardless of when anything runs.
       _looks_like_new_definition (Task 2) is the fallback for that case --
       it doesn't depend on pipeline position at all, only on the untagged
       text itself looking like a definition start.

    Returns count of <def> elements completed.
    """
    count = 0
    for def_el in list(root.iter(_DEF_TAG)):
        text = "".join(def_el.itertext()).strip()
        if not text.endswith(":"):
            continue
        anchor = _find_qualifying_anchor(def_el)
        if anchor is None:
            continue
        if _collect_and_append_list_content(def_el, anchor):
            count += 1
    return count
```

Add the report field to `src/lexau/models.py`, after line 83 (`asterisk_unresolved: int = 0`):

```python
    # v0.7.2 additions
    list_defs_completed: int = 0
```

Update `src/lexau/builder.py`:

Line 15, add the new import:
```python
from lexau.termlinks import inject_terms, inject_list_defs, complete_list_definitions
```

After the `inject_note_refs` call (after line 1067, before the `# 6. Populate <references>` comment):

```python
        # 4b. Complete truncated list-form <def>s (colon-terminated definiens
        # with orphaned list content in sibling <paragraph>/<blockList>
        # elements). MUST run last -- see complete_list_definitions' docstring.
        list_defs_completed = complete_list_definitions(root)
        report.list_defs_completed = list_defs_completed
```

### Step 4: Run tests to verify they pass

Run: `python -m pytest tests/test_termlinks.py -k complete_list_definitions -v`
Expected: PASS (4 tests)

### Step 5: Add the builder end-to-end test, verify cli.py needs no change

Add to `tests/test_builder.py`, after `test_build_with_report_list_defs_found` (after line 1253):

```python
def test_build_with_report_list_defs_completed(meta):
    """build_with_report folds orphaned list content into a truncated <def>
    via complete_list_definitions, and reports the count."""
    from unittest.mock import patch
    from lexau.endnote_parser import EndnoteResult

    b = AknBuilder(meta)
    b.add(ParsedParagraph(ElementType.SECTION, number="6", heading="Definitions"))
    b.add(ParsedParagraph(ElementType.SUBSECTION, number="1", text=""))
    b.add(ParsedParagraph(ElementType.BODY, text="eligible entity means any of the following:"))
    b.add(ParsedParagraph(ElementType.PARAGRAPH, number="a", text="a body corporate; or"))
    b.add(ParsedParagraph(ElementType.PARAGRAPH, number="b", text="a natural person."))

    corpus_index: dict = {}
    with patch("lexau.builder.parse_endnotes", return_value=EndnoteResult([], [])):
        xml, report = b.build_with_report(corpus_index, last_volume_path=None)

    assert report.list_defs_completed >= 1
    ns = {"akn": AKN_NS}
    def_el = xml.find(".//akn:def", ns)
    assert def_el is not None
    text = "".join(def_el.itertext())
    assert "a body corporate" in text
    assert "a natural person" in text
```

`src/lexau/cli.py` prints `ParseReport` fields by explicit name in a fixed-width table (lines 93-108), not generic iteration — add `list_defs_completed` as a new column. Change line 97 from:

```python
            f"{'Terms':>5} {'DupT':>4} {'Qtys':>4} {'Roles':>5} {'NtRef':>5}"
```

to:

```python
            f"{'Terms':>5} {'DupT':>4} {'Qtys':>4} {'Roles':>5} {'NtRef':>5} {'LDefC':>5}"
```

And change lines 106-107 from:

```python
                f"{r.terms_found:>5} {r.duplicate_terms:>4} {r.quantities_found:>4} "
                f"{r.roles_found:>5} {r.note_refs_injected:>5}"
```

to:

```python
                f"{r.terms_found:>5} {r.duplicate_terms:>4} {r.quantities_found:>4} "
                f"{r.roles_found:>5} {r.note_refs_injected:>5} {r.list_defs_completed:>5}"
```

Run: `python -m pytest tests/test_builder.py -k list_defs_completed -v`
Expected: PASS (1 test)

### Step 6: Run full suite, then commit

Run: `python -m pytest -q`
Expected: all tests pass — baseline (3,236) plus every test added across Tasks 1-3 (3 from Task 1, 6 from Task 2, 4 from Task 3's termlinks tests, 1 builder end-to-end test)

```bash
git add src/lexau/termlinks.py src/lexau/builder.py src/lexau/models.py src/lexau/cli.py tests/test_termlinks.py tests/test_builder.py
git commit -m "feat: wire complete_list_definitions into build pipeline"
```

---

## Task 4: Full-corpus verification gate (no rebuild yet — read-only check)

**Files:**
- Create: `scripts/verify_list_definitions.py` (one-off verification script, not a permanent CLI command — mirrors the ad-hoc verification approach used for the 2026-07-13 narrative-FP-guards fix)

**Interfaces:**
- Consumes: `complete_list_definitions` (Task 3), the existing corpus at `corpus/xml/*.xml`.
- Produces: a printed report — no return value consumed elsewhere. This is a manual verification gate, not part of the build pipeline.

### Step 1: Write the verification script

Create `scripts/verify_list_definitions.py`:

```python
"""One-off verification: run complete_list_definitions against every
existing corpus/xml/*.xml file (WITHOUT writing anything back) and report
how many <def> elements it would complete, cross-checked against the spec's
verified count (3,136 qualifying cases across the corpus).

This does NOT rebuild the corpus -- it re-parses each already-built XML file,
runs complete_list_definitions on an in-memory copy, and reports counts. The
actual corpus rebuild (which re-runs the full lexau build pipeline from DOCX)
is Task 5, gated on this script's output looking correct.
"""
import glob
from lxml import etree
from lexau.termlinks import complete_list_definitions

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
AKN = f"{{{AKN_NS}}}"


def main() -> None:
    total_completed = 0
    total_files_affected = 0
    errors = []

    for path in sorted(glob.glob("corpus/xml/*.xml")):
        try:
            root = etree.parse(path).getroot()
        except etree.XMLSyntaxError as e:
            errors.append((path, str(e)))
            continue
        count = complete_list_definitions(root)
        if count > 0:
            total_files_affected += 1
            total_completed += count

    print(f"Files affected: {total_files_affected}")
    print(f"<def> elements completed: {total_completed}")
    print(f"Parse errors: {len(errors)}")
    for path, err in errors[:10]:
        print(f"  {path}: {err}")

    print()
    print("Spot-check: bankruptcy-act-1966.xml related-entity / relative pair")
    root = etree.parse("corpus/xml/bankruptcy-act-1966.xml").getroot()
    complete_list_definitions(root)

    related_entity_def = None
    for def_el in root.iter(f"{AKN}def"):
        p_text = "".join(def_el.getparent().itertext())
        if p_text.startswith("related entity"):
            related_entity_def = def_el
            break

    assert related_entity_def is not None, "related-entity <def> not found -- corpus structure may have changed"
    related_text = "".join(related_entity_def.itertext())
    print(f"  related-entity <def> length after: {len(related_text)} chars")
    assert "spouse of the person" not in related_text, \
        "REGRESSION: related-entity swallowed relative's list"
    assert "relative, in relation to a person" not in related_text, \
        "REGRESSION: related-entity swallowed relative's own untagged lead-in text"

    # "relative" is expected to remain untagged (no <term>/<def> at all) --
    # a separate, known, out-of-scope gap in inject_list_defs (see Global
    # Constraints). This spot-check confirms that gap wasn't papered over by
    # accidentally absorbing relative's content into related-entity instead.
    relative_tagged = any(
        "relative" == (t.text or "").strip()
        for t in root.iter(f"{AKN}term")
    )
    print(f"  'relative' tagged as its own <term>: {relative_tagged} (expected: False -- known separate gap)")

    print("  Spot-check passed: no cross-contamination between the two definitions.")


if __name__ == "__main__":
    main()
```

### Step 2: Run it and evaluate against the spec's verified numbers

Run: `python scripts/verify_list_definitions.py`

Expected: "`<def>` elements completed" close to 3,136 (the spec's independently-verified qualifying count). Some drift is expected and fine — the spec's count was a static-analysis walk-up check using the same algorithm design as Task 1/2's implementation, not a byte-for-byte guarantee, and corpus files may have edge cases not in the 4 test fixtures above. Flag for manual review (not necessarily a bug) if the number is:
- Below ~2,800 (more than ~10% short of 3,136 — investigate why real cases aren't qualifying)
- Above ~3,300 (materially more than 3,136 — check whether the term-boundary stop condition is over-matching)

The bankruptcy-act-1966.xml spot-check assertions must pass with no `AssertionError`.

### Step 3: Commit the verification script

```bash
git add scripts/verify_list_definitions.py
git commit -m "test: add corpus-wide verification script for list defs"
```

**STOP POINT.** Do not proceed to a full corpus rebuild (`lexau build --list-file`), `lexau export-hf`, `lexau site`, or any git tag without explicit user go-ahead — those are destructive/costly operations (541-2,944-file rebuild, public HuggingFace re-publish) out of this plan's scope. Report the verification script's output and stop here.
