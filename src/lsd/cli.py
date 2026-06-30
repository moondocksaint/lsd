"""LSD command-line interface.

Usage:
    lsd build <url> [--output DIR] [--mode MODE] [--dry-run]
    lsd build <url1> <url2> ... [--output DIR] [--mode MODE] [--retrieval-backend NAME]
    lsd check <url>
    lsd eval <case-dir> [--expected-dir DIR]
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
@click.option(
    "--retrieval-backend", "retrieval_backend",
    default=None,
    help="Retrieval backend for multi-source builds. Default: naive. "
         "Available: naive. (bm25, colbert, pixelrag coming in future releases.)",
)
@click.option(
    "--token-threshold",
    default=50_000,
    show_default=True,
    help="Token count at which to warn and truncate for multi-source builds.",
)
def build_cmd(
    urls: tuple[str, ...],
    output: Optional[str],
    mode: Optional[str],
    dry_run: bool,
    retrieval_backend: Optional[str],
    token_threshold: int,
) -> None:
    """Build a skill package from one or more URLs.

    Single URL: produces a full skill package (SKILL.md, source.md, …).
    Multiple URLs: produces a multi-source package (source-1.md, source-2.md,
    sources-index.md, conflicts.md, …) with retrieval-grounded compilation.
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
        if retrieval_backend:
            console.print(f"[dim]Retrieval backend: {retrieval_backend}[/dim]")

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
                ctx = build_multi(
                    list(urls),
                    out_dir,
                    mode_override=mode_override,
                    retrieval_backend_name=retrieval_backend,
                    token_threshold=token_threshold,
                )
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

        # Retrieval index summary
        if hasattr(ctx, "_retrieval_index"):
            ri = ctx._retrieval_index
            console.print(
                f"[dim]Retrieval index: {ri.backend_name} backend, "
                f"{ri.source_count} source(s), "
                f"~{ri.total_chars // 1000}K chars[/dim]"
            )

        # Sources table
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


