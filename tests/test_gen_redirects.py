import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "gen_redirects", Path(__file__).parent.parent / "scripts" / "gen_redirects.py"
)
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


def test_redirects_page_source_and_catchall_in_order():
    lines, skipped = gen.build_redirects(
        {"privacy-act-1988": "/akn/au/act/1988/119/"}, {"privacy-act-1988"}
    )
    assert lines == [
        "/akn/au/act/1988/119/ https://lex-au-explorer.netlify.app/reader/privacy-act-1988 301",
        "/akn/au/act/1988/119/source.xml "
        "https://huggingface.co/datasets/cchew/lex-au/resolve/main/xml/privacy-act-1988.xml 301",
        "/ https://lex-au-explorer.netlify.app/ 301!",
        "/* https://lex-au-explorer.netlify.app/ 301",
    ]
    assert skipped == []


def test_slug_with_parentheses_is_percent_encoded():
    lines, _ = gen.build_redirects(
        {"a-(b)-act-2000": "/akn/au/act/2000/1/"}, {"a-(b)-act-2000"}
    )
    assert "/reader/a-%28b%29-act-2000 301" in lines[0]


def test_act_missing_from_explorer_falls_through():
    lines, skipped = gen.build_redirects({"x-act-2001": "/akn/au/act/2001/2/"}, set())
    assert skipped == ["x-act-2001"]
    assert lines == [
        "/ https://lex-au-explorer.netlify.app/ 301!",
        "/* https://lex-au-explorer.netlify.app/ 301",
    ]
