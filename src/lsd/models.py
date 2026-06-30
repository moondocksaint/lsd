"""Core data contracts for LSD.

These types are LSD's own — they never leak PixelRAG or any other
backend's types into the rest of the pipeline. Backends translate
into these types; the compiler, classifier, and writer only see these.

This is the seam that makes the fork path clean: swap the backend,
keep everything else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


SourceType = Literal["html", "pdf", "image", "google_doc", "social", "gated", "unsupported"]


@dataclass
class FetchResult:
    """Normalised text artifact from a fetched URL."""
    url: str
    canonical_url: str
    title: str
    text: str                        # normalised markdown text
    html: str                        # raw HTML, kept for hybrid reconciliation
    fetched_at: str                  # ISO 8601
    http_status: int
    word_count: int = 0
    source_type: SourceType = "html"


@dataclass
class VisualResult:
    """Visual artifact from a rendered URL."""
    url: str
    rendered_at: str                 # ISO 8601
    full_screenshot: Path | None
    tiles: list[Path] = field(default_factory=list)
    backend: str = "unknown"         # e.g. "pixelrag", "native"


IngestionMode = Literal["text-first", "hybrid", "visual-first"]


@dataclass
class IngestionResult:
    """Combined result from the ingestion stage."""
    fetch: FetchResult
    visual: VisualResult | None      # None for text-first
    mode: IngestionMode
    routing_notes: str = ""


@dataclass
class SourceFit:
    """Source classification scores."""
    overall_fit: Literal["high", "medium", "low"] = "medium"
    rule_density: Literal["high", "medium", "low"] = "medium"
    procedure_density: Literal["high", "medium", "low"] = "medium"
    example_density: Literal["high", "medium", "low"] = "medium"
    stability: Literal["high", "medium", "low"] = "medium"
    specificity: Literal["high", "medium", "low"] = "medium"
    composability: Literal["high", "medium", "low"] = "medium"
    fit_notes: str = ""


@dataclass
class SkillCandidate:
    """A candidate skill type from the opportunity map."""
    type: str
    confidence: Literal["high", "medium", "low"]
    build_timing: Literal["now", "later", "defer"]
    why_fit: str
    needed_extras: list[str] = field(default_factory=list)


@dataclass
class OpportunityMap:
    """Ranked skill opportunities for this source."""
    recommended_action: Literal[
        "build_one_skill", "build_multiple_skills",
        "opportunity_map_only", "defer"
    ]
    recommended_skill_type: str
    candidates: list[SkillCandidate] = field(default_factory=list)


@dataclass
class BuildContext:
    """Everything the compiler and writer need."""
    ingestion: IngestionResult
    source_fit: SourceFit
    opportunity_map: OpportunityMap
    output_dir: Path
    builder_version: str = "0.1.0"
    generated_at: str = ""          # ISO 8601, set by writer


# ---------------------------------------------------------------------------
# v0.3 — Multi-source types
# ---------------------------------------------------------------------------

@dataclass
class SourceEntry:
    """One source in a multi-source build."""
    url: str
    fetch_result: FetchResult
    fit: SourceFit
    source_type: SourceType          # mirrors FetchResult.source_type
    normalised: str
    ingestion_mode: IngestionMode
    index: int                       # 1-based


@dataclass
class Conflict:
    """A single detected conflict between sources."""
    kind: str                        # "contradiction" | "gap" | "overlap"
    description: str
    source_indices: list[int]        # which sources (1-based) are involved
    severity: str                    # "high" | "medium" | "low"
    suggestion: str                  # how to resolve


@dataclass
class ConflictReport:
    """Result of cross-source conflict analysis."""
    conflicts: list[Conflict]
    summary: str
    has_blocking_conflicts: bool     # True if any severity == "high"


@dataclass
class MultiSourceBuildContext:
    """Build context for multi-source builds."""
    sources: list[SourceEntry]
    output_dir: Path
    conflict_report: ConflictReport
    combined_opportunities: OpportunityMap


# ---------------------------------------------------------------------------
# v0.4 — Retrieval types
# ---------------------------------------------------------------------------

@dataclass
class Passage:
    """A retrieved text chunk with full provenance.

    Provenance is never lost regardless of which RetrievalBackend produced
    the passage — the compiler always cites source_url + char_offset.
    """
    text: str
    source_index: int                # 1-based, matches SourceEntry.index
    source_url: str
    source_file: str                 # e.g. "source-1.md"
    char_offset: int                 # start offset in the normalised source text
    score: float = 0.0               # relevance score; higher = more relevant


@dataclass
class IndexedSource:
    """A source prepared for indexing by a RetrievalBackend."""
    index: int                       # 1-based, matches SourceEntry.index
    url: str
    source_file: str                 # e.g. "source-1.md"
    text: str                        # normalised text to be chunked/embedded


@dataclass
class RetrievalIndex:
    """Opaque handle returned by RetrievalBackend.index().

    The backend owns the internal representation; callers only pass this
    token back to retrieve(). The metadata fields are for logging/debugging.
    """
    backend_name: str
    source_count: int
    total_chars: int
    _state: object = field(default=None, repr=False)  # backend-specific state
