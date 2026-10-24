"""Offline corpus rebuild from cached DOCX + index metadata (no network).

Reads a baseline corpus (index.json + docx/, never written) and converts the
selected Acts into a separate output corpus with an explicit local-definitions
setting, so a flags-on vs flags-off diff has identical compilation inputs.
"""
from __future__ import annotations

import json
import multiprocessing
import os
import random
import re
import shutil
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
from datetime import date
from pathlib import Path
from typing import Any

import click
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from lexau.cli import _convert_act, _load_corpus_index  # noqa: E402
from lexau.corpus import STRUCTURE_VERSION, Corpus  # noqa: E402
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


def total_docx_size(paths: list[Path]) -> int:
    return sum(p.stat().st_size for p in paths)


def order_largest_first(keys: list[str], sizes: dict[str, int]) -> list[str]:
    """Single work queue order: biggest Act (sum of all volumes) first, name as tiebreak."""
    return sorted(keys, key=lambda k: (-sizes.get(k, 0), k))


def is_well_formed(path: Path) -> bool:
    try:
        etree.parse(str(path))
        return True
    except (etree.XMLSyntaxError, OSError):
        return False


def _atomic_write(path: Path, data: bytes) -> None:
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


_WORKER_STATE: dict[str, Any] = {}


def _init_worker(worker_tmp_root: str) -> None:
    """Give each worker process its own TMPDIR so concurrent soffice runs never share a scratch path.

    figures.materialise_figures already makes a fresh mkdtemp (with its own -env:UserInstallation
    profile) per Act; pointing TMPDIR at a per-process directory makes that isolation explicit.
    """
    d = Path(worker_tmp_root) / f"worker-{os.getpid()}"
    d.mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(d)
    tempfile.tempdir = None


def build_one(task: dict[str, Any]) -> dict[str, Any]:
    """Convert one Act and write its XML and report atomically. Never raises."""
    key = task["key"]
    started = time.monotonic()
    result: dict[str, Any] = {"key": key, "pid": os.getpid()}
    try:
        out_dir = Path(task["out_dir"])
        cache = _WORKER_STATE.setdefault("corpus_index", {})
        if task["index_path"] not in cache:
            cache.clear()
            cache[task["index_path"]] = _load_corpus_index(Path(task["index_path"]))
        corpus_index = cache[task["index_path"]]
        meta = meta_from_entry(task["entry"])
        paths = [Path(p) for p in task["paths"]]
        profile = profile_for("act", task["local_definitions"])
        xml, report = _convert_act(meta, paths, out_dir, corpus_index, profile)
        report.volumes_fetched = len(paths)
        data = etree.tostring(xml, pretty_print=True, xml_declaration=True, encoding="UTF-8")
        _atomic_write(out_dir / "reports" / f"{meta.safe_name}.json", json.dumps(asdict(report), indent=2).encode())
        _atomic_write(out_dir / "xml" / f"{meta.safe_name}.xml", data)  # last: its presence marks the Act done
        result.update(status="built", vols=len(paths), terms=report.terms_found)
    except Exception as exc:  # noqa: BLE001
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    result["seconds"] = round(time.monotonic() - started, 2)
    return result


def run_pool(
    tasks: list[dict[str, Any]],
    workers: int,
    out_dir: Path,
    build_fn: Any = None,
    mp_context: str = "spawn",
    summary_every_s: float = 60.0,
) -> list[dict[str, Any]]:
    """Run tasks (already in queue order) over `workers` processes; one result per task."""
    build_fn = build_fn or build_one
    progress = out_dir / "rebuild-progress.jsonl"
    worker_tmp = Path(tempfile.mkdtemp(prefix="lexau-rebuild-"))
    results: list[dict[str, Any]] = []
    labels: dict[int, str] = {}
    t0 = last_summary = time.monotonic()
    try:
        with ProcessPoolExecutor(
            max_workers=workers,
            mp_context=multiprocessing.get_context(mp_context),
            initializer=_init_worker,
            initargs=(str(worker_tmp),),
        ) as ex, progress.open("a") as pf:
            futures = {ex.submit(build_fn, t): t for t in tasks}
            for fut in as_completed(futures):
                task = futures[fut]
                try:
                    res = fut.result()
                except Exception as exc:  # noqa: BLE001  (e.g. BrokenProcessPool)
                    res = {"key": task["key"], "pid": 0, "status": "failed",
                           "error": f"{type(exc).__name__}: {exc}", "seconds": 0.0}
                res["worker"] = labels.setdefault(res.get("pid", 0), f"w{len(labels) + 1}")
                results.append(res)
                pf.write(json.dumps(res) + "\n")
                pf.flush()
                tag = "OK" if res["status"] == "built" else "ERROR"
                extra = "" if res["status"] == "built" else f" {res['error']}"
                click.echo(f"{tag} {res['key']} {res['seconds']}s {res['worker']}{extra}")
                now = time.monotonic()
                if now - last_summary >= summary_every_s:
                    last_summary = now
                    click.echo(
                        f"-- {len(results)}/{len(tasks)} done, "
                        f"{sum(r['status'] != 'built' for r in results)} failed, {int(now - t0)}s elapsed"
                    )
    finally:
        shutil.rmtree(worker_tmp, ignore_errors=True)
    return results


