"""Map source fit scores to candidate skill opportunities and honest assessment.

This module does three things that were previously separate or absent:

  1. Skill opportunity mapping  — which skill types this source can support,
     with confidence and timing signals.

  2. Tool candidate detection   — cases where the source describes capabilities
     that require live execution (API calls, stateful ops, data pipelines) that
     a static skill cannot provide. These are surfaced as ToolCandidate objects
     so the user can decide to build a tool instead of (or alongside) a skill.

  3. Honest assessment          — a SourceAssessment that names specific
     limitations, better alternatives, stability warnings, and a plain-language
     verdict. This flows into SKILL.md caveats, extraction-report.md, and the
     CLI post-build verdict. It is never suppressed even when build proceeds.

Swap-candidate criteria:
  Replace the heuristic skill/tool classification with an LLM call when:
  - False-positive rate on tool-vs-skill detection exceeds 20% on a curated
    eval set (i.e. the heuristics are misfiring on real-world URLs).
  - A model with reliable structured-output support is available at low cost,
    making LLM-based classification cheaper than maintaining these heuristics.
  The interface (map_opportunities / map_opportunities_multi) is the stable
  contract; swap the implementation behind it.
"""

from __future__ import annotations

import re

from lsd.models import (
    OpportunityMap,
    SkillCandidate,
    SourceAssessment,
    SourceEntry,
    SourceFit,
    ToolCandidate,
)


# ---------------------------------------------------------------------------
# URL-pattern signals for tool detection
# ---------------------------------------------------------------------------

# Sources whose primary purpose is to describe callable APIs — the agent
# can learn the API semantics from a skill, but cannot call it without a tool.
_API_REFERENCE_PATTERNS = [
    r"api\.", r"/api/", r"/reference/", r"/openapi", r"swagger",
    r"graphql", r"/rest/", r"developers\.", r"developer\.",
]

# Sources describing data pipelines, ETL, scheduled jobs, or batch processes
_PIPELINE_PATTERNS = [
    r"airflow", r"prefect", r"dagster", r"dbt", r"pipeline",
    r"etl", r"batch", r"cron", r"scheduled", r"data-engineering",
]

# Sources for interactive dashboards and apps — visual only, not encodable as rules
_APP_ONLY_PATTERNS = [
    r"app\.", r"dashboard\.", r"console\.", r"studio\.",
    r"figma\.com", r"miro\.com", r"airtable\.com",
]

# Sources that are pure changelogs / release notes — high instability, low fit
_CHANGELOG_PATTERNS = [
    r"changelog", r"release.note", r"releases", r"what.s.new",
    r"version \d+\.\d+", r"breaking.change",
]

# Sources that are marketing/landing pages — no actionable content
_MARKETING_PATTERNS = [
    r"pricing", r"landing", r"signup", r"sign-up", r"features?$",
    r"product$", r"solutions?$", r"enterprise$",
]


