from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from lxml import etree
from markupsafe import Markup, escape

from lexau.corpus import Corpus
from lexau.models import ActMetadata

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
NS = {"akn": AKN_NS}

# Structural container elements that may nest other containers and sections.
_CONTAINER_TAGS = ("chapter", "part", "division", "subDivision")

# Inline elements that map directly onto an HTML tag of the same name and
# should render as actual styling. Every other inline element lex-au emits
# inside a <p> (ref, term, def, date, quantity, role, TLCTerm-referencing
# spans, noteRef, ...) is treated as a transparent wrapper: its own text and
# its children's text are kept, just without special styling — a static
# browse page doesn't need live jump-to-definition links, but it must not
# silently drop the words inside those elements.
_INLINE_HTML_TAGS = {"b", "i", "sup", "sub"}


@dataclass
class SectionNode:
    eid: str
    num: str
    heading: str
    tag: str
    paragraphs: list[Markup] = field(default_factory=list)
    children: list["SectionNode"] = field(default_factory=list)


def _instance_suffix(m: ActMetadata) -> str:
    """Intrinsic, per-Act disambiguating path segment for a colliding Act.

    Pure function of the Act's own identity: it reads no other Act, so two
    Acts can never be assigned the same suffix by accident and no Act's
    suffix can change because a different Act joined or left its collision
    group.

    Two components, both always emitted:

    - `title_id` (lowercased) -- legislation.gov.au's own Titles-API id
      (e.g. `C2004A04733`), the FRBR-identity field for the Act, and
      directly searchable back on legislation.gov.au.
    - a short digest of `safe_name` -- because `title_id` is *not* in fact
      unique per corpus entry. Verified against the live 3,078-Act corpus
      (2026-08-16): two pairs share a title_id outright --
      `C2004A00100` (Human Services (Medicare) Act 1973 / Health Insurance
      Commission Act 1973) and `C2004A03679` (Fair Work (Registered
      Organisations) Act 2009 / Workplace Relations Act 1996). Those pairs
      are the same legislative composition ingested twice under an old and
      a new Act title, so `comp_id`, `comp_num`, `effective_date`, `year`
      and `number` all tie too; `name` is the only differing field. Its
      derived `safe_name` is the corpus index key, hence unique per corpus
      entry by construction. It is hashed rather than inlined because raw
      safe_names are long and contain URL-awkward characters (parentheses,
      commas).

    The digest component is emitted even when the group's title_ids already
    differ. Making it conditional would reintroduce exactly the instability
    this replaces: a later Act arriving with a title_id matching an
    existing member would force that existing member's already-published
    URL to grow a digest.

    blake2b (not the builtin `hash()`) so the value is stable across
    processes and Python versions regardless of PYTHONHASHSEED.
    """
    digest = hashlib.blake2b(m.safe_name.encode("utf-8"), digest_size=4).hexdigest()
    return f"{m.title_id.lower()}-{digest}"


def _assign_site_paths(all_meta: list[ActMetadata]) -> dict[str, str]:
    """Map each Act's safe_name to its site path, disambiguating (year, number)
    collisions.

    `number` is an Act's number *within its enactment year* per
    legislation.gov.au's own scheme, not a globally unique identifier -- it
    isn't unique across collection/subCollection types (Act vs Regulation)
    or an old/new numbering-scheme mismatch, so two different Acts can
    legitimately share the same (year, number) pair.

    Acts in a group of one keep the bare `/akn/au/act/{year}/{number}/`
    path, byte-identical to what is published today (3,072 of 3,078 Acts in
    the live corpus). Every member of a colliding group instead gets
    `/akn/au/act/{year}/{number}-{suffix}/`, where the suffix is
    `_instance_suffix(m)` -- derived only from that Act's own identity, so:

    - No tie is possible and no ordering is consulted, so the mapping does
      not depend on `all_meta`'s iteration or sort order, and cannot flip if
      that order ever changes.
    - A new Act joining an existing collision group cannot move any
      existing member's URL onto different content -- the failure mode of
      an ordinal `-0`/`-1` suffix, which renumbers earlier members whenever
      a lower-sorting one arrives.

    Residual, accepted per the design spec: an Act that is *currently*
    alone in its group does move from the bare path to a suffixed one if a
    second Act later collides with it. Avoiding that would mean suffixing
    all 3,078 Acts, changing every already-published URL to fix a problem
    affecting six.
    """
    groups: dict[tuple[int, int], list[ActMetadata]] = {}
    for m in all_meta:
        groups.setdefault((m.year, m.number), []).append(m)

    paths: dict[str, str] = {}
    for (year, number), members in groups.items():
        if len(members) == 1:
            paths[members[0].safe_name] = f"/akn/au/act/{year}/{number}/"
        else:
            for m in members:
                paths[m.safe_name] = f"/akn/au/act/{year}/{number}-{_instance_suffix(m)}/"
    return paths


