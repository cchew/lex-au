import pytest
from pathlib import Path
from lxml import etree
from datetime import date
from lexau.corpus import Corpus
from lexau.models import ActMetadata
from lexau.site import SiteGenerator
from lexau.builder import AknBuilder
from lexau.parser import ParsedParagraph, ElementType


@pytest.fixture
def built_corpus(tmp_path, privacy_meta):
    corpus = Corpus(tmp_path / "corpus")
    builder = AknBuilder(privacy_meta)
    builder.add(ParsedParagraph(ElementType.PART, number="I", heading="Preliminary"))
    builder.add(ParsedParagraph(ElementType.SECTION, number="1", heading="Short title"))
    builder.add(ParsedParagraph(ElementType.BODY, text="This Act is the Privacy Act 1988."))
    builder.add(ParsedParagraph(ElementType.SECTION, number="2", heading="Commencement"))
    corpus.save(privacy_meta, builder.build())
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
    assert 'id="sec-1"' in content
    assert "Short title" in content
