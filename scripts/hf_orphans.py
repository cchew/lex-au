"""List (and optionally delete) files on the HF dataset that the corpus no longer uses.

`lexau export-hf` only adds and updates files; its deletion step is skipped unless the local
corpus carries a fresh restore stamp, which an offline rebuild never has. Files left behind
(figures dropped when a Table of Provisions was removed, superseded report versions, Acts
removed from the index) therefore accumulate. This tool needs no stamp: it works out what is
unused from the corpus itself.

  xml/<slug>.xml            orphan if <slug> is not in index.json
  images/<name>             orphan if no <img src> in any xml/*.xml names it
  reports/<slug>-vX.json    orphan if <slug> is not in the index, or X is not the current version
                            (analysis files, logs and reports/fidelity/ are never touched)

Dry run by default. --delete removes the orphans in a single commit.

    python scripts/hf_orphans.py --corpus-dir <restored corpus with index.json and xml/>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from lxml import etree

AKN = "{http://docs.oasis-open.org/legaldocml/ns/akn/3.0}"
CURRENT_REPORT_VERSION = "v0.5.0"
_REPORT_RE = re.compile(r"^reports/(?P<slug>.+)-(?P<ver>v\d+\.\d+\.\d+)\.json$")


def find_orphans(
    remote_files: list[str],
    index_slugs: set[str],
    referenced_images: set[str],
    current_report_version: str = CURRENT_REPORT_VERSION,
) -> dict[str, list[str]]:
    if not index_slugs or not referenced_images:
        raise ValueError(
            "index or image references are empty: the local corpus is not a restore of the dataset, "
            "so nothing can be called an orphan"
        )
    orphans: dict[str, list[str]] = {"xml": [], "images": [], "reports": []}
    for path in sorted(remote_files):
        if path.startswith("xml/") and path.endswith(".xml"):
            if path[len("xml/"):-len(".xml")] not in index_slugs:
                orphans["xml"].append(path)
        elif path.startswith("images/") and path.count("/") == 1:
            if path[len("images/"):] not in referenced_images:
                orphans["images"].append(path)
        else:
            m = _REPORT_RE.match(path)
            if m and (m["slug"] not in index_slugs or m["ver"] != current_report_version):
                orphans["reports"].append(path)
    return orphans


def referenced_images(xml_dir: Path) -> set[str]:
    names: set[str] = set()
    for xml_path in xml_dir.glob("*.xml"):
        for img in etree.parse(str(xml_path)).getroot().iter(f"{AKN}img"):
            src = img.get("src") or ""
            if src:
                names.add(src.rsplit("/", 1)[-1])
    return names


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus-dir", type=Path, required=True)
    ap.add_argument("--repo", default="cchew/lex-au")
    ap.add_argument("--delete", action="store_true", help="delete the orphans (default: list only)")
    args = ap.parse_args(argv)

    from huggingface_hub import HfApi

    index = json.loads((args.corpus_dir / "index.json").read_text())["acts"]
    remote = HfApi().list_repo_files(args.repo, repo_type="dataset")
    orphans = find_orphans(remote, set(index), referenced_images(args.corpus_dir / "xml"))
    total = sum(len(v) for v in orphans.values())
    for kind, paths in orphans.items():
        print(f"{kind}: {len(paths)} orphan(s)")
        for p in paths[:5]:
            print(f"  {p}")
    if not total:
        print("Nothing to delete.")
        return 0
    if not args.delete:
        print(f"\nDry run: {total} file(s) would be deleted. Re-run with --delete to remove them.")
        return 0
    from huggingface_hub import CommitOperationDelete

    ops = [CommitOperationDelete(path_in_repo=p) for paths in orphans.values() for p in paths]
    info = HfApi().create_commit(
        args.repo, repo_type="dataset", operations=ops,
        commit_message=f"remove {total} files no longer referenced by the corpus",
    )
    print(f"Deleted {total} file(s): {info.commit_url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
