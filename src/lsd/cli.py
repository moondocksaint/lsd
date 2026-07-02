"""LSD command-line interface.

Usage:
    lsd build <url> [--output DIR] [--mode MODE] [--dry-run]
    lsd build <url1> <url2> ... [--output DIR] [--mode MODE] [--retrieval-backend NAME]
    lsd check <package-dir-or-url> [--url URL]
    lsd package <package-dir> [--zip] [--output PATH]
    lsd eval <case-dir> [--expected-dir DIR]
    lsd version
"""

from __future__ import annotations

import json
import re
import zipfile
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
    """LSD — Link-to-Skill Designer.\n\nTurn any webpage into a reusable agent skill package."""


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------

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
    help="Retrieval backend for multi-source builds. Default: naive.",
)
@click.option(
    "--token-threshold",
    default=50_000,
    show_default=True,
    help="Token count at which to warn and truncate for multi-source builds.",
)
@click.option(
    "--name",
    default=None,
    help="Override skill name slug in generated SKILL.md frontmatter.",
)
def build_cmd(
    urls: tuple[str, ...],
    output: Optional[str],
    mode: Optional[str],
    dry_run: bool,
    retrieval_backend: Optional[str],
    token_threshold: int,
    name: Optional[str],
) -> None:
    """Build a skill package from one or more URLs."""
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
            progress.add_task("Compiling and writing package...", total=None)
            try:
                result_dir = write_multi_package(ctx)
            except Exception as exc:
                console.print(f"[red]Write failed:[/red] {exc}")
                raise SystemExit(1) from exc

        # Retrieval index summary
        if hasattr(ctx, "_retrieval_index"):
            ri = ctx._retrieval_index
            trunc_note = " [yellow](truncated)[/yellow]" if getattr(ri, "was_truncated", False) else ""
            estimated_tokens = getattr(ctx, "estimated_tokens", 0)
            token_note = f", ~{estimated_tokens:,} tokens" if estimated_tokens else ""
            console.print(
                f"[dim]Retrieval index: {ri.backend_name} backend, "
                f"{ri.source_count} source(s), "
                f"~{ri.total_chars // 1000}K chars{token_note}[/dim]{trunc_note}"
            )

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

        # Post-build verdict for multi-source
        _print_verdict(ctx.combined_opportunities)

        console.print(f"\n[bold green]✓ Package written to:[/bold green] {result_dir}")
        _print_tree(result_dir)
        return

    # ------------------------------------------------------------------ #
    # Single-source path
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

    # Post-build verdict — read opportunity_map from metadata.json
    _print_verdict_from_package(result_dir)

    console.print(f"\n[bold green]✓ Package written to:[/bold green] {result_dir}")
    _print_tree(result_dir)


# ---------------------------------------------------------------------------
# Post-build verdict helpers
# ---------------------------------------------------------------------------

def _print_verdict(opp) -> None:
    """Print the post-build verdict panel from an OpportunityMap object."""
    action = opp.recommended_action
    assessment = opp.assessment

    summary = assessment.summary if assessment and hasattr(assessment, "summary") else ""
    limitations = assessment.limitations if assessment else []
    tool_candidates = opp.tool_candidates if hasattr(opp, "tool_candidates") else []
    stability_warning = assessment.stability_warning if assessment else ""
    breadth_warning = assessment.breadth_warning if assessment else ""

    _render_verdict_panel(
        action=action,
        summary=summary,
        limitations=limitations,
        tool_candidates=tool_candidates,
        stability_warning=stability_warning,
        breadth_warning=breadth_warning,
    )


def _print_verdict_from_package(package_dir: Path) -> None:
    """Read metadata.json from a just-written package and print the verdict panel."""
    meta_path = package_dir / "metadata.json"
    if not meta_path.exists():
        return
    try:
        meta = json.loads(meta_path.read_text())
    except Exception:
        return

    opp_summary = meta.get("opportunity_summary", {})
    action = opp_summary.get("recommended_action", "build")
    assessment = opp_summary.get("assessment", {})
    summary = assessment.get("summary", "")
    limitations = assessment.get("limitations", [])
    tool_candidate_count = assessment.get("tool_candidate_count", 0)
    tool_candidates_raw = opp_summary.get("tool_candidates", [])
    stability_warning = assessment.get("stability_warning", "")
    breadth_warning = assessment.get("breadth_warning", "")

    # Reconstruct minimal tool candidate objects for display
    class _TC:
        def __init__(self, d: dict):
            self.type = d.get("type", "")
            self.confidence = d.get("confidence", "")
            self.why_fit = d.get("why_fit", "")

    tool_candidates = [_TC(tc) for tc in tool_candidates_raw]
    if not tool_candidates and tool_candidate_count:
        # Metadata has count but no list — show count-only note
        tool_candidates = [_TC({"type": f"{tool_candidate_count} tool type(s) detected", "confidence": "", "why_fit": "see skill-opportunities.md"})]

    _render_verdict_panel(
        action=action,
        summary=summary,
        limitations=limitations,
        tool_candidates=tool_candidates,
        stability_warning=stability_warning,
        breadth_warning=breadth_warning,
    )