@main.command(name="eval")
@click.argument("case_dir", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--expected-dir", "expected_dir",
    default=None,
    help="Directory containing expected output files. Defaults to <case_dir>/expected/.",
)
@click.option(
    "--output", "-o",
    default=None,
    help="Where to write the re-run output. Defaults to <case_dir>/actual/.",
)
def eval_cmd(case_dir: str, expected_dir: Optional[str], output: Optional[str]) -> None:
    """Re-run a test case and score it against expected output.

    CASE_DIR must contain an input.json with at least a 'url' field.
    If <case_dir>/expected/ exists, diffs each file and scores against
    the rubric in tests/rubric.md.
    """
    import json

    case_path = Path(case_dir)
    input_file = case_path / "input.json"

    if not input_file.exists():
        console.print(f"[red]No input.json found in {case_dir}[/red]")
        raise SystemExit(1)

    try:
        case = json.loads(input_file.read_text())
    except json.JSONDecodeError as exc:
        console.print(f"[red]Could not parse input.json: {exc}[/red]")
        raise SystemExit(1) from exc

    url = case.get("url")
    if not url:
        console.print("[red]input.json must contain a 'url' field.[/red]")
        raise SystemExit(1)

    mode_override = case.get("ingestion_mode_override")
    out_dir = Path(output) if output else case_path / "actual"

    console.print(Panel.fit(
        f"[bold]LSD eval[/bold] — {case_path.name}",
        border_style="dim",
    ))
    console.print(f"[dim]URL: {url}[/dim]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        progress.add_task("Running pipeline...", total=None)
        try:
            result_dir = build(url, out_dir, mode_override=mode_override)
        except Exception as exc:
            console.print(f"[red]Pipeline failed:[/red] {exc}")
            raise SystemExit(1) from exc

    console.print(f"[green]Pipeline output written to:[/green] {result_dir}")

    # Score against rubric
    exp_dir = Path(expected_dir) if expected_dir else case_path / "expected"
    score, max_score, details = _score_package(result_dir, exp_dir if exp_dir.exists() else None)

    # Score table
    score_table = Table(title="Rubric Score", show_header=True)
    score_table.add_column("Criterion", style="dim")
    score_table.add_column("Score")
    score_table.add_column("Notes")
    for criterion, s, note in details:
        color = "green" if s == s else "yellow"
        score_table.add_row(criterion, str(s), note)
    console.print(score_table)

    threshold_label = "Production-ready" if score >= 12 else \
        "Usable — needs review" if score >= 9 else \
        "Needs rework" if score >= 6 else "Do not promote"
    score_color = "green" if score >= 12 else "yellow" if score >= 9 else "red"
    console.print(
        f"\n[bold {score_color}]Total: {score}/{max_score} — {threshold_label}[/bold {score_color}]"
    )

    if exp_dir.exists():
        console.print("\n[dim]Diffing against expected/...[/dim]")
        _diff_against_expected(result_dir, exp_dir)


def _score_package(package_dir: Path, expected_dir: Path | None) -> tuple[int, int, list]:
    """Score a package directory against the rubric. Returns (score, max, details)."""
    details: list[tuple[str, int, str]] = []

    # 1. Source preservation (0-2)
    has_source = (package_dir / "source.md").exists()
    has_policy = (package_dir / "source-policy.md").exists()
    if has_source and has_policy:
        source_score = 2
        source_note = "source.md + source-policy.md present"
    elif has_source or has_policy:
        source_score = 1
        source_note = "partial — one file missing"
    else:
        source_score = 0
        source_note = "neither file present"
    details.append(("Source preservation", source_score, source_note))

    # 2. Ingestion mode (0-2) — check extraction-report.md has routing notes
    report = package_dir / "extraction-report.md"
    if report.exists():
        content = report.read_text()
        if "Routing rationale" in content and len(content) > 200:
            mode_score = 2
            mode_note = "routing rationale present"
        else:
            mode_score = 1
            mode_note = "report present but rationale thin"
    else:
        mode_score = 0
        mode_note = "extraction-report.md missing"
    details.append(("Ingestion mode", mode_score, mode_note))

    # 3. Skill completeness (0-3)
    skill_file = package_dir / "SKILL.md"
    if skill_file.exists():
        skill_text = skill_file.read_text()
        has_sections = all(
            h in skill_text for h in ["## Core principle", "## Workflow", "## Output format"]
        )
        has_todos = "<!-- TODO" in skill_text
        has_caveats = "## Caveats" in skill_text
        if has_sections and not has_todos and has_caveats:
            skill_score = 3
            skill_note = "all sections filled, caveated"
        elif has_sections and has_caveats:
            skill_score = 2
            skill_note = "all sections present (some TODOs)"
        elif has_sections:
            skill_score = 1
            skill_note = "sections present, caveats missing"
        else:
            skill_score = 0
            skill_note = "key sections missing"
    else:
        skill_score = 0
        skill_note = "SKILL.md missing"
    details.append(("Skill completeness", skill_score, skill_note))

    # 4. Opportunity mapping (0-2)
    opp_file = package_dir / "skill-opportunities.md"
    if opp_file.exists():
        opp_text = opp_file.read_text()
        has_confidence = "Confidence" in opp_text
        has_timing = "Build timing" in opp_text or "build_timing" in opp_text
        if has_confidence and has_timing:
            opp_score = 2
            opp_note = "confidence + timing present"
        else:
            opp_score = 1
            opp_note = "partial opportunity map"
    else:
        opp_score = 0
        opp_note = "skill-opportunities.md missing"
    details.append(("Opportunity mapping", opp_score, opp_note))

    # 5. Governance (0-2)
    meta_file = package_dir / "metadata.json"
    if meta_file.exists():
        try:
            import json
            meta = json.loads(meta_file.read_text())
            has_gov = "governance" in meta
            has_fallback = (
                "fallback_order" in str(meta)
                or "source_dependencies" in meta  # v0.3 multi-source schema
            )
            if has_gov and has_fallback:
                gov_score = 2
                gov_note = "governance + fallback order present"
            elif has_gov or has_fallback:
                gov_score = 1
                gov_note = "partial governance"
            else:
                gov_score = 1
                gov_note = "metadata present but governance thin"
        except Exception:
            gov_score = 0
            gov_note = "metadata.json invalid JSON"
    else:
        gov_score = 0
        gov_note = "metadata.json missing"
    details.append(("Governance", gov_score, gov_note))

    # 6. Caveat faithfulness (0-2)
    if skill_file.exists():
        skill_text = skill_file.read_text()
        has_caveat_section = "## Caveats" in skill_text
        caveat_text = skill_text.split("## Caveats")[-1] if has_caveat_section else ""
        if has_caveat_section and len(caveat_text.strip()) > 50:
            cav_score = 2
            cav_note = "caveats present and substantive"
        elif has_caveat_section:
            cav_score = 1
            cav_note = "caveat section present but thin"
        else:
            cav_score = 0
            cav_note = "no caveats section"
    else:
        cav_score = 0
        cav_note = "SKILL.md missing"
    details.append(("Caveat faithfulness", cav_score, cav_note))

    # 7. Metadata validity (0-1)
    if meta_file.exists():
        try:
            import json
            json.loads(meta_file.read_text())
            meta_score = 1
            meta_note = "valid JSON"
        except Exception:
            meta_score = 0
            meta_note = "invalid JSON"
    else:
        meta_score = 0
        meta_note = "missing"
    details.append(("Metadata validity", meta_score, meta_note))

    total = sum(s for _, s, _ in details)
    return total, 14, details


def _diff_against_expected(actual_dir: Path, expected_dir: Path) -> None:
    """Print a simple diff summary between actual and expected output files."""
    expected_files = list(expected_dir.glob("*"))
    if not expected_files:
        console.print("[dim]Expected directory is empty — nothing to diff.[/dim]")
        return

    for exp_file in sorted(expected_files):
        if exp_file.is_dir():
            continue
        act_file = actual_dir / exp_file.name
        if not act_file.exists():
            console.print(f"  [red]MISSING[/red]  {exp_file.name}")
            continue
        exp_text = exp_file.read_text()
        act_text = act_file.read_text()
        if exp_text == act_text:
            console.print(f"  [green]MATCH[/green]    {exp_file.name}")
        else:
            exp_lines = len(exp_text.splitlines())
            act_lines = len(act_text.splitlines())
            console.print(
                f"  [yellow]DIFFER[/yellow]   {exp_file.name} "
                f"(expected {exp_lines} lines, actual {act_lines} lines)"
            )


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