def _matches_any(url: str, patterns: list[str]) -> bool:
    url_lower = url.lower()
    return any(re.search(p, url_lower) for p in patterns)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def map_opportunities(fit: SourceFit, url: str) -> OpportunityMap:
    """Produce an OpportunityMap (skill candidates + assessment) from a SourceFit."""
    candidates: list[SkillCandidate] = []
    tool_candidates: list[ToolCandidate] = []
    limitations: list[str] = []
    better_alternatives: list[str] = []
    stability_warning = ""
    breadth_warning = ""
    rebuild_cadence = ""

    url_lower = url.lower()
    is_repo = any(p in url_lower for p in ["github.com", "gitlab.com"])
    is_api_ref = _matches_any(url, _API_REFERENCE_PATTERNS)
    is_pipeline = _matches_any(url, _PIPELINE_PATTERNS)
    is_app_only = _matches_any(url, _APP_ONLY_PATTERNS)
    is_changelog = _matches_any(url, _CHANGELOG_PATTERNS)
    is_marketing = _matches_any(url, _MARKETING_PATTERNS)

    # ------------------------------------------------------------------ #
    # Tool candidate detection — must run before skill candidates so the
    # verdict logic can see whether tool_candidates is non-empty
    # ------------------------------------------------------------------ #

    if is_api_ref:
        tool_candidates.append(ToolCandidate(
            tool_type="function_tool",
            description=(
                "Expose the described API endpoints as callable agent tools, "
                "so the agent can execute live requests rather than only knowing semantics."
            ),
            why_not_skill=(
                "A skill can teach an agent the API's semantics (endpoints, params, "
                "response shapes) but cannot make live HTTP calls. The agent still "
                "needs a function tool or MCP server to actually call the API."
            ),
            effort="medium",
            reference_url="https://modelcontextprotocol.io",
        ))
        tool_candidates.append(ToolCandidate(
            tool_type="mcp_server",
            description="Expose the API as an MCP server for any MCP-compatible agent.",
            why_not_skill="MCP server enables live execution; a skill only encodes knowledge.",
            effort="high",
            reference_url="https://modelcontextprotocol.io/quickstart/server",
        ))
        limitations.append(
            "This source describes an API. The compiled skill teaches endpoint semantics "
            "but cannot make live calls. For actual API execution, build a function tool "
            "or MCP server alongside this skill."
        )
        better_alternatives.append(
            "Build an MCP server (modelcontextprotocol.io) or function tool definition "
            "so the agent can call the API directly, not just know about it."
        )

    if is_pipeline:
        tool_candidates.append(ToolCandidate(
            tool_type="data_pipeline",
            description="Implement the described pipeline as executable code, not a skill.",
            why_not_skill=(
                "Data pipelines require stateful execution, scheduling, and I/O that "
                "a skill cannot provide. A skill can describe the pipeline but not run it."
            ),
            effort="high",
            reference_url="",
        ))
        limitations.append(
            "This source describes a data pipeline or ETL process. The skill can explain "
            "the architecture but cannot execute it. Actual pipeline execution requires code."
        )

    if is_app_only:
        limitations.append(
            "This source is a web app or dashboard. Its value is interactive; a skill "
            "can capture its concepts but not reproduce the visual or stateful experience."
        )
        better_alternatives.append(
            "Use PixelRAG or visual-first ingestion to capture UI layout and interaction "
            "patterns, then supplement with a tool integration for live data access."
        )

    # ------------------------------------------------------------------ #
    # Stability warning
    # ------------------------------------------------------------------ #

    if is_changelog or fit.stability == "low":
        stability_warning = (
            "This source changes frequently (changelog, release notes, or versioned content). "
            "The skill will become stale quickly."
        )
        rebuild_cadence = "on each new release"
        limitations.append(
            "Source stability is low — this content is updated with each software release. "
            "Run `lsd check` before each use and rebuild when the hash changes."
        )
        better_alternatives.append(
            "Build from a stable architecture or concept doc rather than the changelog. "
            "Use the changelog as a trigger for rebuilds, not as the primary source."
        )

    # ------------------------------------------------------------------ #
    # Breadth warning — source covers too much for one skill
    # ------------------------------------------------------------------ #

    highs = sum([
        fit.rule_density == "high",
        fit.procedure_density == "high",
        fit.example_density == "high",
    ])
    if highs >= 2 and fit.specificity != "high":
        breadth_warning = (
            "This source supports multiple skill types. This build targets the "
            "primary type; consider running additional builds for the others."
        )
        limitations.append(
            "The source is broad enough to support multiple skills. "
            "This build covers the primary skill type. "
            "See skill-opportunities.md for secondary build opportunities."
        )

    # ------------------------------------------------------------------ #
    # Marketing / pure informational — low signal, often better to defer
    # ------------------------------------------------------------------ #

    if is_marketing:
        limitations.append(
            "This appears to be a marketing or landing page. "
            "It describes features rather than how to use them. "
            "A how-to guide, tutorial, or docs page would produce a stronger skill."
        )
        better_alternatives.append(
            "Use the product's documentation or tutorial pages instead of the marketing site."
        )

    # ------------------------------------------------------------------ #
    # Skill candidates — same as before, plus is_api_ref generates a
    # 'semantic_reference' candidate (skill alongside the tool)
    # ------------------------------------------------------------------ #

    if fit.rule_density == "high":
        candidates.append(SkillCandidate(
            type="reviewer",
            confidence="high",
            build_timing="now",
            why_fit="High rule density maps directly to a reviewer checklist.",
        ))
    if fit.rule_density in ("high", "medium") and fit.example_density in ("high", "medium"):
        candidates.append(SkillCandidate(
            type="rewriter",
            confidence="medium",
            build_timing="now",
            why_fit="Rules and examples together support rewrite targets.",
        ))
    if fit.procedure_density == "high":
        candidates.append(SkillCandidate(
            type="workflow_coach" if not is_repo else "integration_planner",
            confidence="high",
            build_timing="now",
            why_fit="High procedure density supports a guided workflow skill.",
            needed_extras=["deployment target"] if is_repo else [],
        ))
    if is_repo and fit.composability == "high":
        candidates.append(SkillCandidate(
            type="ingestion_advisor",
            confidence="high",
            build_timing="now",
            why_fit="Repository page with visual signals; good for ingestion routing guidance.",
        ))
    if is_api_ref:
        candidates.append(SkillCandidate(
            type="semantic_reference",
            confidence="medium",
            build_timing="now",
            why_fit=(
                "API reference pages make good semantic skills — the agent learns "
                "endpoint names, params, and response shapes. Pair with a function "
                "tool for live execution."
            ),
            needed_extras=["function tool or MCP server for live calls"],
        ))

    # Reference companion — always a lower-priority fallback
    candidates.append(SkillCandidate(
        type="reference_companion",
        confidence="medium" if fit.overall_fit != "low" else "low",
        build_timing="later" if fit.overall_fit != "low" else "defer",
        why_fit="Any content-rich page can support a reference companion skill.",
        needed_extras=["cross-links to related pages"],
    ))

    # ------------------------------------------------------------------ #
    # Recommended action and verdict
    # ------------------------------------------------------------------ #

    high_now = [c for c in candidates if c.confidence == "high" and c.build_timing == "now"]

    # Defer: genuinely unsuitable (marketing, no content signal, app-only with no fit)
    if is_marketing and fit.overall_fit == "low":
        action = "defer"
        recommended_type = "none"
        verdict = "poor"
        assessment_summary = (
            "This source is not suitable for skill-building. "
            "It describes features without actionable content. "
            "Use a docs or tutorial page instead."
        )
    # Tool problem: primary value is live execution, not knowledge encoding
    elif tool_candidates and fit.overall_fit == "low":
        action = "build_with_caveats"
        recommended_type = tool_candidates[0].tool_type
        verdict = "tool_problem"
        assessment_summary = (
            "This source primarily describes executable capabilities. "
            "A skill can encode the semantics but the real value requires a tool. "
            "Consider building a tool instead of, or alongside, the skill."
        )
    # Build with caveats: source has limitations that need surfacing
    elif limitations or stability_warning or tool_candidates:
        if len(high_now) >= 2:
            action = "build_multiple_skills"
        elif high_now:
            action = "build_with_caveats"
        else:
            action = "build_with_caveats"
        recommended_type = high_now[0].type if high_now else (candidates[0].type if candidates else "reference_companion")
        verdict = "partial" if tool_candidates or stability_warning else "good"
        assessment_summary = (
            limitations[0] if limitations else stability_warning
        )
    elif len(high_now) >= 2:
        action = "build_multiple_skills"
        recommended_type = high_now[0].type
        verdict = "good"
        assessment_summary = f"Strong source: supports {len(high_now)} high-confidence skill types."
    elif high_now:
        action = "build_one_skill"
        recommended_type = high_now[0].type
        verdict = "good"
        assessment_summary = f"Good source for a {recommended_type.replace('_', ' ')} skill."
    elif candidates:
        action = "build_one_skill"
        recommended_type = candidates[0].type
        verdict = "partial"
        assessment_summary = "Moderate source fit. Review the generated skill before use."
    else:
        action = "defer"
        recommended_type = "none"
        verdict = "poor"
        assessment_summary = "No strong skill signals found. Consider a different source."

    assessment = SourceAssessment(
        skill_fit_verdict=verdict,  # type: ignore[arg-type]
        summary=assessment_summary,
        limitations=limitations,
        better_alternatives=better_alternatives,
        tool_candidates=tool_candidates,
        stability_warning=stability_warning,
        breadth_warning=breadth_warning,
        recommended_rebuild_cadence=rebuild_cadence,
    )

    return OpportunityMap(
        recommended_action=action,
        recommended_skill_type=recommended_type,
        candidates=candidates,
        assessment=assessment,
        tool_candidates=tool_candidates,
    )