def _render_inline(elem: etree._Element) -> Markup:
    """Serialise a <p> (or any inline element)'s full mixed content to safe HTML.

    Using `elem.text` alone only returns the text *before* the first child
    element, silently truncating or dropping any paragraph containing a
    <ref>, <term>, <b>, etc. This walks the whole subtree instead.
    """
    parts = [escape(elem.text or "")]
    for child in elem:
        local = child.tag.split("}")[-1]
        inner = _render_inline(child)
        if local in _INLINE_HTML_TAGS:
            parts.append(Markup(f"<{local}>{inner}</{local}>"))
        else:
            parts.append(inner)
        parts.append(escape(child.tail or ""))
    return Markup("").join(parts)


def _direct_paragraphs(elem: etree._Element) -> list[Markup]:
    """Collect text of <p> elements under this element's own <content>, not nested sections."""
    paras: list[Markup] = []
    for content in elem.findall("akn:content", NS):
        for p in content.iter(f"{{{AKN_NS}}}p"):
            rendered = _render_inline(p)
            if rendered.strip():
                paras.append(rendered)
    return paras


def _make_node(elem: etree._Element) -> SectionNode:
    local = elem.tag.split("}")[-1]
    num_el = elem.find("akn:num", NS)
    head_el = elem.find("akn:heading", NS)
    node = SectionNode(
        eid=elem.get("eId", ""),
        num=num_el.text if num_el is not None else "",
        heading=head_el.text if head_el is not None else "",
        tag=local,
    )
    if local == "section":
        # Sections are leaves: pull every descendant <p>.
        for p in elem.iter(f"{{{AKN_NS}}}p"):
            rendered = _render_inline(p)
            if rendered.strip():
                node.paragraphs.append(rendered)
        return node

    # Container: collect its own direct content paragraphs, then recurse into
    # nested containers and sections.
    node.paragraphs.extend(_direct_paragraphs(elem))
    for sub in elem:
        sub_local = sub.tag.split("}")[-1]
        if sub_local in _CONTAINER_TAGS or sub_local == "section":
            node.children.append(_make_node(sub))
    return node


def _parse_body(xml_root: etree._Element) -> list[SectionNode]:
    body = xml_root.find(".//akn:body", NS)
    if body is None:
        return []
    nodes: list[SectionNode] = []
    for child in body:
        local = child.tag.split("}")[-1]
        if local in _CONTAINER_TAGS or local == "section":
            nodes.append(_make_node(child))
    return nodes


class SiteGenerator:
    def __init__(self, corpus: Corpus, site_dir: Path, templates_dir: Path) -> None:
        self._corpus = corpus
        self._site_dir = site_dir
        self._env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)

    def generate(self) -> None:
        # Full regeneration, not an incremental write: an Act that has left
        # the corpus, been renamed, or moved between a bare and a
        # disambiguated path would otherwise leave its previous page on
        # disk, published and stale, with nothing to overwrite it.
        shutil.rmtree(self._site_dir, ignore_errors=True)
        self._site_dir.mkdir(parents=True, exist_ok=True)
        all_meta = sorted(self._corpus.all_metadata(), key=lambda m: m.name)
        site_paths = _assign_site_paths(all_meta)

        act_list = [
            {
                "name": m.name,
                "site_path": site_paths[m.safe_name],
                "effective_date": m.effective_date.isoformat(),
            }
            for m in all_meta
        ]
        index_tmpl = self._env.get_template("index.html.j2")
        (self._site_dir / "index.html").write_text(
            index_tmpl.render(acts=act_list), encoding="utf-8"
        )

        for meta in all_meta:
            xml_path = self._corpus.root / "xml" / f"{meta.safe_name}.xml"
            if not xml_path.exists():
                continue
            xml_root = etree.parse(xml_path).getroot()
            body_nodes = _parse_body(xml_root)

            out_dir = self._site_dir / site_paths[meta.safe_name].strip("/")
            out_dir.mkdir(parents=True, exist_ok=True)

            # Serve the raw AKN XML alongside the rendered page, so the source
            # is reachable without a separate download from Hugging Face.
            shutil.copyfile(xml_path, out_dir / "source.xml")

            act_tmpl = self._env.get_template("act.html.j2")
            (out_dir / "index.html").write_text(
                act_tmpl.render(meta=meta, body=body_nodes), encoding="utf-8"
            )
