import pytest
from pathlib import Path
from lxml import etree
from datetime import date
from lexau.corpus import Corpus
from lexau.models import ActMetadata
from lexau.site import SiteGenerator, _render_inline, AKN_NS
from lexau.builder import AknBuilder
from lexau.parser import ParsedParagraph, ElementType


def test_assign_site_paths_no_collision_keeps_bare_path():
    from lexau.site import _assign_site_paths
    meta = ActMetadata(
        name="Privacy Act 1988", title_id="C2004A03712", comp_id="C1",
        comp_num="1", year=1988, number=119, effective_date=date(2024, 1, 1),
    )
    paths = _assign_site_paths([meta])
    assert paths[meta.safe_name] == "/akn/au/act/1988/119/"


def test_assign_site_paths_collision_uses_intrinsic_suffix():
    from lexau.site import _assign_site_paths
    a = ActMetadata(
        name="Training Guarantee (Administration) Amendment Act 1994", title_id="T2",
        comp_id="C1", comp_num="1", year=1994, number=57, effective_date=date(2024, 1, 1),
    )
    b = ActMetadata(
        name="Superannuation Industry (Supervision) Regulations 1994", title_id="T1",
        comp_id="C2", comp_num="1", year=1994, number=57, effective_date=date(2024, 1, 1),
    )
    # Suffix = lowercased title_id + blake2b-4 digest of safe_name: intrinsic to
    # each Act, so neither the group's composition nor its ordering can move it.
    paths = _assign_site_paths([a, b])
    assert paths[a.safe_name] == "/akn/au/act/1994/57-t2-f086ea4d/"
    assert paths[b.safe_name] == "/akn/au/act/1994/57-t1-ba01e2a0/"
    # Reversing the input must produce an identical mapping.
    assert _assign_site_paths([b, a]) == paths


def test_assign_site_paths_three_way_collision():
    from lexau.site import _assign_site_paths
    members = [
        ActMetadata(name=f"Act {t}", title_id=t, comp_id=f"C{t}", comp_num="1",
                    year=2000, number=1, effective_date=date(2024, 1, 1))
        for t in ("T3", "T1", "T2")
    ]
    paths = _assign_site_paths(members)
    assert paths["act-t1"] == "/akn/au/act/2000/1-t1-a2134542/"
    assert paths["act-t2"] == "/akn/au/act/2000/1-t2-dbad39bc/"
    assert paths["act-t3"] == "/akn/au/act/2000/1-t3-f0aaa1ef/"


def test_assign_site_paths_identical_title_id_still_disambiguates():
    """Two corpus entries can share a title_id outright.

    Real case, live corpus: Human Services (Medicare) Act 1973 and Health
    Insurance Commission Act 1973 both carry title_id C2004A00100 (and the
    same comp_id, comp_num and effective_date) -- the same composition
    ingested twice under an old and a new title. title_id alone therefore
    cannot separate them, and a sort on it would leave the outcome to input
    order.
    """
    from lexau.site import _assign_site_paths
    a = ActMetadata(
        name="Human Services (Medicare) Act 1973", title_id="C2004A00100",
        comp_id="C2025C00609", comp_num="51", year=1974, number=41,
        effective_date=date(2025, 11, 1),
    )
    b = ActMetadata(
        name="Health Insurance Commission Act 1973", title_id="C2004A00100",
        comp_id="C2025C00609", comp_num="51", year=1974, number=41,
        effective_date=date(2025, 11, 1),
    )
    paths = _assign_site_paths([a, b])
    assert paths[a.safe_name] == "/akn/au/act/1974/41-c2004a00100-bd8f6b96/"
    assert paths[b.safe_name] == "/akn/au/act/1974/41-c2004a00100-7a8d488c/"
    assert paths[a.safe_name] != paths[b.safe_name]
    # Order-independent: reversed input yields the identical mapping.
    assert _assign_site_paths(list(reversed([a, b]))) == paths


def test_assign_site_paths_existing_member_survives_group_growth():
    """A new Act joining a collision group must not move an existing member's URL.

    An ordinal suffix fails here: a third member sorting ahead of an
    existing one renumbers it, silently repointing an already-published URL
    at different Act content.
    """
    from lexau.site import _assign_site_paths
    a = ActMetadata(name="Act B", title_id="T5", comp_id="C1", comp_num="1",
                    year=2000, number=1, effective_date=date(2024, 1, 1))
    b = ActMetadata(name="Act C", title_id="T9", comp_id="C2", comp_num="1",
                    year=2000, number=1, effective_date=date(2024, 1, 1))
    before = _assign_site_paths([a, b])

    # New arrival sorts ahead of both existing members on every field.
    newcomer = ActMetadata(name="Act A", title_id="T0", comp_id="C0", comp_num="1",
                           year=2000, number=1, effective_date=date(2024, 1, 1))
    after = _assign_site_paths([newcomer, a, b])

    assert after[a.safe_name] == before[a.safe_name]
    assert after[b.safe_name] == before[b.safe_name]
    assert after[newcomer.safe_name] not in (before[a.safe_name], before[b.safe_name])


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


def test_collision_disambiguates_paths_and_generates_distinct_pages(tmp_path):
    corpus = Corpus(tmp_path / "corpus")
    entries = [
        # (name, title_id, year, number)
        ("Training Guarantee (Administration) Amendment Act 1994", "T2", 1994, 57),
        ("Superannuation Industry (Supervision) Regulations 1994", "T1", 1994, 57),
        ("Privacy Act 1988", "T3", 1988, 119),
    ]
    for name, title_id, year, number in entries:
        meta = ActMetadata(
            name=name, title_id=title_id, comp_id=f"C{title_id}",
            comp_num="1", year=year, number=number,
            effective_date=date(2024, 1, 1),
        )
        builder = AknBuilder(meta)
        builder.add(ParsedParagraph(ElementType.SECTION, number="1", heading="H"))
        xml, _ = builder.build()
        corpus.save(meta, xml)

    site_dir = tmp_path / "site"
    gen = SiteGenerator(corpus, site_dir, templates_dir=Path("templates"))
    gen.generate()

    # Colliding pair: each member gets its own title_id + safe_name-digest suffix.
    act_dir = site_dir / "akn" / "au" / "act" / "1994"
    assert (act_dir / "57-t1-ba01e2a0" / "index.html").exists()
    assert (act_dir / "57-t2-f086ea4d" / "index.html").exists()
    assert not (act_dir / "57").exists()

    # Non-colliding Act keeps its bare path, unchanged.
    assert (site_dir / "akn" / "au" / "act" / "1988" / "119" / "index.html").exists()

    index_content = (site_dir / "index.html").read_text()
    assert "/akn/au/act/1994/57-t1-ba01e2a0/" in index_content
    assert "/akn/au/act/1994/57-t2-f086ea4d/" in index_content

