from __future__ import annotations

import sys
from pathlib import Path

import click
from docx import Document
from huggingface_hub import HfApi

from lexau.corpus import Corpus
from lexau.crawler import Crawler
from lexau.parser import parse_paragraph
from lexau.builder import AknBuilder


@click.group()
def cli() -> None:
    """lex-au: Commonwealth Acts as AKN 3.0 XML."""


def _build_acts(act_names: list[str], corpus_dir: Path, force: bool) -> None:
    """Build Acts: download DOCX and convert to AKN XML."""
    corpus = Corpus(corpus_dir)
    crawler = Crawler()
    docx_dir = corpus_dir / "docx"

    for act_name in act_names:
        try:
            click.echo(f"[fetch ] {act_name}")
            meta = crawler.fetch_metadata(act_name)
            if meta is None:
                click.echo(f"  SKIP -- not found in legislation.gov.au", err=True)
                continue

            if not force and corpus.is_current(meta):
                click.echo(f"  SKIP -- compilation #{meta.comp_num} already current")
                continue

            docx_path = crawler.fetch_docx(meta, docx_dir)
            if docx_path is None:
                click.echo(f"  SKIP -- DOCX download failed", err=True)
                continue

            click.echo(f"[convert] {act_name}")
            doc = Document(docx_path)
            builder = AknBuilder(meta)
            for para in doc.paragraphs:
                style = para.style.name if para.style else "Default"
                builder.add(parse_paragraph(style, para.text))

            xml, validation = builder.build()
            if not validation.passed:
                for err in validation.errors:
                    click.echo(f"  [validation] {err}", err=True)
            saved = corpus.save(meta, xml)
            click.echo(f"  saved -> {saved.relative_to(corpus_dir)}")
        except Exception as exc:  # noqa: BLE001 - one bad Act must not abort the batch
            click.echo(f"  ERROR -- {act_name}: {exc}", err=True)
            continue

    click.echo("Done.")


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
def build(
    acts: tuple[str, ...],
    list_file: Path | None,
    build_all: bool,
    corpus_dir: Path,
    force: bool,
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

    _build_acts(act_names, corpus_dir, force)


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
def export_hf(repo: str, corpus_dir: Path, readme: Path) -> None:
    """Push corpus XML + index + dataset card to a Hugging Face dataset."""
    api = HfApi()
    click.echo(f"Uploading corpus to {repo}…")
    api.upload_folder(
        folder_path=str(corpus_dir),
        repo_id=repo,
        repo_type="dataset",
        commit_message="lex-au corpus update",
        ignore_patterns=["docx/**"],
    )
    click.echo(f"Uploading dataset card from {readme}…")
    api.upload_file(
        path_or_fileobj=str(readme),
        path_in_repo="README.md",
        repo_id=repo,
        repo_type="dataset",
        commit_message="lex-au dataset card update",
    )
    click.echo("Upload complete.")


@cli.command("list-acts")
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Write to file instead of stdout (e.g. acts.txt)",
)
@click.option("--page-size", default=200, show_default=True, help="OData page size per request")
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
    _build_acts(in_corpus, corpus_dir, force=True)