def write_index(baseline_corpus: Path, out_dir: Path) -> None:
    """Same index as merge_offline for a single output: baseline entries unchanged, structure_version stamped."""
    index = json.loads((baseline_corpus / "index.json").read_text())
    index["structure_version"] = STRUCTURE_VERSION
    _atomic_write(out_dir / "index.json", json.dumps(index, ensure_ascii=False, indent=2).encode())


def _run_parallel(
    baseline_corpus: Path,
    out_dir: Path,
    acts: dict[str, dict],
    volumes: dict[str, list[Path]],
    keys: list[str],
    local_definitions: bool,
    workers: int,
    resume: bool,
) -> int:
    for sub in ("xml", "reports", "images"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)
    missing = [k for k in keys if not volumes[k]]
    todo = [k for k in keys if volumes[k]]
    for k in missing:
        click.echo(f"SKIP-MISSING {k}")
    skipped: list[str] = []
    if resume:
        skipped = [k for k in todo if (out_dir / "xml" / f"{k}.xml").exists() and is_well_formed(out_dir / "xml" / f"{k}.xml")]
        todo = [k for k in todo if k not in set(skipped)]
    order = order_largest_first(todo, {k: total_docx_size(volumes[k]) for k in todo})
    index_path = str(baseline_corpus / "index.json")
    tasks = [
        {"key": k, "entry": acts[k], "paths": [str(p) for p in volumes[k]], "out_dir": str(out_dir),
         "index_path": index_path, "local_definitions": local_definitions}
        for k in order
    ]
    results = run_pool(tasks, workers, out_dir) if tasks else []
    failed = sorted(r["key"] for r in results if r["status"] != "built")
    write_index(baseline_corpus, out_dir)
    click.echo(
        f"built={len(results) - len(failed)} skipped-resume={len(skipped)} skipped-missing-docx={len(missing)} "
        f"errors={len(failed)} selected={len(keys)} local_definitions={local_definitions} workers={workers}"
    )
    if missing:
        click.echo("missing: " + ", ".join(missing))
    if failed:
        click.echo("failed: " + ", ".join(failed), err=True)
    return 1 if failed else 0


@click.command()
@click.option("--baseline-corpus", type=click.Path(exists=True, file_okay=False, path_type=Path), required=True)
@click.option("--out", "out_dir", type=click.Path(path_type=Path), required=True)
@click.option("--local-definitions/--no-local-definitions", "local_definitions", default=None)
@click.option("--only-multivolume", is_flag=True)
@click.option("--sample", type=int, default=None)
@click.option("--seed", type=int, default=0, show_default=True)
@click.option("--acts-file", type=click.Path(exists=True, dir_okay=False, path_type=Path), default=None)
@click.option("--workers", type=click.IntRange(min=1), default=1, show_default=True,
              help="Worker processes over one largest-first queue. 1 keeps the original sequential path.")
@click.option("--resume", is_flag=True,
              help="Skip Acts whose output XML already exists and is well-formed (truncated files are rebuilt).")
def main(
    baseline_corpus: Path,
    out_dir: Path,
    local_definitions: bool,
    only_multivolume: bool,
    sample: int | None,
    seed: int,
    acts_file: Path | None,
    workers: int,
    resume: bool,
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

    if workers > 1 or resume:
        sys.exit(_run_parallel(baseline_corpus, out_dir, acts, volumes, keys, local_definitions, workers, resume))

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
