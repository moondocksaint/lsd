"""LSD command-line interface.

Usage:
    lsd build <url> [--output DIR] [--mode MODE] [--dry-run]
    lsd build <url1> <url2> ... [--output DIR] [--mode MODE]
    lsd check <url>
    lsd version
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from lsd import __version__
from lsd.backends import get_visual_backend
from lsd.classifier import classify
from lsd.fetcher import fetch
from lsd.models import IngestionMode
from lsd.pipeline import build, build_multi, prepare
from lsd.router import route
from lsd.writer import write_multi_package

console = Console()


@click.group()
def main() -> None:
    """LSD — Link-to-Skill Designer.\n\nTurn any webpage into a reusable Claude skill package."""


@main.command(name="build")
@click.argument("urls", nargs=-1, required=True)
@click.option(
    "--output", "-o",
    default=None,
    help="Output directory. Defaults to ./<slugified-title>/ for single source, ./multi-source/ for multiple.",
)
@click.option(
    "--mode", "-m",
    type=click.Choice(["text-first", "hybrid", "visual-first"]),
    default=None,
    help="Override ingestion mode. Default: auto-detect.",
)
@click.option(
    "--dry-run", is_flag=True,
    help="Classify and route without writing any files.",
)
def build_cmd(
    urls: tuple[str, ...],
    output: Optional[str],
    mode: Optional[str],
    dry_run: bool,
) -> None:
    """Build a skill package from one or more URLs.

    Single URL: produces a full skill package (SKILL.md, source.md, …).
    Multiple URLs: produces a multi-source package (source-1.md, source-2.md,
    sources-index.md, conflicts.md, …).
    """
    console.print(Panel.fit(
        f"[bold]LSD[/bold] v{__version__} — Link-to-Skill Designer",
        border_style="dim",
    ))

    mode_override: IngestionMode | None = mode  # type: ignore[assignment]

    # ------------------------------------------------------------------ #
    # Multi-source path
    # ------------------------------------------------------------------ #
    if len(urls) > 1:
        console.print(f"[dim]Building from {len(urls)} sources...[/dim]")

        if dry_run:
            console.print("\n[yellow]Dry run — no files written.[/yellow]")
            for i, url in enumerate(urls, 1):
                console.print(f"  {i}. {url}")
            return

        out_dir = Path(output) if output else Path(".") / "multi-source"

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task(
                f"Fetching {len(urls)} sources in parallel...", total=None
            )
            try:
                ctx = build_multi(list(urls), out_dir, mode_override=mode_override)
            except Exception as exc:
                console.print(f"[red]Multi-source build failed:[/red] {exc}")
                raise SystemExit(1) from exc

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            progress.add_task("Writing package...", total=None)
            try:
                result_dir = write_multi_package(ctx)
            except Exception as exc:
                console.print(f"[red]Write failed:[/red] {exc}")
                raise SystemExit(1) from exc

        # Sources summary table
        table = Table(show_header=True, title="Sources")
        table.add_column("#", style="dim", width=3)
        table.add_column("URL")
        table.add_column("Type", width=12)
        table.add_column("Mode", width=14)
        table.add_column("Fit", width=8)
        for e in ctx.sources:
            table.add_row(
                str(e.index),
                e.url[:70],
                str(e.source_type),
                str(e.ingestion_mode),
                getattr(e.fit, "overall_fit", "—"),
            )
        console.print(table)

        # Conflict summary
        conflict_style = "bold red" if ctx.conflict_report.has_blocking_conflicts else "dim"
        console.print(Panel(
            f"[{conflict_style}]{ctx.conflict_report.summary}[/{conflict_style}]",
            title="Conflict Report",
        ))
        if ctx.conflict_report.has_blocking_conflicts:
            console.print(
                "[bold red]Warning: high-severity contradictions detected. "
                "Review conflicts.md before using this skill.[/bold red]"
            )

        console.print(f"\n[bold green]✓ Package written to:[/bold green] {result_dir}")
        _print_tree(result_dir)
        return

    # ------------------------------------------------------------------ #
    # Single-source path (original behaviour)
    # ------------------------------------------------------------------ #
    url = urls[0]

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:

        progress.add_task("Fetching, classifying, routing...", total=None)
        try:
            routing = prepare(url, mode_override)
        except Exception as exc:
            console.print(f"[red]Fetch failed:[/red] {exc}")
            raise SystemExit(1) from exc

    fetch_result = routing.fetch
    source_fit = routing.source_fit
    visual_backend = routing.visual_backend

    # Summary table
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_row("[dim]URL[/dim]", fetch_result.canonical_url)
    table.add_row("[dim]Title[/dim]", fetch_result.title[:80])
    table.add_row("[dim]Words[/dim]", str(fetch_result.word_count))
    table.add_row("[dim]Mode[/dim]", f"[bold cyan]{routing.mode}[/bold cyan]")
    table.add_row("[dim]Fit[/dim]", source_fit.overall_fit)
    table.add_row(
        "[dim]Visual backend[/dim]",
        f"[green]{visual_backend.name}[/green]" if visual_backend else "[yellow]none (text-first only)[/yellow]",
    )
    console.print(table)
    console.print(f"[dim]{routing.routing_notes}[/dim]")

    if dry_run:
        console.print("\n[yellow]Dry run — no files written.[/yellow]")
        return

    # Resolve output dir
    if output:
        out_dir = Path(output)
    else:
        slug = _slugify(fetch_result.title)[:40]
        out_dir = Path(".") / slug

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Building package...", total=None)
        try:
            result_dir = build(url, out_dir, mode_override=mode_override, routing=routing)
        except Exception as exc:
            console.print(f"[red]Build failed:[/red] {exc}")
            raise SystemExit(1) from exc

    console.print(f"\n[bold green]✓ Package written to:[/bold green] {result_dir}")
    _print_tree(result_dir)


@main.command(name="check")
@click.argument("url")
def check_cmd(url: str) -> None:
    """Classify a URL and show routing decision without building."""
    console.print(f"Checking [bold]{url}[/bold]...")
    try:
        fetch_result = fetch(url)
    except Exception as exc:
        console.print(f"[red]Fetch failed:[/red] {exc}")
        raise SystemExit(1) from exc

    source_fit = classify(fetch_result)
    visual_backend = get_visual_backend()
    mode, notes = route(fetch_result, source_fit, visual_backend is not None)

    table = Table(title="Source Classification", show_header=True)
    table.add_column("Dimension", style="dim")
    table.add_column("Score")
    table.add_row("Overall fit", source_fit.overall_fit)
    table.add_row("Rule density", source_fit.rule_density)
    table.add_row("Procedure density", source_fit.procedure_density)
    table.add_row("Example density", source_fit.example_density)
    table.add_row("Stability", source_fit.stability)
    table.add_row("Ingestion mode", f"[bold cyan]{mode}[/bold cyan]")
    console.print(table)
    console.print(f"\n[dim]{notes}[/dim]")
    console.print(f"\n[dim]{source_fit.fit_notes}[/dim]")


@main.command()
def version() -> None:
    """Show LSD version."""
    console.print(f"lsd {__version__}")


def _slugify(text: str) -> str:
    import re
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


def _print_tree(path: Path) -> None:
    console.print("")
    for f in sorted(path.rglob("*")):
        rel = f.relative_to(path)
        depth = len(rel.parts) - 1
        indent = "  " * depth
        icon = "📁" if f.is_dir() else "📄"
        console.print(f"  {indent}{icon} {rel.name}")
