"""Offline corpus rebuild from cached DOCX + index metadata (no network).

Reads a baseline corpus (index.json + docx/, never written) and converts the
selected Acts into a separate output corpus with an explicit local-definitions
setting, so a flags-on vs flags-off diff has identical compilation inputs.
"""
from __future__ import annotations

import json
import random
import re
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lexau.cli import _convert_act, _load_corpus_index  # noqa: E402
from lexau.corpus import Corpus  # noqa: E402
from lexau.models import ActMetadata  # noqa: E402
from lexau.profiles import profile_for  # noqa: E402


def meta_from_entry(entry: dict) -> ActMetadata:
    return ActMetadata(
        name=entry["name"],
        title_id=entry["title_id"],
        comp_id=entry["comp_id"],
        comp_num=str(entry["comp_num"]),
        year=int(entry["year"]),
        number=int(entry["number"]),
        effective_date=date.fromisoformat(str(entry["effective_date"])[:10]),
        aliases=list(entry.get("aliases", [])),
        doc_type=entry.get("doc_type", "act"),
        locality=entry.get("locality"),
    )


def find_volumes(docx_dir: Path, safe_name: str, comp_num: str) -> list[Path]:
    """Cached volumes sorted by volume number; legacy un-versioned names only if no -c file exists."""
    def collect(pattern: str) -> list[Path]:
        rx = re.compile(pattern)
        found = [(int(m.group(1)), p) for p in docx_dir.glob("*.docx") if (m := rx.match(p.name))]
        return [p for _, p in sorted(found)]

    current = collect(rf"^{re.escape(safe_name)}-c{re.escape(str(comp_num))}-vol(\d+)\.docx$")
    return current or collect(rf"^{re.escape(safe_name)}-vol(\d+)\.docx$")


def select_keys(
    acts: dict[str, dict],
    volumes: dict[str, list[Path]],
    only_multivolume: bool,
    sample: int | None,
    seed: int,
    acts_file: Path | None,
) -> list[str]:
    keys = sorted(k for k, e in acts.items() if e.get("doc_type", "act") == "act")
    if acts_file is not None:
        wanted = {ln.strip() for ln in acts_file.read_text().splitlines() if ln.strip()}
        keys = [k for k in keys if k in wanted or acts[k]["name"] in wanted]
    if only_multivolume:
        keys = [k for k in keys if len(volumes.get(k, [])) > 1]
    if sample is not None and sample < len(keys):
        keys = sorted(random.Random(seed).sample(keys, sample))
    return keys


@click.command()
@click.option("--baseline-corpus", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--out", "out_dir", type=click.Path(path_type=Path), required=True)
@click.option("--local-definitions/--no-local-definitions", "local_definitions", default=None)
@click.option("--only-multivolume", is_flag=True)
@click.option("--sample", type=int, default=None)
@click.option("--seed", type=int, default=0, show_default=True)
@click.option("--acts-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
def main(
    baseline_corpus: Path,
    out_dir: Path,
    local_definitions: bool,
    only_multivolume: bool,
    sample: int | None,
    seed: int,
    acts_file: Path | None,
) -> None:
    """Rebuild Acts offline into --out from the baseline's cached DOCX."""
    if local_definitions is None:
        raise click.UsageError("pass --local-definitions or --no-local-definitions explicitly")
    if out_dir.resolve() == baseline_corpus.resolve():
        raise click.UsageError("--out must differ from --baseline-corpus")
    index_path = baseline_corpus / "index.json"
    acts = json.loads(index_path.read_text())["acts"]
    corpus_index = _load_corpus_index(index_path)
    docx_dir = baseline_corpus / "docx"

    volumes = {k: find_volumes(docx_dir, k, str(e["comp_num"])) for k, e in acts.items()}
    keys = select_keys(acts, volumes, only_multivolume, sample, seed, acts_file)

    corpus = Corpus(out_dir)
    reports_dir = out_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    profile = profile_for("act", local_definitions)
    built, missing, errors = 0, [], []
    for key in keys:
        entry, paths = acts[key], volumes[key]
        if not paths:
            missing.append(key)
            click.echo(f"SKIP-MISSING {key}")
            continue
        try:
            meta = meta_from_entry(entry)
            xml, report = _convert_act(meta, paths, out_dir, corpus_index, profile)
            report.volumes_fetched = len(paths)
            corpus.save(meta, xml, source_format=entry.get("source_format"))
            (reports_dir / f"{meta.safe_name}.json").write_text(json.dumps(asdict(report), indent=2))
            built += 1
            click.echo(f"OK {key} vols={len(paths)} terms={report.terms_found}")
        except Exception as exc:  # noqa: BLE001
            errors.append(key)
            click.echo(f"ERROR {key}: {exc}", err=True)
    click.echo(
        f"built={built} skipped-missing-docx={len(missing)} errors={len(errors)} "
        f"selected={len(keys)} local_definitions={local_definitions}"
    )
    if missing:
        click.echo("missing: " + ", ".join(missing))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