def _render_verdict_panel(
    action: str,
    summary: str,
    limitations: list,
    tool_candidates: list,
    stability_warning: str,
    breadth_warning: str,
) -> None:
    """Render the post-build verdict as a Rich panel."""
    if action in ("build_one_skill", "build_multiple_skills", "build"):
        border = "green"
        multi = action == "build_multiple_skills"
        title = (
            "[bold green]Verdict: Build (multiple skills)[/bold green]"
            if multi else
            "[bold green]Verdict: Build[/bold green]"
        )
        body_lines = [
            "[green]This source is a good fit for a skill.[/green]"
            if not multi else
            "[green]This source supports multiple skill types — consider building each.[/green]"
        ]
        if summary:
            body_lines.append(f"\n{summary}")

    elif action == "build_with_caveats":
        border = "yellow"
        title = "[bold yellow]Verdict: Build with caveats[/bold yellow]"
        body_lines = [
            "[yellow]This skill was built, but the source has known limitations.[/yellow]",
            "[yellow]Review carefully before promoting to production.[/yellow]",
        ]
        if summary:
            body_lines.append(f"\n{summary}")
        if limitations:
            body_lines.append("\n[bold]Limitations:[/bold]")
            for lim in limitations:
                body_lines.append(f"  • {lim}")
        if stability_warning:
            body_lines.append(f"\n[yellow]Stability:[/yellow] {stability_warning}")
        if breadth_warning:
            body_lines.append(f"[yellow]Breadth:[/yellow] {breadth_warning}")

    elif action == "defer":
        border = "red"
        title = "[bold red]Verdict: Defer[/bold red]"
        body_lines = [
            "[red]This source is not a good fit for a skill at this time.[/red]",
        ]
        if summary:
            body_lines.append(f"\n{summary}")
        if limitations:
            body_lines.append("\n[bold]Reasons:[/bold]")
            for lim in limitations:
                body_lines.append(f"  • {lim}")

    else:
        # Unknown action — skip panel
        return

    # Tool candidates footnote — shown prominently for build_with_caveats
    if tool_candidates:
        body_lines.append("")
        tc_types = ", ".join(
            tc.type for tc in tool_candidates if tc.type
        )
        body_lines.append(
            f"[dim]Tool opportunity detected ({tc_types}). "
            "A tool may serve this source better than a skill — "
            "see skill-opportunities.md.[/dim]"
        )

    console.print("")
    console.print(Panel(
        "\n".join(body_lines),
        title=title,
        border_style=border,
    ))


# ---------------------------------------------------------------------------
# check  (G3: real drift detection)
# ---------------------------------------------------------------------------

@main.command(name="check")
@click.argument("target")
@click.option(
    "--url",
    default=None,
    help="Override the source URL to check against (useful if the canonical URL has moved).",
)
def check_cmd(target: str, url: Optional[str]) -> None:
    """Detect source drift for a skill package or a single URL.

    TARGET can be:
      - A local package directory (contains metadata.json) — compares
        normalized_hash for each source dependency.
      - A single URL — fetches, classifies, and routes (original behaviour);
        also checks against any local package if --url points to one.

    Drift states:
      UNCHANGED   Hash identical — no action needed.
      MINOR       Content changed, heading structure intact — consider rebuild.
      SUBSTANTIAL Major rewrite detected — warn, do not auto-overwrite.
      GONE        URL unreachable (4xx/5xx/timeout) — preserve existing package.
      REDIRECTED  URL permanently redirected to a new location.
    """
    target_path = Path(target)
    is_package = target_path.is_dir() and (target_path / "metadata.json").exists()

    if is_package:
        _check_package(target_path, url_override=url)
    else:
        # Treat target as a URL — original classify+route behaviour
        _check_url(target)


