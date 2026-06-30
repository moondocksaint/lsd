"""Top-level build pipeline.

Orchestrates: fetch → classify → route → ingest → map → compile → write.
This is what the CLI calls. It can also be called programmatically.
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

# Token threshold for multi-source builds. When combined estimated tokens
# exceed this value, a warning is emitted and the naive backend truncates.
# Configurable via LSD_TOKEN_THRESHOLD env var or --token-threshold CLI flag.
DEFAULT_TOKEN_THRESHOLD = 50_000


@dataclass
class Routing:
    """Results of the fetch → classify → route phase, reusable by build()."""
    fetch: FetchResult
    source_fit: SourceFit
    visual_backend: IngestionBackend | None
    mode: IngestionMode
    routing_notes: str


def prepare(url: str, mode_override: IngestionMode | None = None) -> Routing:
    """Run fetch → classify → route once and return the combined result.

    This is the network-touching phase. Callers that need the routing
    summary before deciding whether to build can call this, then pass the
    result into build() to avoid a second live fetch.
    """
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
    """Run the full LSD build pipeline for a URL.

    Args:
        url: The URL to build a skill from.
        output_dir: Where to write the skill package.
        mode_override: Force a specific ingestion mode.
        routing: Pre-computed fetch/classify/route result. When provided,
            the live fetch is skipped and these results are reused.

    Returns:
        The path to the written package directory.
    """
    if routing is None:
        routing = prepare(url, mode_override)

    fetch_result = routing.fetch
    source_fit = routing.source_fit
    visual_backend = routing.visual_backend
    mode = routing.mode
    routing_notes = routing.routing_notes

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


def build_multi(
    urls: list[str],
    output_dir: Path,
    mode_override: IngestionMode | None = None,
    retrieval_backend_name: str | None = None,
    token_threshold: int = DEFAULT_TOKEN_THRESHOLD,
) -> MultiSourceBuildContext:
    """Fetch, classify, and analyse multiple sources in parallel.

    Runs up to 5 fetches concurrently, then performs cross-source conflict
    detection, merges opportunity maps, and (v0.4) builds a retrieval index
    for grounded multi-source compilation.

    Swap-candidate criteria for the parallel fetch:
      Replace ThreadPoolExecutor with asyncio when the fetcher gains an
      async interface, or when I/O parallelism needs to exceed 5 workers.

    Args:
        urls:                  List of source URLs to fetch.
        output_dir:            Where to write the skill package.
        mode_override:         Force a specific ingestion mode for all sources.
        retrieval_backend_name: Name of the retrieval backend to use.
                               If None, uses the default from retrieval/__init__.py
                               or LSD_RETRIEVAL_BACKEND env var.
        token_threshold:       Token count at which to warn and truncate.
                               Default: 50,000.

    Returns:
        A MultiSourceBuildContext with per-source entries, conflict report,
        and an attached retrieval index ready for compilation.
    """
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
        return SourceEntry(
            url=url,
            fetch_result=routing.fetch,
            fit=routing.source_fit,
            source_type=routing.fetch.source_type,
            normalised=norm,
            ingestion_mode=routing.mode,
            index=idx,
        )

    entries: list[SourceEntry] = []
    with ThreadPoolExecutor(max_workers=min(len(urls), 5)) as pool:
        futures = {pool.submit(_process_one, (i + 1, url)): url for i, url in enumerate(urls)}
        for future in as_completed(futures):
            entries.append(future.result())

    # Preserve original URL order
    entries.sort(key=lambda e: e.index)

    # Token threshold check
    indexed = [
        IndexedSource(
            index=e.index,
            url=e.url,
            source_file=f"source-{e.index}.md",
            text=e.normalised,
        )
        for e in entries
    ]
    estimated = combined_token_estimate(indexed)
    if estimated > token_threshold:
        log.warning(
            "Combined sources are ~%d estimated tokens (threshold: %d). "
            "The retrieval backend will truncate to the budget. "
            "For better grounding on large corpora, use a RAG backend "
            "(--retrieval-backend bm25 or colbert) once available.",
            estimated,
            token_threshold,
        )

    # Build retrieval index
    ret_backend = get_retrieval_backend(retrieval_backend_name)
    retrieval_index = ret_backend.index(indexed)

    # Cross-source conflict detection
    conflict_report = detect_conflicts(entries)
    combined_opportunities = map_opportunities_multi(entries)

    ctx = MultiSourceBuildContext(
        sources=entries,
        output_dir=output_dir,
        conflict_report=conflict_report,
        combined_opportunities=combined_opportunities,
    )

    # Attach retrieval state as a non-model attribute for the compiler
    # (avoids adding retrieval types to the dataclass contract)
    ctx._retrieval_backend = ret_backend       # type: ignore[attr-defined]
    ctx._retrieval_index = retrieval_index     # type: ignore[attr-defined]

    return ctx
