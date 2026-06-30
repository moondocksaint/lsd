"""Top-level build pipeline.

Orchestrates: fetch → classify → route → ingest → map → compile → write.
This is what the CLI calls. It can also be called programmatically.
"""

from __future__ import annotations

from pathlib import Path

from lsd.backends import TextBackend, get_visual_backend
from lsd.classifier import classify
from lsd.fetcher import fetch
from lsd.models import BuildContext, IngestionMode, IngestionResult
from lsd.opportunity_mapper import map_opportunities
from lsd.router import route
from lsd.writer import write_package


def build(
    url: str,
    output_dir: Path,
    mode_override: IngestionMode | None = None,
) -> Path:
    """Run the full LSD build pipeline for a URL.

    Args:
        url: The URL to build a skill from.
        output_dir: Where to write the skill package.
        mode_override: Force a specific ingestion mode.

    Returns:
        The path to the written package directory.
    """
    # 1. Fetch
    fetch_result = fetch(url)

    # 2. Classify
    source_fit = classify(fetch_result)

    # 3. Route
    visual_backend = get_visual_backend()
    visual_available = visual_backend is not None
    mode, routing_notes = route(
        fetch_result, source_fit, visual_available, override=mode_override
    )

    # 4. Ingest visual (if applicable)
    visual_result = None
    if mode in ("hybrid", "visual-first") and visual_backend is not None:
        visual_dir = str(output_dir / "visual")
        visual_result = visual_backend.render(url, visual_dir)

    ingestion = IngestionResult(
        fetch=fetch_result,
        visual=visual_result,
        mode=mode,
        routing_notes=routing_notes,
    )

    # 5. Map opportunities
    opportunity_map = map_opportunities(source_fit, fetch_result.canonical_url)

    # 6. Build context
    ctx = BuildContext(
        ingestion=ingestion,
        source_fit=source_fit,
        opportunity_map=opportunity_map,
        output_dir=output_dir,
    )

    # 7. Write package
    return write_package(ctx)