def _check_package(package_dir: Path, url_override: Optional[str] = None) -> None:
    """Re-fetch each source in the package and compare hashes."""
    meta_path = package_dir / "metadata.json"
    try:
        meta = json.loads(meta_path.read_text())
    except Exception as exc:
        console.print(f"[red]Could not read metadata.json:[/red] {exc}")
        raise SystemExit(1) from exc

    # Collect source entries — single or multi
    deps = []
    if "source_dependency" in meta:
        deps = [meta["source_dependency"]]
    elif "source_dependencies" in meta:
        deps = meta["source_dependencies"]
    else:
        console.print("[red]metadata.json has no source_dependency or source_dependencies key.[/red]")
        raise SystemExit(1)

    console.print(Panel.fit(
        f"[bold]LSD check[/bold] — {package_dir.name} ({len(deps)} source{'s' if len(deps) > 1 else ''})",
        border_style="dim",
    ))

    results = []
    for dep in deps:
        check_url = url_override or dep.get("canonical_url") or dep.get("url")
        stored_hash = dep.get("normalized_hash", "")
        idx = dep.get("index", "")
        label = f"Source {idx}: " if idx else ""

        if not check_url:
            results.append((label + "?", "ERROR", "No URL in metadata", "", ""))
            continue

        # Resolve the stored source.md path for this dep so _classify_magnitude
        # can diff old vs new normalised text directly rather than using proxies.
        # Single-source: source.md; multi-source: source-{index}.md.
        if idx:
            source_file = package_dir / f"source-{idx}.md"
        else:
            source_file = package_dir / "source.md"
        old_source_path = source_file if source_file.exists() else None

        console.print(f"[dim]Fetching {check_url}...[/dim]")
        state, new_hash, magnitude_note, redirect_url = _fetch_and_classify_drift(
            check_url, stored_hash, old_source_path=old_source_path
        )
        results.append((label + check_url, state, magnitude_note, new_hash, redirect_url))

    # Results table
    table = Table(title="Drift Check Results", show_header=True)
    table.add_column("Source", max_width=50)
    table.add_column("State", width=14)
    table.add_column("Notes")
    for url_label, state, notes, _, _ in results:
        color = {
            "UNCHANGED": "green",
            "MINOR": "yellow",
            "SUBSTANTIAL": "bold red",
            "GONE": "red",
            "REDIRECTED": "cyan",
            "ERROR": "red",
        }.get(state, "white")
        table.add_row(url_label[:50], f"[{color}]{state}[/{color}]", notes)
    console.print(table)

    # Guidance per state
    for url_label, state, notes, new_hash, redirect_url in results:
        if state == "UNCHANGED":
            pass  # already clear from table
        elif state == "MINOR":
            console.print(
                f"\n[yellow]Minor change detected.[/yellow] "
                "Content has changed but structure is intact. "
                "Consider rebuilding: [bold]lsd build <url> --output <package-dir>[/bold]"
            )
        elif state == "SUBSTANTIAL":
            console.print(
                f"\n[bold red]Substantial change detected.[/bold red] "
                "The source has been significantly rewritten. "
                "The original motivation for this skill may no longer apply. "
                "Review the source before rebuilding. "
                "Do not auto-overwrite — use a new output directory."
            )
        elif state == "GONE":
            console.print(
                f"\n[red]Source URL is unreachable.[/red] "
                "The existing package is preserved. "
                "Check source-policy.md for the fallback chain."
            )
        elif state == "REDIRECTED":
            console.print(
                f"\n[cyan]Source URL has moved to:[/cyan] {redirect_url}\n"
                "Consider updating the canonical URL in metadata.json and rebuilding."
            )
        elif state == "ERROR":
            console.print(f"\n[red]Error checking source.[/red] {notes}")


