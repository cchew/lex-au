"""Generate the redirect stub that replaces lex-au.netlify.app.

Every old per-Act page (/akn/au/act/{year}/{number}/) redirects to the same Act
in lex-au-explorer; its source.xml redirects to the Hugging Face copy. Anything
else (unknown Acts, the index) lands on the explorer home page.

    python scripts/gen_redirects.py --corpus-dir corpus \
        --explorer-index ../../lex-au-explorer/repo/web/public/data/index.json \
        --out-dir redirects
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import quote

from lexau.corpus import Corpus
from lexau.site import _assign_site_paths

EXPLORER = "https://lex-au-explorer.netlify.app"
HF_XML = "https://huggingface.co/datasets/cchew/lex-au/resolve/main/xml"


def build_redirects(
    site_paths: dict[str, str], explorer_slugs: set[str]
) -> tuple[list[str], list[str]]:
    """Return (_redirects lines, safe_names skipped for lack of an explorer page)."""
    lines: list[str] = []
    skipped: list[str] = []
    for slug, path in sorted(site_paths.items(), key=lambda kv: kv[1]):
        if slug not in explorer_slugs:
            skipped.append(slug)
            continue
        enc = quote(slug, safe="-.")
        lines.append(f"{path} {EXPLORER}/reader/{enc} 301")
        lines.append(f"{path}source.xml {HF_XML}/{enc}.xml 301")
    # Specific rules above win: Netlify applies the first match.
    # "!" forces the root redirect past the stub index.html, which Netlify
    # would otherwise serve in preference to a rule.
    lines.append(f"/ {EXPLORER}/ 301!")
    lines.append(f"/* {EXPLORER}/ 301")
    return lines, skipped


STUB_HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>lex-au has moved</title>
<meta http-equiv="refresh" content="0; url={EXPLORER}/">
</head>
<body>
<p>The lex-au corpus browser is now <a href="{EXPLORER}/">lex-au-explorer</a>.</p>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus-dir", type=Path, default=Path("corpus"))
    ap.add_argument("--explorer-index", type=Path, required=True)
    ap.add_argument("--out-dir", type=Path, default=Path("redirects"))
    args = ap.parse_args()

    meta = sorted(Corpus(args.corpus_dir).all_metadata(), key=lambda m: m.name)
    site_paths = _assign_site_paths(meta)
    explorer_slugs = {e["slug"] for e in json.loads(args.explorer_index.read_text())}

    lines, skipped = build_redirects(site_paths, explorer_slugs)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "_redirects").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (args.out_dir / "index.html").write_text(STUB_HTML, encoding="utf-8")
    print(f"{len(site_paths) - len(skipped)} Acts redirected, {len(skipped)} fall through to home")
    for s in skipped:
        print(f"  no explorer page: {s}")


if __name__ == "__main__":
    main()
