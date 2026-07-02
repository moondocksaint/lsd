"""Top-level build pipeline.

Orchestrates: fetch → classify → route → ingest → map → compile → write.

Audit fixes (v0.5):
  - BuildContext no longer carries builder_version (removed field); lsd_version
    is imported from __init__ directly by compiler.py and writer.py.
  - SourceEntry.opportunity_map is now populated in _process_one() so
    per-source opportunity data is not discarded before write_multi_package().
  - estimated_tokens is stored in MultiSourceBuildContext so writer and
    CLI can surface it without re-computing.
  - NaiveRetrievalBackend truncation flag is propagated via RetrievalIndex.was_truncated.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from lsd.backends import get_visual_backend
from lsd.backends.base import IngestionBackend
from lsd.classifier import classify
from lsd.fetcher import fetch
from lsd.models import (
    BuildContext,
    FetchResult,
    IngestionMode,
    IngestionResult,
    MultiSourceBuildContext,
    SourceEntry,
    SourceFit,
)
from lsd.opportunity_mapper import map_opportunities
from lsd.router import route
from lsd.writer import write_package

log = logging.getLogger(__name__)

DEFAULT_TOKEN_THRESHOLD = 50_000


@dataclass
class Routing:
    """Results of the fetch → classify → route phase."""
    fetch: FetchResult
    source_fit: SourceFit
    visual_backend: IngestionBackend | None
    mode: IngestionMode
    routing_notes: str


def prepare(url: str, mode_override: IngestionMode | None = None) -> Routing:
    fetch_result = fetch(url)
    source_fit = classify(fetch_result)
    visual_backend = get_visual_backend()
    mode, routing_notes = route(
        fetch_result, source_fit, visual_backend is not None, override=mode_override
    )
    return Routing(fetch_result, source_fit, visual_backend, mode, routing_notes)


def build(
    url: str,
    output_dir: Path,
    mode_override: IngestionMode | None = None,
    routing: Routing | None = None,
) -> Path:
    if routing is None:
        routing = prepare(url, mode_override)

    fetch_result = routing.fetch
    source_fit = routing.source_fit
    visual_backend = routing.visual_backend
    mode = routing.mode
    routing_notes = routing.routing_notes

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

    opportunity_map = map_opportunities(source_fit, fetch_result.canonical_url)

    from lsd.retrieval.naive import estimate_tokens
    estimated_tokens = estimate_tokens(fetch_result.text)

    ctx = BuildContext(
        ingestion=ingestion,
        source_fit=source_fit,
        opportunity_map=opportunity_map,
        output_dir=output_dir,
        estimated_tokens=estimated_tokens,
    )

    return write_package(ctx)


def build_multi(
    urls: list[str],
    output_dir: Path,
    mode_override: IngestionMode | None = None,
    retrieval_backend_name: str | None = None,
    token_threshold: int = DEFAULT_TOKEN_THRESHOLD,
) -> MultiSourceBuildContext:
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from lsd.conflict_detector import detect_conflicts
    from lsd.models import IndexedSource
    from lsd.normaliser import normalise
    from lsd.opportunity_mapper import map_opportunities_multi
    from lsd.retrieval import get_retrieval_backend
    from lsd.retrieval.naive import combined_token_estimate

    def _process_one(idx_url: tuple[int, str]) -> SourceEntry:
        idx, url = idx_url
        routing = prepare(url, mode_override)
        norm = normalise(routing.fetch)
        # Audit fix: compute and preserve per-source opportunity_map
        opp = map_opportunities(routing.source_fit, routing.fetch.canonical_url)
        return SourceEntry(
            url=url,
            fetch_result=routing.fetch,
            fit=routing.source_fit,
            source_type=routing.fetch.source_type,
            normalised=norm,
            ingestion_mode=routing.mode,
            index=idx,
            opportunity_map=opp,
        )

    entries: list[SourceEntry] = []
    with ThreadPoolExecutor(max_workers=min(len(urls), 5)) as pool:
        futures = {pool.submit(_process_one, (i + 1, url)): url for i, url in enumerate(urls)}
        for future in as_completed(futures):
            entries.append(future.result())

    entries.sort(key=lambda e: e.index)

    indexed = [
        IndexedSource(
            index=e.index, url=e.url,
            source_file=f"source-{e.index}.md",
            text=e.normalised,
        )
        for e in entries
    ]
    # Audit fix: store estimated_tokens in context
    estimated_tokens = combined_token_estimate(indexed)
    if estimated_tokens > token_threshold:
        log.warning(
            "Combined sources are ~%d estimated tokens (threshold: %d). "
            "The retrieval backend will truncate to the budget.",
            estimated_tokens, token_threshold,
        )

    ret_backend = get_retrieval_backend(retrieval_backend_name)
    retrieval_index = ret_backend.index(indexed)

    conflict_report = detect_conflicts(entries)
    # Audit fix: map_opportunities_multi now reads per-source opportunity_map
    # from SourceEntry instead of discarding it
    combined_opportunities = map_opportunities_multi(entries)

    ctx = MultiSourceBuildContext(
        sources=entries,
        output_dir=output_dir,
        conflict_report=conflict_report,
        combined_opportunities=combined_opportunities,
        estimated_tokens=estimated_tokens,
    )
    ctx._retrieval_backend = ret_backend       # type: ignore[attr-defined]
    ctx._retrieval_index = retrieval_index     # type: ignore[attr-defined]
    return ctx
