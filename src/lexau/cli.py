from __future__ import annotations

import json
import sys
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import click
from lxml import etree
from docx import Document
from huggingface_hub import HfApi
from huggingface_hub.utils import filter_repo_objects

from lexau import hfsync
from lexau.corpus import Corpus
from lexau.crawler import Crawler
from lexau.builder import AknBuilder
from lexau.docx_reader import iter_paragraphs
from lexau.models import ActMetadata, ParseReport
from lexau.profiles import ParserProfile, profile_for

# Files list_repo_files() returns that export_hf never derives from
# corpus_dir -- the dataset card (uploaded separately, from --readme) and
# HF-repo-internal metadata it manages itself -- so the reconcile step must
# never propose deleting them, however "orphaned" they'd otherwise look.
_HF_MANAGED_FILES = {"README.md", ".gitattributes"}

# Written into the corpus dir by scripts/restore_corpus_from_hf.py right
# after a snapshot_download. Its presence + freshness is what tells
# export-hf the local corpus is a faithful mirror of the remote and is
# therefore safe to reconcile deletions against. Kept out of the upload
# (it is local sync state, not corpus content).
_HF_SYNC_STAMP = ".hf-sync-stamp.json"

# How stale the sync stamp may be before export-hf stops trusting the
# local corpus to drive remote deletions. A scheduled run restores then
# publishes within the same job (90-min timeout), so any real gap here
# means someone is exporting a corpus they hydrated hours or days ago,
# which may be missing Acts the pipeline has since added straight to HF.
_HF_SYNC_STAMP_MAX_AGE = timedelta(hours=24)


def _find_endnote_volume(docx_paths: list[Path]) -> Path | None:
    """Return the volume containing 'Endnotes' (ENotesHeading 1), scanning from last."""
    for path in reversed(docx_paths):
        doc = Document(str(path))
        for para in doc.paragraphs:
            if para.style and para.style.name == "ENotesHeading 1" and para.text.strip() == "Endnotes":
                return path
    return None


@click.group()
def cli() -> None:
    """lex-au: Commonwealth Acts as AKN 3.0 XML."""


def _load_corpus_index(index_path: Path) -> dict:
    """Build the name -> {frbr_uri} lookup reflinks.inject_refs resolves
    citations against, including alias names so a citation to a superseded
    Act name (see Corpus.save()'s title_id-merge) still resolves.
    """
    if not index_path.exists():
        return {}
    raw = json.loads(index_path.read_text())
    corpus_index: dict = {}
    for entry in raw.get("acts", {}).values():
        value = {"frbr_uri": entry.get("frbr_uri", "")}
        corpus_index[entry["name"]] = value
        for alias in entry.get("aliases", []):
            corpus_index.setdefault(alias, value)
    return corpus_index


def _convert_act(
    meta: ActMetadata,
    docx_paths: list[Path],
    corpus_dir: Path,
    corpus_index: dict,
    profile: ParserProfile | None,
) -> tuple[etree._Element, ParseReport]:
    """Convert an Act's cached DOCX volumes to AKN XML (no network, no writes beyond images)."""
    builder = AknBuilder(meta, images_out=corpus_dir / "images", profile=profile)
    # Sole producer of volume_index. _split_stream's groupby() requires
    # paragraphs to be volume-contiguous; this loop guarantees it by
    # adding all of volume N before volume N+1's first paragraph.
    for vol_idx, docx_path in enumerate(docx_paths):
        doc = Document(docx_path)
        for p in iter_paragraphs(doc):
            builder.add(replace(p, volume_index=vol_idx))

    endnote_vol = _find_endnote_volume(docx_paths)
    return builder.build_with_report(corpus_index, last_volume_path=endnote_vol)


