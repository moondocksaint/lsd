"""Map source fit scores to candidate skill opportunities.

This is a heuristic rule-based mapper. It produces a ranked list
of candidate skill types and a recommended first action.

Future: supplement with an LLM call for richer candidate generation.
"""

from __future__ import annotations

from lsd.models import OpportunityMap, SkillCandidate, SourceFit


def map_opportunities(fit: SourceFit, url: str) -> OpportunityMap:
    """Produce an OpportunityMap from a SourceFit."""
    candidates: list[SkillCandidate] = []

    url_lower = url.lower()
    is_repo = any(p in url_lower for p in ["github.com", "gitlab.com"])

    # Reviewer / rewriter — best fit when rule + example density are high
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

    # Workflow / integration — best fit when procedure density is high
    if fit.procedure_density == "high":
        candidates.append(SkillCandidate(
            type="workflow_coach" if not is_repo else "integration_planner",
            confidence="high",
            build_timing="now",
            why_fit="High procedure density supports a guided workflow skill.",
            needed_extras=["deployment target"] if is_repo else [],
        ))

    # Ingestion advisor — best fit for repo pages with visual signals
    if is_repo and fit.composability == "high":
        candidates.append(SkillCandidate(
            type="ingestion_advisor",
            confidence="high",
            build_timing="now",
            why_fit="Repository page with visual signals; good source for ingestion routing guidance.",
        ))

    # Reference companion — always a lower-priority option
    candidates.append(SkillCandidate(
        type="reference_companion",
        confidence="medium",
        build_timing="later",
        why_fit="Any content-rich page can support a reference companion skill.",
        needed_extras=["cross-links to related pages"],
    ))

    # Recommend action
    high_confidence = [c for c in candidates if c.confidence == "high" and c.build_timing == "now"]
    if len(high_confidence) >= 2:
        action = "build_multiple_skills"
        recommended_type = high_confidence[0].type
    elif len(high_confidence) == 1:
        action = "build_one_skill"
        recommended_type = high_confidence[0].type
    elif candidates:
        action = "build_one_skill"
        recommended_type = candidates[0].type
    else:
        action = "defer"
        recommended_type = "unknown"

    return OpportunityMap(
        recommended_action=action,
        recommended_skill_type=recommended_type,
        candidates=candidates,
    )