def _fetch_and_classify_drift(
    url: str,
    stored_hash: str,
    old_source_path: Path | None = None,
) -> tuple[str, str, str, str]:
    """Fetch a URL and classify drift against stored_hash.

    Returns (state, new_hash, magnitude_note, redirect_url).
    state: UNCHANGED | MINOR | SUBSTANTIAL | GONE | REDIRECTED | ERROR

    old_source_path: if provided and the file exists, _classify_magnitude will
    diff the stored source.md text against the new normalised text directly,
    producing a sharper MINOR/SUBSTANTIAL signal than the word-count heuristic.
    """
    from lsd.normaliser import content_hash, normalise

    # Check for redirect before full fetch
    redirect_url = _detect_redirect(url)
    if redirect_url and redirect_url != url:
        return "REDIRECTED", "", f"Redirected to {redirect_url[:80]}", redirect_url

    try:
        fetch_result = fetch(url)
    except Exception as exc:
        err = str(exc)
        if any(code in err for code in ("404", "403", "410", "timeout", "connect")):
            return "GONE", "", str(exc)[:120], ""
        return "ERROR", "", str(exc)[:120], ""

    normalised = normalise(fetch_result)
    new_hash = content_hash(normalised)

    if new_hash == stored_hash:
        return "UNCHANGED", new_hash, "Hash identical", ""

    # Load stored source text for direct diffing if available
    old_normalised: str | None = None
    if old_source_path is not None:
        try:
            old_normalised = old_source_path.read_text(encoding="utf-8")
        except Exception:
            pass  # fall back to proxy heuristic

    magnitude, note = _classify_magnitude(normalised, old_normalised=old_normalised)
    return magnitude, new_hash, note, ""


def _detect_redirect(url: str) -> str:
    """Return the final URL after following redirects, or empty string on error."""
    try:
        import httpx
        resp = httpx.head(url, follow_redirects=True, timeout=10)
        final = str(resp.url)
        return final if final != url else ""
    except Exception:
        return ""


def _classify_magnitude(
    new_normalised: str,
    old_normalised: str | None = None,
) -> tuple[str, str]:
    """Classify the magnitude of a content change as MINOR or SUBSTANTIAL.

    Two modes depending on whether the stored source.md text is available:

    Direct diff (preferred — when old_normalised is provided):
      Uses difflib.SequenceMatcher on the normalised line sets to compute a
      similarity ratio, plus heading-set symmetric difference and word-count
      ratio. Thresholds:
        similarity < 0.60  → SUBSTANTIAL  (> 40% of content is different)
        heading loss > 30% → SUBSTANTIAL  (major structural reorganisation)
        word ratio < 0.50 or > 2.5 → SUBSTANTIAL  (dramatic size shift)
        otherwise          → MINOR

    Proxy heuristic (fallback — when old_normalised is absent):
      Uses new content word count as proxy. Less accurate; biased toward
      MINOR because we lack the old baseline.
        new_words < 200    → SUBSTANTIAL  (likely truncation or gate)
        otherwise          → MINOR

    Swap-candidate: replace with an embedding-based semantic similarity when a
    low-latency embedding API is available in the LSD environment — semantic
    drift (same words, different meaning) is invisible to both modes above.
    """
    import difflib

    new_words = len(new_normalised.split())
    new_headings = set(re.findall(r"^#{1,3}\s+(.+)$", new_normalised, re.MULTILINE))

    # ------------------------------------------------------------------ #
    # Direct diff — old source.md text available
    # ------------------------------------------------------------------ #
    if old_normalised is not None:
        old_words = len(old_normalised.split())
        old_headings = set(re.findall(r"^#{1,3}\s+(.+)$", old_normalised, re.MULTILINE))

        # Similarity ratio on content lines (strip LSD metadata header lines
        # before diffing so timestamps / word-count lines don't skew the score)
        old_lines = _content_lines(old_normalised)
        new_lines = _content_lines(new_normalised)
        ratio = difflib.SequenceMatcher(None, old_lines, new_lines).ratio()

        # Word-count ratio
        word_ratio = new_words / old_words if old_words else 1.0

        # Heading loss: headings present in old but gone in new
        if old_headings:
            lost_fraction = len(old_headings - new_headings) / len(old_headings)
        else:
            lost_fraction = 0.0

        reasons: list[str] = []
        if ratio < 0.60:
            reasons.append(f"similarity {ratio:.0%}")
        if lost_fraction > 0.30:
            reasons.append(f"{lost_fraction:.0%} of headings removed")
        if word_ratio < 0.50:
            reasons.append(f"word count dropped to {word_ratio:.0%}")
        elif word_ratio > 2.5:
            reasons.append(f"word count grew to {word_ratio:.1f}×")

        if reasons:
            detail = "; ".join(reasons)
            return (
                "SUBSTANTIAL",
                f"{new_words:,} words now vs {old_words:,} before — {detail}",
            )

        # MINOR — surface the similarity score so the user can judge
        changed_headings = old_headings.symmetric_difference(new_headings)
        heading_note = (
            f", {len(changed_headings)} heading(s) changed" if changed_headings else ""
        )
        return (
            "MINOR",
            f"similarity {ratio:.0%}, {new_words:,} words (was {old_words:,}){heading_note}",
        )

    # ------------------------------------------------------------------ #
    # Proxy heuristic — no stored source text
    # ------------------------------------------------------------------ #
    if new_words < 200:
        return (
            "SUBSTANTIAL",
            f"New content very short ({new_words} words) — possible truncation or gate "
            "(no stored source.md to compare against)",
        )

    heading_note = f", {len(new_headings)} headings" if new_headings else ", no headings"
    return (
        "MINOR",
        f"Content changed, {new_words:,} words{heading_note} "
        "(no stored source.md — proxy estimate only)",
    )


