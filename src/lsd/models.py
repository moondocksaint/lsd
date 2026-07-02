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
from typing import Any, Literal


SourceType = Literal["html", "pdf", "image", "google_doc", "social", "gated", "unsupported"]

SkillType = Literal[
    "reviewer",
    "rewriter",
    "reference_companion",
    "semantic_reference",
    "data_pipeline",
    "mcp_server",
    "function_tool",
    "api_wrapper",
    "workflow_coach",
    "integration_planner",
    "ingestion_advisor",
]



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
    type: SkillType
    confidence: Literal["high", "medium", "low"]
    build_timing: Literal["now", "later", "defer"]
    why_fit: str
    needed_extras: list[str] = field(default_factory=list)


@dataclass
class ToolCandidate:
    """A tool (non-skill) opportunity detected from the source.

    Captures cases where the source describes capabilities that require
    live execution — API calls, data fetches, stateful operations — that
    a static skill cannot provide. Used in honest assessment output.

    Tool types:
      mcp_server    — Model Context Protocol server; exposes tools to agents
      function_tool — OpenAI/Anthropic function/tool definition
      api_wrapper   — Thin HTTP client the agent can call via bash/code
      data_pipeline — ETL or batch process, not suitable for skill encoding

    Derived properties (.type, .confidence, .why_fit, .build_timing) provide
    a SkillCandidate-compatible read surface for tables and metadata — so the
    writer and CLI can render tool and skill candidates uniformly without
    branching. The compiler uses the richer fields (.tool_type, .description,
    .why_not_skill, .effort) for SKILL.md generation.
    """
    tool_type: Literal["mcp_server", "function_tool", "api_wrapper", "data_pipeline"]
    description: str                # one sentence: what the tool would do
    why_not_skill: str              # why a skill is insufficient
    effort: Literal["low", "medium", "high"]   # relative build effort
    reference_url: str = ""        # relevant SDK/framework docs

    # ------------------------------------------------------------------
    # Derived properties — SkillCandidate-compatible read surface
    # ------------------------------------------------------------------

    @property
    def type(self) -> str:
        """Human-readable tool type label (same shape as SkillCandidate.type)."""
        return self.tool_type.replace("_", " ").title()

    @property
    def confidence(self) -> str:
        """Confidence derived from build effort: low effort → high confidence."""
        return {"low": "high", "medium": "medium", "high": "low"}.get(self.effort, "medium")

    @property
    def why_fit(self) -> str:
        """Why this tool fits — maps why_not_skill to a positive framing."""
        return self.description

    @property
    def build_timing(self) -> str:
        """Build timing derived from effort: low → now, medium → later, high → later."""
        return "now" if self.effort == "low" else "later"

    @property
    def needed_extras(self) -> list[str]:
        """Compatibility shim — SkillCandidate has needed_extras; return reference if set."""
        return [self.reference_url] if self.reference_url else []


@dataclass
class SourceAssessment:
    """Honest assessment of a source's suitability for skill-building.

    Produced by the opportunity mapper and threaded through to every
    generated artifact: SKILL.md caveats, extraction-report.md Limitations
    section, and the CLI post-build verdict.

    Limitations list: each entry is one actionable sentence describing
    a specific constraint the agent using the skill will encounter.

    Better_alternatives list: each entry describes something the user
    could do instead of (or in addition to) building a skill.

    Tool candidates are stored on OpportunityMap.tool_candidates (the
    canonical list). SourceAssessment carries only the scalar assessment
    fields so there is a single source of truth for tool candidate data.
    """
    skill_fit_verdict: Literal["good", "partial", "poor", "tool_problem"]
    summary: str                   # one sentence; shown in CLI verdict
    limitations: list[str] = field(default_factory=list)
    better_alternatives: list[str] = field(default_factory=list)
    stability_warning: str = ""    # non-empty if source changes frequently
    breadth_warning: str = ""      # non-empty if source is too broad for one skill
    recommended_rebuild_cadence: str = ""  # e.g. "monthly", "on each release"


@dataclass
class OpportunityMap:
    """Ranked skill opportunities and honest assessment for this source.

    recommended_action values:
      build_one_skill      — single strong skill candidate; build now
      build_multiple_skills — two or more high-confidence candidates; build all
      build_with_caveats   — build, but important limitations exist; surface them
      defer                — source is genuinely unsuitable; do not build
    """
    recommended_action: Literal[
        "build_one_skill",
        "build_multiple_skills",
        "build_with_caveats",
        "defer",
    ]
    recommended_skill_type: str
    candidates: list[SkillCandidate] = field(default_factory=list)
    assessment: SourceAssessment | None = None    # always set by map_opportunities()
    tool_candidates: list[ToolCandidate] = field(default_factory=list)


@dataclass
class BuildContext:
    """Everything the compiler and writer need."""
    ingestion: IngestionResult
    source_fit: SourceFit
    opportunity_map: OpportunityMap
    output_dir: Path
    generated_at: str = ""          # ISO 8601, set by writer
    estimated_tokens: int = 0       # set by pipeline if available
    skill_license: str | None = None  # ponytail: None = omit license field; set via --license flag


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
    opportunity_map: OpportunityMap | None = None   # per-source; set by build_multi


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
    shared_vocabulary: dict[int, list[str]] = field(default_factory=dict)
    # shared_vocabulary: source_pair_key (min_idx * 100 + max_idx) → shared terms
    # Preserved for honest assessment and debugging; not used by conflict logic itself


@dataclass
class MultiSourceBuildContext:
    """Build context for multi-source builds."""
    sources: list[SourceEntry]
    output_dir: Path
    conflict_report: ConflictReport
    combined_opportunities: OpportunityMap
    estimated_tokens: int = 0       # combined token estimate from pipeline
    skill_license: str | None = None  # ponytail: None = omit license field; set via --license flag


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
    was_truncated: bool = False      # set True if any retrieve() call hit the budget
    _state: Any = field(default=None, repr=False)  # backend-specific state (opaque)
