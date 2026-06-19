from __future__ import annotations

import sys
from pathlib import Path

import click
from docx import Document

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

        xml = builder.build()
        saved = corpus.save(meta, xml)
        click.echo(f"  saved -> {saved.relative_to(corpus_dir)}")

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

    click.echo(f"Found {len(modified)} modified Act(s): {', '.join(modified)}")
    _build_acts(modified, corpus_dir, force=True)
