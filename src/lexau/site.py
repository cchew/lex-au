from __future__ import annotations

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
        self._site_dir.mkdir(parents=True, exist_ok=True)
        all_meta = sorted(self._corpus.all_metadata(), key=lambda m: m.name)

        act_list = [
            {
                "name": m.name,
                "site_path": f"/akn/au/act/{m.year}/{m.number}/",
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

            out_dir = (
                self._site_dir / "akn" / "au" / "act" / str(meta.year) / str(meta.number)
            )
            out_dir.mkdir(parents=True, exist_ok=True)

            # Serve the raw AKN XML alongside the rendered page, so the source
            # is reachable without a separate download from Hugging Face.
            shutil.copyfile(xml_path, out_dir / "source.xml")

            act_tmpl = self._env.get_template("act.html.j2")
            (out_dir / "index.html").write_text(
                act_tmpl.render(meta=meta, body=body_nodes), encoding="utf-8"
            )