def _content_lines(normalised: str) -> list[str]:
    """Return content lines from a normalised source, stripping the LSD
    metadata header (title, URL, Retrieved, word count lines) that change
    between builds and would otherwise inflate the diff score."""
    lines = normalised.splitlines()
    try:
        content_start = next(
            i for i, ln in enumerate(lines) if ln.strip() == "## Content"
        )
        return lines[content_start:]
    except StopIteration:
        return lines


def _check_url(url: str) -> None:
    """Original classify+route behaviour for a single URL (no package dir)."""
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


# ---------------------------------------------------------------------------
# package  (G4: ZIP for webapp/desktop installation)
# ---------------------------------------------------------------------------

@main.command(name="package")
@click.argument("package_dir", type=click.Path(exists=True, file_okay=False))
@click.option(
    "--zip", "make_zip", is_flag=True, default=False,
    help="Produce a ZIP file for claude.ai / desktop app installation.",
)
@click.option(
    "--output", "-o",
    default=None,
    help="Output path for the ZIP file. Defaults to <package-dir>/../<name>.zip",
)
def package_cmd(package_dir: str, make_zip: bool, output: Optional[str]) -> None:
    """Validate and package a skill for installation.

    Validates the SKILL.md against the agentskills spec (name field,
    allowed frontmatter keys). With --zip, produces a ZIP file suitable
    for upload to claude.ai (Customize > Skills > + > Upload a skill),
    Claude desktop, or VS Code Copilot.

    The ZIP contains a single folder named after the skill's `name` field,
    which must exactly match the folder name inside the ZIP per the spec.
    """
    pkg_path = Path(package_dir)
    skill_file = pkg_path / "SKILL.md"

    if not skill_file.exists():
        console.print(f"[red]No SKILL.md found in {package_dir}[/red]")
        raise SystemExit(1)

    skill_text = skill_file.read_text()

    # Parse name from frontmatter
    name = _extract_frontmatter_field(skill_text, "name")
    if not name:
        console.print("[red]SKILL.md has no 'name' field in frontmatter.[/red]")
        raise SystemExit(1)

    # Validate name against agentskills spec
    name_errors = _validate_skill_name(name)
    if name_errors:
        console.print(f"[red]Invalid skill name '{name}':[/red]")
        for err in name_errors:
            console.print(f"  • {err}")
        console.print(
            "\n[dim]Fix the name field in SKILL.md frontmatter, then re-run.[/dim]\n"
            "[dim]Valid: lowercase, alphanumeric + hyphens, max 64 chars.[/dim]"
        )
        raise SystemExit(1)

    # Validate allowed frontmatter fields
    field_errors = _validate_frontmatter_fields(skill_text)
    if field_errors:
        console.print("[yellow]Frontmatter warnings (non-blocking):[/yellow]")
        for err in field_errors:
            console.print(f"  • {err}")

    console.print(f"[green]✓[/green] Skill name valid: [bold]{name}[/bold]")

    if not make_zip:
        console.print(
            "\n[dim]Package validated. Use [bold]--zip[/bold] to produce a ZIP for installation.[/dim]"
        )
        return

    # Produce ZIP
    if output:
        zip_path = Path(output)
    else:
        zip_path = pkg_path.parent / f"{name}.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(pkg_path.rglob("*")):
            if f.is_file():
                # Archive path: <name>/<relative-path>
                arc_name = f"{name}/{f.relative_to(pkg_path)}"
                zf.write(f, arc_name)

    console.print(f"\n[bold green]✓ ZIP written to:[/bold green] {zip_path}")
    console.print(
        "\n[dim]To install in Claude.ai:[/dim]\n"
        "  Settings → Customize → Skills → + → Upload a skill\n"
        "\n[dim]To install in Claude Code:[/dim]\n"
        f"  cp -r {package_dir} ~/.claude/skills/{name}/\n"
        "\n[dim]To install in VS Code Copilot:[/dim]\n"
        f"  cp -r {package_dir} .agents/skills/{name}/"
    )


