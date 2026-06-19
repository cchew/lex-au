from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from lxml import etree

from lexau.corpus import Corpus
from lexau.models import ActMetadata

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"
NS = {"akn": AKN_NS}


def _leaf_eid(eid: str) -> str:
    """Return the leaf segment of a compound eId for use as an HTML anchor id.

    e.g. 'part-I__sec-1' -> 'sec-1', 'sec-4' -> 'sec-4'
    """
    return eid.split("__")[-1] if eid else eid


@dataclass
class SectionNode:
    eid: str
    num: str
    heading: str
    tag: str
    paragraphs: list[str] = field(default_factory=list)
    children: list["SectionNode"] = field(default_factory=list)


def _parse_body(xml_root: etree._Element) -> list[SectionNode]:
    body = xml_root.find(".//akn:body", NS)
    if body is None:
        return []
    nodes: list[SectionNode] = []
    for child in body:
        local = child.tag.split("}")[-1]
        if local in ("part", "chapter", "division", "section"):
            num_el = child.find("akn:num", NS)
            head_el = child.find("akn:heading", NS)
            node = SectionNode(
                eid=_leaf_eid(child.get("eId", "")),
                num=num_el.text if num_el is not None else "",
                heading=head_el.text if head_el is not None else "",
                tag=local,
            )
            # Collect direct section children
            for sub in child:
                sub_local = sub.tag.split("}")[-1]
                if sub_local == "section":
                    sub_num = sub.find("akn:num", NS)
                    sub_head = sub.find("akn:heading", NS)
                    sec_node = SectionNode(
                        eid=_leaf_eid(sub.get("eId", "")),
                        num=sub_num.text if sub_num is not None else "",
                        heading=sub_head.text if sub_head is not None else "",
                        tag="section",
                    )
                    for p in sub.iter(f"{{{AKN_NS}}}p"):
                        if p.text:
                            sec_node.paragraphs.append(p.text)
                    node.children.append(sec_node)
                elif sub_local == "content":
                    for p in sub.iter(f"{{{AKN_NS}}}p"):
                        if p.text:
                            node.paragraphs.append(p.text)
            nodes.append(node)
        elif local == "section":
            # Top-level section (no parent Part)
            num_el = child.find("akn:num", NS)
            head_el = child.find("akn:heading", NS)
            node = SectionNode(
                eid=_leaf_eid(child.get("eId", "")),
                num=num_el.text if num_el is not None else "",
                heading=head_el.text if head_el is not None else "",
                tag="section",
            )
            for p in child.iter(f"{{{AKN_NS}}}p"):
                if p.text:
                    node.paragraphs.append(p.text)
            nodes.append(node)
    return nodes


class SiteGenerator:
    def __init__(self, corpus: Corpus, site_dir: Path, templates_dir: Path) -> None:
        self._corpus = corpus
        self._site_dir = site_dir
        self._env = Environment(loader=FileSystemLoader(str(templates_dir)), autoescape=True)

    def generate(self) -> None:
        self._site_dir.mkdir(parents=True, exist_ok=True)
        all_meta = self._corpus.all_metadata()

        act_list = [
            {
                "name": m.name,
                "site_path": f"/akn/au/act/{m.year}/{m.number}/",
                "effective_date": m.effective_date.isoformat(),
            }
            for m in all_meta
        ]
        index_tmpl = self._env.get_template("index.html.j2")
        (self._site_dir / "index.html").write_text(index_tmpl.render(acts=act_list))

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

            act_tmpl = self._env.get_template("act.html.j2")
            (out_dir / "index.html").write_text(
                act_tmpl.render(meta=meta, body=body_nodes)
            )
