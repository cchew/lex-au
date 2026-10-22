"""Merge parallel rebuild_offline.py chunk outputs into one corpus directory.

Starts from a copy of the baseline corpus (xml/, index.json) so Acts that were not rebuilt keep their
baseline XML, overlays the rebuilt XML from every chunk, and copies reports/ and images/. Index entries
stay exactly as in the baseline (metadata is unchanged by an offline rebuild); only the top-level
``structure_version`` is taken from the chunks, and every chunk must agree on it.
Rejects chunk XML that is not well-formed (a killed run can leave a truncated file).
Never writes into the baseline or chunk directories.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import click
from lxml import etree


def merge(baseline: Path, chunks: list[Path], out: Path) -> dict[str, int]:
    if out.exists() and any(out.iterdir()):
        raise click.UsageError(f"{out} is not empty")
    if any(out.resolve() == p.resolve() for p in [baseline, *chunks]):
        raise click.UsageError("--out must be a new directory")

    base_index = json.loads((baseline / "index.json").read_text())
    versions = {json.loads((c / "index.json").read_text()).get("structure_version") for c in chunks}
    if len(versions) != 1 or None in versions:
        raise click.UsageError(f"chunks disagree on or lack structure_version: {versions}")

    (out / "xml").mkdir(parents=True)
    shutil.copytree(baseline / "xml", out / "xml", dirs_exist_ok=True)

    rebuilt: set[str] = set()
    for chunk in chunks:
        for xml in (chunk / "xml").glob("*.xml"):
            if xml.stem not in base_index["acts"]:
                raise click.UsageError(f"{xml.name} from {chunk} is not in the baseline index")
            if xml.stem in rebuilt:
                raise click.UsageError(f"{xml.stem} was rebuilt by two chunks")
            try:
                etree.parse(str(xml))
            except etree.XMLSyntaxError as exc:
                raise click.UsageError(f"{xml} is not well-formed XML (truncated by a killed run?): {exc}")
            shutil.copy2(xml, out / "xml" / xml.name)
            rebuilt.add(xml.stem)
        for sub in ("reports", "images"):
            src = chunk / sub
            if src.is_dir():
                shutil.copytree(src, out / sub, dirs_exist_ok=True)

    index = dict(base_index)
    index["structure_version"] = versions.pop()
    (out / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2))
    return {"baseline_acts": len(base_index["acts"]), "rebuilt": len(rebuilt), "kept_baseline": len(base_index["acts"]) - len(rebuilt)}


@click.command()
@click.option("--baseline-corpus", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--chunk", "chunks", type=click.Path(exists=True, file_okay=False, path_type=Path), multiple=True, required=True)
@click.option("--out", type=click.Path(path_type=Path), required=True)
def main(baseline_corpus: Path, chunks: tuple[Path, ...], out: Path) -> None:
    stats = merge(baseline_corpus, list(chunks), out)
    click.echo(" ".join(f"{k}={v}" for k, v in stats.items()))


if __name__ == "__main__":
    sys.exit(main())
