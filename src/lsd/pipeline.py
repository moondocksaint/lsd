"""Top-level build pipeline.

Orchestrates: fetch → classify → route → ingest → map → compile → write.

Ponytail fixes:
  - Routing dataclass removed: it was a single-caller bag of five fields
    unpacked immediately in build(). prepare() now returns a plain tuple.
  - estimate_tokens / combined_token_estimate inlined: both were one-liners
    that didn't justify named functions in retrieval/naive.py.
  - NaiveRetrievalBackend truncation flag is propagated via RetrievalIndex.was_truncated.

Pre-release fix:
  - _CHARS_PER_TOKEN moved to lsd.utils (was duplicated here and in retrieval/naive.py).
"""

from __future__ import annotations

import logging
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
from lsd.utils import CHARS_PER_TOKEN
from lsd.writer import write_package

log = logging.getLogger(__name__)

DEFAULT_TOKEN_THRESHOLD = 50_000


def prepare(
    url: str, mode_override: IngestionMode | None = None
) -> tuple[FetchResult, SourceFit, IngestionBackend | None, IngestionMode, str]:
    """Fetch → classify → route. Returns (fetch, fit, visual_backend, mode, notes)."""
    fetch_result = fetch(url)
    source_fit = classify(fetch_result)
    visual_backend = get_visual_backend()
    mode, routing_notes = route(
        fetch_result, source_fit, visual_backend is not None, override=mode_override
    )
    return fetch_result, source_fit, visual_backend, mode, routing_notes


def build(
    url: str,
    output_dir: Path,
    mode_override: IngestionMode | None = None,
    routing: tuple | None = None,
) -> Path:
    if routing is None:
        routing = prepare(url, mode_override)

    fetch_result, source_fit, visual_backend, mode, routing_notes = routing

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
    estimated_tokens = int(len(fetch_result.text) / CHARS_PER_TOKEN)

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

    def _process_one(idx_url: tuple[int, str]) -> SourceEntry:
        idx, url = idx_url
        fetch_result, source_fit, _backend, ing_mode, _notes = prepare(url, mode_override)
        norm = normalise(fetch_result)
        opp = map_opportunities(source_fit, fetch_result.canonical_url)
        return SourceEntry(
            url=url,
            fetch_result=fetch_result,
            fit=source_fit,
            source_type=fetch_result.source_type,
            normalised=norm,
            ingestion_mode=ing_mode,
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

    # ponytail: inlined from retrieval/naive.py — both were int(len/3.5) one-liners
    estimated_tokens = int(sum(len(s.text) for s in indexed) / CHARS_PER_TOKEN)
    if estimated_tokens > token_threshold:
        log.warning(
            "Combined sources are ~%d estimated tokens (threshold: %d). "
            "The retrieval backend will truncate to the budget.",
            estimated_tokens, token_threshold,
        )

    ret_backend = get_retrieval_backend(retrieval_backend_name)
    retrieval_index = ret_backend.index(indexed)

    conflict_report = detect_conflicts(entries)
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
