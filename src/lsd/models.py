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