def _extract_frontmatter_field(text: str, field: str) -> str:
    """Extract a field value from YAML frontmatter."""
    match = re.search(rf"^{field}:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip().strip('"\'') if match else ""


def _validate_skill_name(name: str) -> list[str]:
    """Return list of validation errors for a skill name. Empty = valid."""
    errors = []
    if not name:
        errors.append("Name is empty.")
        return errors
    if name != name.lower():
        errors.append(f"Name must be lowercase (got '{name}').")
    if not re.match(r"^[a-z0-9][a-z0-9-]*[a-z0-9]$", name) and len(name) > 1:
        errors.append("Name must contain only lowercase letters, digits, and hyphens.")
    if "--" in name:
        errors.append("Name must not contain consecutive hyphens (--).")
    if len(name) > 64:
        errors.append(f"Name must be ≤ 64 chars (got {len(name)}).")
    return errors


_AGENTSKILLS_ALLOWED = {
    "name", "description", "license", "allowed-tools", "metadata", "compatibility"
}


def _validate_frontmatter_fields(text: str) -> list[str]:
    """Return warnings for frontmatter fields not in the agentskills spec."""
    # Extract frontmatter block
    fm_match = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not fm_match:
        return ["Could not parse frontmatter."]
    fm = fm_match.group(1)
    # Top-level keys only (lines that start without indentation)
    keys = re.findall(r"^([a-z][a-zA-Z_-]*):", fm, re.MULTILINE)
    unknown = [k for k in keys if k not in _AGENTSKILLS_ALLOWED]
    if unknown:
        return [
            f"Non-standard frontmatter key '{k}' — move to metadata: map for spec compliance."
            for k in unknown
        ]
    return []


# ---------------------------------------------------------------------------
# eval
# ---------------------------------------------------------------------------

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
    """Re-run a test case and score it against expected output."""
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

    exp_dir = Path(expected_dir) if expected_dir else case_path / "expected"
    score, max_score, details = _score_package(result_dir, exp_dir if exp_dir.exists() else None)

    score_table = Table(title="Rubric Score", show_header=True)
    score_table.add_column("Criterion", style="dim")
    score_table.add_column("Score")
    score_table.add_column("Notes")
    for criterion, s, note in details:
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


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------

@main.command()
def version() -> None:
    """Show LSD version."""
    console.print(f"lsd {__version__}")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
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