def _build_acts(
    act_names: list[str],
    corpus_dir: Path,
    force: bool,
    doc_type: str = "act",
    local_definitions: bool = True,
) -> None:
    """Build Acts: download DOCX and convert to AKN XML."""
    corpus = Corpus(corpus_dir)
    crawler = Crawler()
    docx_dir = corpus_dir / "docx"
    reports_dir = corpus_dir / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    index_path = corpus_dir / "index.json"
    corpus_index = _load_corpus_index(index_path)

    report_rows: list = []

    for act_name in act_names:
        try:
            click.echo(f"[fetch ] {act_name}")
            meta = crawler.fetch_metadata(act_name, doc_type=doc_type)
            if meta is None:
                click.echo(f"  SKIP -- not found in legislation.gov.au", err=True)
                continue

            if not force and corpus.is_current(meta):
                corpus.touch_last_checked(meta)
                click.echo(f"  SKIP -- compilation #{meta.comp_num} already current")
                continue

            docx_paths = crawler.fetch_docx_volumes(meta, docx_dir)
            if not docx_paths:
                click.echo(f"  SKIP -- DOCX download failed", err=True)
                continue
            source_format = "doc-converted" if any(docx_dir.glob(f"{meta.safe_name}-c{meta.comp_num}-vol*.doc")) else None

            click.echo(f"[convert] {act_name} ({len(docx_paths)} volume(s))")
            xml, report = _convert_act(
                meta, docx_paths, corpus_dir, corpus_index, profile_for(doc_type, local_definitions),
            )
            report.volumes_fetched = len(docx_paths)

            saved = corpus.save(meta, xml, source_format=source_format)
            click.echo(f"  saved -> {saved.relative_to(corpus_dir)}")

            report_path = reports_dir / f"{meta.safe_name}-v0.5.0.json"
            report_path.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2))
            report_rows.append(report)

        except Exception as exc:  # noqa: BLE001
            click.echo(f"  ERROR -- {act_name}: {exc}", err=True)
            continue

    if report_rows:
        click.echo("\n--- Parse Report Summary ---")
        click.echo(
            f"{'Act':<40} {'Vols':>4} {'Subsecs':>7} {'Paras':>6} "
            f"{'Sched':>5} {'Claus':>5} {'Notes':>5} {'Pens':>4} {'Tabs':>4} "
            f"{'Refs':>5} {'Unres':>5} {'Fallbk':>6} "
            f"{'Terms':>5} {'DupT':>4} {'Qtys':>4} {'Roles':>5} {'NtRef':>5} {'LDefC':>5}"
        )
        click.echo("-" * 130)
        for r in report_rows:
            click.echo(
                f"{r.act_name:<40} {r.volumes_fetched:>4} {r.subsections_parsed:>7} "
                f"{r.paragraphs_parsed:>6} {r.schedules_found:>5} {r.schedule_clauses_found:>5} "
                f"{r.notes_found:>5} {r.penalties_found:>4} {r.tables_found:>4} "
                f"{r.refs_resolved:>5} {r.refs_unresolved:>5} {r.style_fallbacks:>6} "
                f"{r.terms_found:>5} {r.duplicate_terms:>4} {r.quantities_found:>4} "
                f"{r.roles_found:>5} {r.note_refs_injected:>5} {r.list_defs_completed:>5}"
            )

    click.echo("\nDone.")


@cli.command()
@click.option("--acts", multiple=True, help="Act name(s) to build (repeatable)")
@click.option(
    "--list-file",
    type=click.Path(exists=True, path_type=Path),
    help="File with one Act name per line",
)
@click.option("--all", "build_all", is_flag=True, help="Build all Acts in acts.txt")
@click.option(
    "--corpus-dir",
    type=click.Path(path_type=Path),
    default=Path("corpus"),
    show_default=True,
)
@click.option("--force", is_flag=True, help="Re-convert even if compilation is current")
@click.option(
    "--type", "doc_type",
    default="act",
    type=click.Choice(["act", "regulation", "instrument"]),
    show_default=True,
    help="Document type (act, regulation, or instrument)",
)
@click.option(
    "--local-definitions/--no-local-definitions",
    default=True,
    show_default=True,
    help="Tag locally scoped and 'In this Act' definitions (Acts only)",
)
def build(
    acts: tuple[str, ...],
    list_file: Path | None,
    build_all: bool,
    corpus_dir: Path,
    force: bool,
    doc_type: str,
    local_definitions: bool,
) -> None:
    """Download DOCX and convert to AKN XML."""
    act_names = list(acts)

    if list_file:
        act_names += [ln.strip() for ln in list_file.read_text().splitlines() if ln.strip()]

    if build_all or (not act_names and not list_file):
        default_list = Path("acts.txt")
        if not default_list.exists():
            click.echo("No acts specified and acts.txt not found.", err=True)
            sys.exit(1)
        act_names += [ln.strip() for ln in default_list.read_text().splitlines() if ln.strip()]

    _build_acts(act_names, corpus_dir, force, doc_type=doc_type, local_definitions=local_definitions)