def map_opportunities_multi(sources: list[SourceEntry]) -> OpportunityMap:
    """Merge opportunity maps across multiple sources.

    Takes the union of all per-source candidates and tool_candidates,
    deduplicating by type. Per-source assessments are merged: all
    limitations and better_alternatives are collected; the most severe
    verdict wins.

    Swap-candidate criteria: replace with LLM-based cross-source synthesis
    when heuristic merging degrades on multi-source eval cases, or when an
    LLM call is already being made for the compiler pass.
    """
    all_candidates: list[SkillCandidate] = []
    all_tool_candidates: list[ToolCandidate] = []
    seen_skill_types: set[str] = set()
    seen_tool_types: set[str] = set()
    all_limitations: list[str] = []
    all_alternatives: list[str] = []
    all_stability_warnings: list[str] = []
    verdict_priority = {"tool_problem": 0, "poor": 1, "partial": 2, "good": 3}
    worst_verdict = "good"

    for entry in sources:
        per_source = entry.opportunity_map or map_opportunities(entry.fit, entry.url)
        for c in per_source.candidates:
            if c.type not in seen_skill_types:
                seen_skill_types.add(c.type)
                all_candidates.append(c)
        for tc in per_source.tool_candidates:
            if tc.tool_type not in seen_tool_types:
                seen_tool_types.add(tc.tool_type)
                all_tool_candidates.append(tc)
        if per_source.assessment:
            a = per_source.assessment
            all_limitations.extend(
                f"[Source {entry.index}] {lim}" for lim in a.limitations
            )
            all_alternatives.extend(a.better_alternatives)
            if a.stability_warning:
                all_stability_warnings.append(
                    f"[Source {entry.index}] {a.stability_warning}"
                )
            if verdict_priority.get(a.skill_fit_verdict, 3) < verdict_priority.get(worst_verdict, 3):
                worst_verdict = a.skill_fit_verdict

    high_now = [c for c in all_candidates if c.confidence == "high" and c.build_timing == "now"]

    if not all_candidates:
        action = "defer"
        recommended_type = "none"
    elif all_tool_candidates and worst_verdict == "tool_problem":
        action = "build_with_caveats"
        recommended_type = all_tool_candidates[0].tool_type
    elif all_limitations or all_stability_warnings or all_tool_candidates:
        action = "build_with_caveats" if len(high_now) <= 1 else "build_multiple_skills"
        recommended_type = high_now[0].type if high_now else all_candidates[0].type
    elif len(high_now) >= 2:
        action = "build_multiple_skills"
        recommended_type = high_now[0].type
    else:
        action = "build_one_skill"
        recommended_type = high_now[0].type if high_now else all_candidates[0].type

    combined_summary = (
        all_limitations[0] if all_limitations
        else all_stability_warnings[0] if all_stability_warnings
        else f"Multi-source build: {len(all_candidates)} skill types detected."
    )

    assessment = SourceAssessment(
        skill_fit_verdict=worst_verdict,  # type: ignore[arg-type]
        summary=combined_summary,
        limitations=all_limitations,
        better_alternatives=list(dict.fromkeys(all_alternatives)),  # deduplicate, preserve order
        tool_candidates=all_tool_candidates,
        stability_warning="\n".join(all_stability_warnings),
        recommended_rebuild_cadence="on each source update" if all_stability_warnings else "",
    )

    return OpportunityMap(
        recommended_action=action,
        recommended_skill_type=recommended_type,
        candidates=all_candidates,
        assessment=assessment,
        tool_candidates=all_tool_candidates,
    )