def _score_package(package_dir: Path, expected_dir: Path | None) -> tuple[int, int, list]:
    """Score a package directory against the rubric. Returns (score, max, details)."""
    details: list[tuple[str, int, str]] = []

    # 1. Source preservation (0-2)
    has_source = (package_dir / "source.md").exists()
    has_policy = (package_dir / "source-policy.md").exists()
    if has_source and has_policy:
        source_score, source_note = 2, "source.md + source-policy.md present"
    elif has_source or has_policy:
        source_score, source_note = 1, "partial — one file missing"
    else:
        source_score, source_note = 0, "neither file present"
    details.append(("Source preservation", source_score, source_note))

    # 2. Ingestion mode (0-2)
    report = package_dir / "extraction-report.md"
    if report.exists():
        content = report.read_text()
        if "Routing rationale" in content and len(content) > 200:
            mode_score, mode_note = 2, "routing rationale present"
        else:
            mode_score, mode_note = 1, "report present but rationale thin"
    else:
        mode_score, mode_note = 0, "extraction-report.md missing"
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
            skill_score, skill_note = 3, "all sections filled, caveated"
        elif has_sections and has_caveats:
            skill_score, skill_note = 2, "all sections present (some TODOs)"
        elif has_sections:
            skill_score, skill_note = 1, "sections present, caveats missing"
        else:
            skill_score, skill_note = 0, "key sections missing"
    else:
        skill_score, skill_note = 0, "SKILL.md missing"
    details.append(("Skill completeness", skill_score, skill_note))

    # 4. Opportunity mapping (0-2)
    opp_file = package_dir / "skill-opportunities.md"
    if opp_file.exists():
        opp_text = opp_file.read_text()
        if "Confidence" in opp_text and ("Build timing" in opp_text or "build_timing" in opp_text):
            opp_score, opp_note = 2, "confidence + timing present"
        else:
            opp_score, opp_note = 1, "partial opportunity map"
    else:
        opp_score, opp_note = 0, "skill-opportunities.md missing"
    details.append(("Opportunity mapping", opp_score, opp_note))

    # 5. Governance (0-2)
    meta_file = package_dir / "metadata.json"
    if meta_file.exists():
        try:
            meta = json.loads(meta_file.read_text())
            has_gov = "governance" in meta
            has_fallback = "fallback_order" in str(meta) or "source_dependencies" in meta
            if has_gov and has_fallback:
                gov_score, gov_note = 2, "governance + fallback order present"
            elif has_gov or has_fallback:
                gov_score, gov_note = 1, "partial governance"
            else:
                gov_score, gov_note = 1, "metadata present but governance thin"
        except Exception:
            gov_score, gov_note = 0, "metadata.json invalid JSON"
    else:
        gov_score, gov_note = 0, "metadata.json missing"
    details.append(("Governance", gov_score, gov_note))

    # 6. Caveat faithfulness (0-2)
    if skill_file.exists():
        skill_text = skill_file.read_text()
        has_caveat_section = "## Caveats" in skill_text
        caveat_text = skill_text.split("## Caveats")[-1] if has_caveat_section else ""
        if has_caveat_section and len(caveat_text.strip()) > 50:
            cav_score, cav_note = 2, "caveats present and substantive"
        elif has_caveat_section:
            cav_score, cav_note = 1, "caveat section present but thin"
        else:
            cav_score, cav_note = 0, "no caveats section"
    else:
        cav_score, cav_note = 0, "SKILL.md missing"
    details.append(("Caveat faithfulness", cav_score, cav_note))

    # 7. Metadata validity (0-1)
    if meta_file.exists():
        try:
            json.loads(meta_file.read_text())
            meta_score, meta_note = 1, "valid JSON"
        except Exception:
            meta_score, meta_note = 0, "invalid JSON"
    else:
        meta_score, meta_note = 0, "missing"
    details.append(("Metadata validity", meta_score, meta_note))

    total = sum(s for _, s, _ in details)
    return total, 14, details


_ISO_TIMESTAMP_RE = re.compile(
    r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})'
)
_CONTENT_HASH_RE = re.compile(
    r'(?<="normalized_hash": ")[0-9a-f]{8,}(?=")'
    r'|(?<=`)[0-9a-f]{16}(?=`)'
)
_SCRUBBED_TS = "__TIMESTAMP__"
_SCRUBBED_HASH = "__CONTENT_HASH__"


def _normalize_for_diff(text: str) -> str:
    """Replace volatile fields with stable placeholders for diffing."""
    text = _ISO_TIMESTAMP_RE.sub(_SCRUBBED_TS, text)
    text = _CONTENT_HASH_RE.sub(_SCRUBBED_HASH, text)
    return text


def _diff_against_expected(actual_dir: Path, expected_dir: Path) -> None:
    """Print a simple diff summary between actual and expected output files."""
    expected_files = list(expected_dir.glob("*"))
    if not expected_files:
        console.print("[dim]Expected directory is empty — nothing to diff.[/dim]")
        return

    for exp_file in sorted(expected_files):
        if exp_file.is_dir():
            continue
        if exp_file.suffix not in (".md", ".json", ".txt", ""):
            continue
        act_file = actual_dir / exp_file.name
        if not act_file.exists():
            console.print(f"  [red]MISSING[/red]  {exp_file.name}")
            continue
        exp_text = _normalize_for_diff(exp_file.read_text())
        act_text = _normalize_for_diff(act_file.read_text())
        if exp_text == act_text:
            console.print(f"  [green]MATCH[/green]    {exp_file.name}")
        else:
            exp_lines = len(exp_text.splitlines())
            act_lines = len(act_text.splitlines())
            console.print(
                f"  [yellow]DIFFER[/yellow]   {exp_file.name} "
                f"(expected {exp_lines} lines, actual {act_lines} lines)"
            )
