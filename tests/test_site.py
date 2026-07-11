import pytest
from pathlib import Path
from lxml import etree
from datetime import date
from lexau.corpus import Corpus
from lexau.models import ActMetadata
from lexau.site import SiteGenerator, _render_inline, AKN_NS
from lexau.builder import AknBuilder
from lexau.parser import ParsedParagraph, ElementType


def _p(inner_xml: str) -> etree._Element:
    """Build a standalone <p> element from inner AKN markup for _render_inline tests."""
    return etree.fromstring(f'<p xmlns="{AKN_NS}">{inner_xml}</p>')


@pytest.fixture
def built_corpus(tmp_path, privacy_meta):
    corpus = Corpus(tmp_path / "corpus")
    builder = AknBuilder(privacy_meta)
    builder.add(ParsedParagraph(ElementType.PART, number="I", heading="Preliminary"))
    builder.add(ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"))
    builder.add(ParsedParagraph(ElementType.BODY, text="This Act is the Privacy Act 1988."))
    builder.add(ParsedParagraph(ElementType.SECTION, number="2", heading="Commencement"))
    xml, _validation = builder.build()
    corpus.save(privacy_meta, xml)
    return corpus


def test_generate_creates_index(tmp_path, built_corpus):
    site_dir = tmp_path / "site"
    gen = SiteGenerator(built_corpus, site_dir, templates_dir=Path("templates"))
    gen.generate()
    assert (site_dir / "index.html").exists()


def test_generate_creates_act_page(tmp_path, built_corpus, privacy_meta):
    site_dir = tmp_path / "site"
    gen = SiteGenerator(built_corpus, site_dir, templates_dir=Path("templates"))
    gen.generate()
    act_page = site_dir / "akn" / "au" / "act" / "1988" / "119" / "index.html"
    assert act_page.exists()


def test_act_page_contains_section_anchor(tmp_path, built_corpus):
    site_dir = tmp_path / "site"
    gen = SiteGenerator(built_corpus, site_dir, templates_dir=Path("templates"))
    gen.generate()
    act_page = site_dir / "akn" / "au" / "act" / "1988" / "119" / "index.html"
    content = act_page.read_text()
    # Anchor must be the full compound eId to avoid collisions between
    # like-numbered sections in different Parts (e.g. part-I__sec-1 vs part-II__sec-1).
    assert 'id="part-I__sec-1"' in content
    assert "Short title" in content


def test_generate_copies_raw_xml_alongside_page(tmp_path, built_corpus):
    site_dir = tmp_path / "site"
    gen = SiteGenerator(built_corpus, site_dir, templates_dir=Path("templates"))
    gen.generate()
    xml_copy = site_dir / "akn" / "au" / "act" / "1988" / "119" / "source.xml"
    assert xml_copy.exists()
    assert "akomaNtoso" in xml_copy.read_text()


def test_act_page_links_to_raw_xml(tmp_path, built_corpus):
    site_dir = tmp_path / "site"
    gen = SiteGenerator(built_corpus, site_dir, templates_dir=Path("templates"))
    gen.generate()
    act_page = site_dir / "akn" / "au" / "act" / "1988" / "119" / "index.html"
    assert 'href="source.xml"' in act_page.read_text()


def test_render_inline_preserves_text_after_ref():
    p = _p('Civil proceedings do not lie under <ref href="#sec-70">section&#160;70</ref>.')
    rendered = _render_inline(p)
    assert "Civil proceedings do not lie under" in rendered
    assert "section" in rendered and "70" in rendered
    assert rendered.strip().endswith(".")


def test_render_inline_preserves_leading_term_def():
    p = _p('<term refersTo="#term-x">Advisory Committee</term> means <def>the Committee.</def>')
    rendered = _render_inline(p)
    assert "Advisory Committee" in rendered
    assert "means" in rendered
    assert "the Committee." in rendered


def test_render_inline_bold_italic_become_html_tags():
    p = _p('<b><i>agency</i></b> does not include an eligible provider.')
    rendered = _render_inline(p)
    assert "<b><i>agency</i></b>" in rendered
    assert "does not include an eligible provider." in rendered


def test_render_inline_escapes_literal_text():
    p = _p("Section 6 &amp; 7 apply.")
    rendered = _render_inline(p)
    # markupsafe.escape turns "&" into "&amp;" — must not leak a raw ampersand.
    assert "&amp;" in rendered


def test_direct_paragraphs_skips_only_truly_empty_p():
    xml = etree.fromstring(f"""
    <part xmlns="{AKN_NS}" eId="part-I">
      <num>I</num>
      <content>
        <p><term refersTo="#term-x">X</term> means <def>Y.</def></p>
        <p></p>
      </content>
    </part>
    """)
    from lexau.site import _direct_paragraphs
    paras = _direct_paragraphs(xml)
    assert len(paras) == 1
    assert "means" in paras[0]


def test_index_sorted_alphabetically(tmp_path):
    corpus = Corpus(tmp_path / "corpus")
    entries = [
        ("Zoo Act 1999", "199", 1999, 1),
        ("Acts Interpretation Act 1901", "1", 1901, 2),
        ("Migration Act 1958", "58", 1958, 3),
    ]
    for name, comp_num, year, number in entries:
        meta = ActMetadata(
            name=name, title_id=f"T{number}", comp_id=f"C{number}",
            comp_num=comp_num, year=year, number=number,
            effective_date=date(2024, 1, 1),
        )
        builder = AknBuilder(meta)
        builder.add(ParsedParagraph(ElementType.SECTION, number="1", heading="H"))
        xml, _ = builder.build()
        corpus.save(meta, xml)

    site_dir = tmp_path / "site"
    gen = SiteGenerator(corpus, site_dir, templates_dir=Path("templates"))
    gen.generate()
    content = (site_dir / "index.html").read_text()

    positions = {name: content.index(name) for name, *_ in entries}
    assert positions["Acts Interpretation Act 1901"] < positions["Migration Act 1958"] < positions["Zoo Act 1999"]