@cli.command()
@click.option("--corpus-dir", type=click.Path(path_type=Path), default=Path("corpus"), show_default=True)
@click.option("--site-dir", type=click.Path(path_type=Path), default=Path("site"), show_default=True)
@click.option("--templates-dir", type=click.Path(path_type=Path), default=Path("templates"), show_default=True)
def site(corpus_dir: Path, site_dir: Path, templates_dir: Path) -> None:
    """Generate static HTML site from the corpus."""
    from lexau.site import SiteGenerator
    corpus = Corpus(corpus_dir)
    gen = SiteGenerator(corpus, site_dir, templates_dir)
    gen.generate()
    click.echo(f"Site generated -> {site_dir}/")


def _stale_sync_reason(corpus_dir: Path, repo: str) -> str | None:
    """Return why the local corpus can't be trusted to drive remote
    deletions, or None if it can.

    The reconcile step only removes remote files "missing locally". If the
    local corpus was hydrated from a different repo, or long enough ago
    that the pipeline has since added Acts straight to HF, those Acts look
    "missing locally" and get deleted -- exactly the 2026-09-04 incident
    where a stale local `export-hf` wiped 6 freshly-ingested Acts off the
    dataset. A valid, fresh sync stamp (written by
    scripts/restore_corpus_from_hf.py) is the evidence that neither is the
    case.
    """
    stamp_path = corpus_dir / _HF_SYNC_STAMP
    if not stamp_path.exists():
        return f"{stamp_path} not found (corpus was never restored from Hugging Face)"
    try:
        stamp = json.loads(stamp_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return f"{stamp_path} is unreadable ({exc})"
    if stamp.get("repo") != repo:
        return f"{stamp_path} was written for repo {stamp.get('repo')!r}, not {repo!r}"
    raw = stamp.get("restored_at")
    try:
        restored_at = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return f"{stamp_path} has an unparseable restored_at ({raw!r})"
    if restored_at.tzinfo is None:
        restored_at = restored_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - restored_at
    if age > _HF_SYNC_STAMP_MAX_AGE:
        limit_h = int(_HF_SYNC_STAMP_MAX_AGE.total_seconds() // 3600)
        return f"{stamp_path} is {age.total_seconds() / 3600:.0f}h old (limit {limit_h}h)"
    return None


def _reconcile_deleted_files(
    api: HfApi, repo: str, corpus_dir: Path, ignore_patterns: list[str]
) -> list[str]:
    """Delete remote dataset files that no longer exist locally.

    upload_large_folder only adds/updates files -- it has no delete
    capability (no delete_patterns param, unlike upload_folder), so a file
    removed from corpus_dir (e.g. a title_id-merge collapsing a duplicate
    Act) stays on the HF repo forever unless something explicitly removes
    it. This diffs the remote file list against corpus_dir and issues one
    batched delete for whatever's left over on the remote side only.

    ignore_patterns is applied on both sides of the diff: once to decide
    which local files are actually managed (mirrors what upload_large_folder
    would have uploaded), and again as a safety net on the orphan
    candidates themselves, so a path under docx/** or doc_spike/** -- never
    uploaded, hence not this function's responsibility to delete either --
    can never be proposed for deletion even if it's genuinely absent
    locally.

    Returns the list of remote paths deleted (empty if none).
    """
    remote_files = set(api.list_repo_files(repo_id=repo, repo_type="dataset"))

    local_files = {
        p.relative_to(corpus_dir).as_posix()
        for p in corpus_dir.rglob("*")
        if p.is_file()
    }
    local_managed = set(filter_repo_objects(local_files, ignore_patterns=ignore_patterns))

    candidates = remote_files - local_managed
    candidates = set(filter_repo_objects(candidates, ignore_patterns=ignore_patterns))
    orphans = sorted(f for f in candidates if f not in _HF_MANAGED_FILES)

    if orphans:
        api.delete_files(repo_id=repo, repo_type="dataset", delete_patterns=orphans)

    return orphans


def _unsynced_reason(head: str, corpus_dir: Path, repo: str) -> str | None:
    """Return why corpus_dir is not a verified restore of repo's current
    head, or None if it is. Checked before any upload: a stamp pinned to an
    older sha means someone published since this corpus was restored, and
    uploading would revert their files."""
    stamp_path = corpus_dir / _HF_SYNC_STAMP
    if not stamp_path.exists():
        return f"{stamp_path} not found (corpus was never restored from Hugging Face)"
    try:
        stamp = json.loads(stamp_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        return f"{stamp_path} is unreadable ({exc})"
    if stamp.get("repo") != repo:
        return f"{stamp_path} was written for repo {stamp.get('repo')!r}, not {repo!r}"
    if stamp.get("allow_patterns"):
        return f"{stamp_path} records a partial restore ({stamp['allow_patterns']})"
    stamp_sha = stamp.get("remote_sha")
    if not stamp_sha:
        return f"{stamp_path} has no remote_sha (written by a pre-v0.13.1 restore)"
    if head != stamp_sha:
        return (
            f"remote head is {head} but the corpus was restored from {stamp_sha} "
            "(someone published in between)"
        )
    return None


def _unexpected_change_reason(
    changed: list[str], corpus_dir: Path, allowance: int
) -> tuple[str, list[str]] | None:
    """Return (reason, paths to show) if the upload set is not what one
    pipeline run should produce, else None.

    Files written this run are newer than the sync stamp (written at the
    end of the restore). A changed file older than the stamp differs from
    the remote without anything in this run having touched it: the stale
    clobber signature. Separately, each Act built this run (xml newer than
    the stamp) may change its own xml, reports and figures; everything else
    (index.json, train.jsonl, ...) must fit within `allowance`. A rebuild
    of ITAA 1997 alone rewrites 362 figures."""
    stamp_path = corpus_dir / _HF_SYNC_STAMP
    stamp_mtime = stamp_path.stat().st_mtime if stamp_path.exists() else None
    untouched = (
        [p for p in changed if (corpus_dir / p).stat().st_mtime <= stamp_mtime]
        if stamp_mtime is not None
        else []
    )
    if untouched:
        return (
            f"{len(untouched)} file(s) differ from the remote but were not written "
            "since the restore",
            untouched,
        )
    built = _built_this_run(corpus_dir, stamp_mtime)
    expected = _expected_paths(corpus_dir, built)
    unexpected = [
        p for p in changed
        if p not in expected
        and not any(p.startswith(f"images/{s}-fig-") for s in built)
    ]
    if len(unexpected) > allowance:
        return (
            f"{len(unexpected)} file(s) outside the {len(built)} Act(s) built this run "
            f"would change, more than allowance {allowance}",
            unexpected,
        )
    return None


def _built_this_run(corpus_dir: Path, stamp_mtime: float | None) -> list[str]:
    """safe_names of Acts whose xml was (re)written since the restore.
    `lexau build`/`update` rewrite xml/<safe_name>.xml for every Act they
    convert, so its mtime is the record of what this run built."""
    if stamp_mtime is None:
        return []
    xml_dir = corpus_dir / "xml"
    if not xml_dir.is_dir():
        return []
    return sorted(p.stem for p in xml_dir.glob("*.xml") if p.stat().st_mtime > stamp_mtime)


def _expected_paths(corpus_dir: Path, built: list[str]) -> set[str]:
    """Paths a rebuild of `built` legitimately rewrites: each Act's xml, its
    reports, and the images its xml references (<img src="corpus/images/...">)."""
    expected: set[str] = set()
    for safe_name in built:
        expected.add(f"xml/{safe_name}.xml")
        for report in (corpus_dir / "reports").glob(f"{safe_name}-v*.json"):
            expected.add(f"reports/{report.name}")
        try:
            root = etree.parse(str(corpus_dir / "xml" / f"{safe_name}.xml")).getroot()
        except (OSError, etree.XMLSyntaxError):
            continue
        for el in root.iter():
            if isinstance(el.tag, str) and etree.QName(el).localname == "img":
                src = el.get("src", "")
                if src.startswith("corpus/"):
                    expected.add(src[len("corpus/"):])
    return expected


@cli.command("export-hf")
@click.option("--repo", required=True, help="HF dataset repo, e.g. cchew/lex-au")
@click.option("--corpus-dir", type=click.Path(path_type=Path), default=Path("corpus"), show_default=True)
@click.option(
    "--readme",
    type=click.Path(exists=True, path_type=Path),
    default=Path("hf-readme.md"),
    show_default=True,
    help="Dataset card to upload as README.md",
)
@click.option(
    "--allow-deletes",
    is_flag=True,
    default=False,
    help=(
        "Reconcile remote deletions even when the local corpus has no fresh "
        f"{_HF_SYNC_STAMP} proving it mirrors the dataset. Only use this when the "
        "local corpus is deliberately authoritative."
    ),
)
@click.option(
    "--change-allowance",
    type=int,
    default=200,
    show_default=True,
    help="Files allowed to change beyond each built Act's own xml, reports and figures (index.json, train.jsonl, ...).",
)
@click.option(
    "--allow-large-change",
    is_flag=True,
    default=False,
    help="Skip the change-set limits, for a deliberate full re-publish (e.g. v0.13.0).",
)
@click.option(
    "--skip-sync-check",
    is_flag=True,
    default=False,
    help=(
        f"Publish without a {_HF_SYNC_STAMP} pinned to the current remote head. Only "
        "for a deliberately authoritative local corpus; may revert others' publishes."
    ),
)
def export_hf(
    repo: str,
    corpus_dir: Path,
    readme: Path,
    allow_deletes: bool,
    change_allowance: int,
    allow_large_change: bool,
    skip_sync_check: bool,
) -> None:
    """Push corpus XML + index + dataset card to a Hugging Face dataset.

    Refuses (non-zero exit, nothing uploaded) unless the corpus is a
    verified restore of the current remote head and the files that differ
    from the remote are limited to what this run built."""
    api = HfApi()
    ignore_patterns = ["docx/**", "doc_spike/**", _HF_SYNC_STAMP]
    head = api.repo_info(repo_id=repo, repo_type="dataset").sha
    if not skip_sync_check:
        reason = _unsynced_reason(head, corpus_dir, repo)
        if reason is not None:
            raise click.ClickException(
                f"Refusing to export: {reason}. Restore into an empty directory with "
                "scripts/restore_corpus_from_hf.py and rebuild, or pass "
                "--skip-sync-check if the local corpus is deliberately authoritative."
            )
    remote = hfsync.remote_files(api, repo, head)
    changed = hfsync.changed_files(corpus_dir, remote, ignore_patterns)
    click.echo(f"{len(changed)} file(s) differ from {repo}@{head}.")
    if not allow_large_change:
        problem = _unexpected_change_reason(changed, corpus_dir, change_allowance)
        if problem is not None:
            reason, paths = problem
            click.echo(f"First {min(20, len(paths))} of {len(paths)}:", err=True)
            for path in paths[:20]:
                click.echo(f"  - {path}", err=True)
            raise click.ClickException(
                f"Refusing to export: {reason}. Pass --allow-large-change only for a "
                "deliberate full re-publish."
            )
    click.echo(f"Uploading corpus to {repo}…")
    # upload_large_folder (not upload_folder) hashes files first and skips
    # ones unchanged since the last commit, and avoided a reproducible
    # SSLError upload_folder hit on this dataset's file count (2026-07-20).
    api.upload_large_folder(
        folder_path=str(corpus_dir),
        repo_id=repo,
        repo_type="dataset",
        ignore_patterns=ignore_patterns,
    )
    click.echo(f"Uploading dataset card from {readme}…")
    api.upload_file(
        path_or_fileobj=str(readme),
        path_in_repo="README.md",
        repo_id=repo,
        repo_type="dataset",
        commit_message="lex-au dataset card update",
    )
    click.echo("Reconciling deleted files…")
    stale_reason = None if allow_deletes else _stale_sync_reason(corpus_dir, repo)
    if stale_reason is not None:
        click.echo(f"WARNING: skipping remote-deletion reconcile -- {stale_reason}.")
        click.echo(
            "  Additions and updates were uploaded, but nothing was deleted. Re-run "
            "scripts/restore_corpus_from_hf.py against this corpus, or pass "
            "--allow-deletes if the local corpus is deliberately authoritative."
        )
        click.echo("Upload complete.")
        return
    deleted = _reconcile_deleted_files(api, repo, corpus_dir, ignore_patterns)
    if deleted:
        click.echo("Deleted orphaned remote files:")
        for path in deleted:
            click.echo(f"  - {path}")
    else:
        click.echo("No orphaned remote files to delete.")
    click.echo("Upload complete.")


@cli.command("export-jsonl")
@click.option("--corpus-dir", type=click.Path(path_type=Path), default=Path("corpus"), show_default=True)
def export_jsonl(corpus_dir: Path) -> None:
    """Write corpus/data/train.jsonl — one row per Act, from index.json.

    HF's auto-parquet-conversion / Data Viewer can't parse .xml (skipped
    entirely) or a single-dict index.json (not row-shaped), and falls back to
    inferring a schema from reports/*.json, which drifts across pipeline
    versions. This gives it a proper tabular file to key off instead —
    referenced explicitly via hf-readme.md's `configs:` block.
    """
    index_path = corpus_dir / "index.json"
    index = json.loads(index_path.read_text())
    data_dir = corpus_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    out_path = data_dir / "train.jsonl"

    rows = 0
    with out_path.open("w") as f:
        for slug, entry in sorted(index["acts"].items()):
            row = {
                "slug": slug,
                "name": entry["name"],
                "title_id": entry["title_id"],
                "comp_id": entry["comp_id"],
                "comp_num": entry["comp_num"],
                "year": entry["year"],
                "number": entry["number"],
                "effective_date": entry["effective_date"],
                "xml_path": entry["xml_path"],
                "aliases": entry.get("aliases", []),
            }
            f.write(json.dumps(row) + "\n")
            rows += 1

    click.echo(f"Wrote {rows} rows -> {out_path}")


@cli.command("list-acts")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Write to file instead of stdout (e.g. acts.txt)",
)
@click.option("--page-size", default=100, show_default=True, help="OData page size per request")
def list_acts(output: Path | None, page_size: int) -> None:
    """List all in-force Commonwealth Acts from legislation.gov.au."""
    crawler = Crawler()
    click.echo("Fetching Act list from legislation.gov.au…", err=True)
    names = crawler.list_acts(page_size=page_size)
    click.echo(f"Found {len(names)} Acts.", err=True)
    text = "\n".join(names) + "\n"
    if output:
        output.write_text(text)
        click.echo(f"Written to {output}", err=True)
    else:
        click.echo(text, nl=False)


@cli.command("list-instruments")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Write to file instead of stdout (e.g. instruments.txt)",
)
@click.option("--page-size", default=100, show_default=True, help="OData page size per request")
def list_instruments(output: Path | None, page_size: int) -> None:
    """List all in-force Commonwealth legislative instruments from legislation.gov.au."""
    crawler = Crawler()
    click.echo("Fetching instrument list from legislation.gov.au…", err=True)
    names = crawler.list_instruments(page_size=page_size)
    click.echo(f"Found {len(names)} instruments.", err=True)
    text = "\n".join(names) + "\n"
    if output:
        output.write_text(text)
        click.echo(f"Written to {output}", err=True)
    else:
        click.echo(text, nl=False)


@cli.command()
@click.option("--since", required=True, help="ISO date, e.g. 2026-01-01")
@click.option(
    "--corpus-dir",
    type=click.Path(path_type=Path),
    default=Path("corpus"),
    show_default=True,
)
def update(since: str, corpus_dir: Path) -> None:
    """Fetch and re-convert Acts modified since a given date."""
    from datetime import date as _date

    since_date = _date.fromisoformat(since)

    crawler = Crawler()
    click.echo(f"Checking for Acts modified since {since}...")
    modified = crawler.list_modified_since(since_date)

    if not modified:
        click.echo("No modified Acts found.")
        return

    # Only re-build Acts already in the corpus; legislation.gov.au returns
    # modifications across all Acts, not just our corpus members.
    corpus = Corpus(corpus_dir)
    corpus_names = {meta.name for meta in corpus.all_metadata()}
    in_corpus = [name for name in modified if name in corpus_names]

    if not in_corpus:
        click.echo(
            f"Found {len(modified)} modified Act(s), none in the corpus."
        )
        return

    click.echo(f"Found {len(in_corpus)} modified corpus Act(s): {', '.join(in_corpus)}")
    # NOT force=True: legislation.gov.au's "modified since" signal is broader
    # than "the compilation actually changed" (observed live 2026-10-13 --
    # every Act in a 3,085-Act corpus showed as "modified" across a handful
    # of weekly runs). force=True bypassed is_current()'s comp_num check, so
    # every one of those got unconditionally rebuilt -- re-stamping
    # FRBRManifestation's Generation date even when nothing legally changed,
    # which made lex-au-search's raw-file-hash delta detection useless (every
    # Act looked changed, every week, forever). Letting is_current() do its
    # job here means an Act's XML (and its content hash) only actually
    # changes when legislation.gov.au issues a new compilation; _build_acts's
    # skip path still stamps last_checked, so "did lex-au reconsider this
    # Act" stays visible even when nothing rebuilds.
    _build_acts(in_corpus, corpus_dir, force=False)
