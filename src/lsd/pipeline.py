"""Top-level build pipeline.

Orchestrates: fetch → classify → route → ingest → map → compile → write.

Design notes:
  - ``prepare()`` returns a plain 5-tuple (there is no ``Routing`` dataclass);
    ``build()`` and ``build_multi()`` unpack it directly.
  - Token-budget math lives in ``lsd.utils`` (``estimate_tokens`` /
    ``combined_token_estimate``) so the single-source and multi-source paths,
    the retrieval backend, and the tests all share one implementation.
  - ``NaiveRetrievalBackend`` propagates its truncation flag via
    ``RetrievalIndex.was_truncated`` so the writer/CLI can surface it.
  - Cross-module dependencies are imported at module scope (not inside
    ``build_multi``); there is no circular-import reason for them to be local,
    and module-scope keeps the pipeline's dependency surface visible.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from lsd.backends import get_visual_backend
from lsd.backends.base import IngestionBackend
from lsd.classifier import classify
from lsd.conflict_detector import detect_conflicts
from lsd.fetcher import fetch
from lsd.models import (
    BuildContext,
    FetchResult,
    IndexedSource,
    IngestionMode,
    IngestionResult,
    MultiSourceBuildContext,
    SourceEntry,
    SourceFit,
)
from lsd.normaliser import normalise
from lsd.opportunity_mapper import map_opportunities, map_opportunities_multi
from lsd.retrieval import get_retrieval_backend
from lsd.router import route
from lsd.utils import combined_token_estimate, estimate_tokens
from lsd.writer import write_package

log = logging.getLogger(__name__)

# ponytail: reads LSD_TOKEN_THRESHOLD env var; default unchanged when unset
DEFAULT_TOKEN_THRESHOLD: int = int(os.environ.get("LSD_TOKEN_THRESHOLD", "50000"))


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
    routing: tuple[FetchResult, SourceFit, IngestionBackend | None, IngestionMode, str] | None = None,
    skill_license: str | None = None,
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
    estimated_tokens = estimate_tokens(fetch_result.text)

    ctx = BuildContext(
        ingestion=ingestion,
        source_fit=source_fit,
        opportunity_map=opportunity_map,
        output_dir=output_dir,
        estimated_tokens=estimated_tokens,
        skill_license=skill_license,
    )

    return write_package(ctx)


def build_multi(
    urls: list[str],
    output_dir: Path,
    mode_override: IngestionMode | None = None,
    retrieval_backend_name: str | None = None,
    token_threshold: int = DEFAULT_TOKEN_THRESHOLD,
) -> MultiSourceBuildContext:
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
