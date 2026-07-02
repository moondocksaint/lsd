"""Compile a SKILL.md from a BuildContext.

Changes in v0.5 (opportunity + audit pass):
  - _render_template: "Related skills" section from OpportunityMap.candidates
  - _render_template: allowed-tools derived from skill type (not hardcoded)
  - _caveat_block: reads SourceAssessment.limitations and stability_warning
  - _tool_candidates_block: new helper; surfaces ToolCandidate objects in
    the caveats section
  - All other logic unchanged from the previous version.
"""

from __future__ import annotations

import logging
import re

from lsd.llm.base import LLMBackend
from lsd.models import BuildContext, MultiSourceBuildContext, OpportunityMap

log = logging.getLogger(__name__)

_MAX_SOURCE_CHARS = 40_000
_MAX_RETRIEVED_CHARS = 15_000


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compile_skill(
    ctx: BuildContext,
    llm_backend: LLMBackend | None = None,
) -> tuple[str, str | None]:
    backend = llm_backend
    if backend is None:
        try:
            from lsd.llm import get_llm_backend
            backend = get_llm_backend()
        except Exception as exc:
            log.warning("Could not initialise LLM backend (%s); using heuristic fallback.", exc)

    if backend is not None:
        try:
            content = _compile_with_llm(ctx, backend)
            return content, backend.model_id
        except Exception as exc:
            log.warning("LLM compiler failed (%s); falling back to heuristic.", exc)

    return _compile_heuristic(ctx), None


def compile_skill_multi(
    ctx: MultiSourceBuildContext,
    llm_backend: LLMBackend | None = None,
    retrieval_backend=None,
) -> tuple[str, str | None]:
    from lsd.models import IndexedSource
    from lsd.retrieval import get_retrieval_backend

    backend = llm_backend
    if backend is None:
        try:
            from lsd.llm import get_llm_backend
            backend = get_llm_backend()
        except Exception as exc:
            log.warning("Could not initialise LLM backend (%s); using heuristic fallback.", exc)

    ret_backend = retrieval_backend
    if ret_backend is None:
        ret_backend = get_retrieval_backend()

    indexed = [
        IndexedSource(index=e.index, url=e.url,
                      source_file=f"source-{e.index}.md", text=e.normalised)
        for e in ctx.sources
    ]
    try:
        ret_index = ret_backend.index(indexed)
    except Exception as exc:
        log.warning("Retrieval indexing failed (%s); falling back to heuristic.", exc)
        return _compile_heuristic_multi(ctx), None

    if backend is not None:
        try:
            content = _compile_multi_with_llm(ctx, backend, ret_backend, ret_index)
            return content, backend.model_id
        except Exception as exc:
            log.warning("LLM multi-source compiler failed (%s); falling back.", exc)

    return _compile_heuristic_multi(ctx), None


# ---------------------------------------------------------------------------
# LLM paths (unchanged from previous version except skill_type plumbing)
# ---------------------------------------------------------------------------

def _compile_with_llm(ctx: BuildContext, backend: LLMBackend) -> str:
    fetch = ctx.ingestion.fetch
    fit = ctx.source_fit
    opp = ctx.opportunity_map
    source_excerpt = fetch.text[:_MAX_SOURCE_CHARS]
    if len(fetch.text) > _MAX_SOURCE_CHARS:
        source_excerpt += "\n\n[Source truncated for compilation — full text in source.md]"
    skill_type = opp.recommended_skill_type.replace("_", " ")
    fit_summary = (
        f"rule_density={fit.rule_density}, procedure_density={fit.procedure_density}, "
        f"example_density={fit.example_density}, overall_fit={fit.overall_fit}"
    )
    system = (
        "You are a skill compiler for LSD (Link-to-Skill Designer). "
        "Read the source and write three concise, source-specific sections for a reusable AI skill. "
        "Be concrete. No generic boilerplate. Every sentence must be grounded in the source."
    )
    user = f"""Source URL: {fetch.canonical_url}
Source title: {fetch.title}
Skill type to build: {skill_type}
Source fit signals: {fit_summary}

Source content:
---
{source_excerpt}
---

Write exactly three sections (use these exact headings):

## Core principle
[One sentence distilling the source's central, actionable idea. Be specific.]

## Workflow
[3-7 numbered steps from the source's actual procedures or rules.]

## Output format
[3-6 bullet fields for output when this skill is used, specific to {skill_type}.]

Return only the three sections. No preamble."""
    response = backend.complete(system=system, user=user, max_tokens=1024)
    core_principle, workflow, output_format = _parse_llm_sections(response)
    return _render_template(ctx, core_principle, workflow, output_format, model_id=backend.model_id)


def _compile_multi_with_llm(ctx, backend, ret_backend, ret_index) -> str:
    opp = ctx.combined_opportunities
    skill_type = opp.recommended_skill_type.replace("_", " ")
    queries = [
        f"core principle and central idea for {skill_type}",
        f"step-by-step workflow and procedures for {skill_type}",
        f"output format and structure for {skill_type}",
    ]
    all_passages = []
    seen: set[tuple[int, int]] = set()
    for query in queries:
        for p in ret_backend.retrieve(ret_index, query, k=5):
            key = (p.source_index, p.char_offset)
            if key not in seen:
                seen.add(key)
                all_passages.append(p)
    context_parts: list[str] = []
    total_chars = 0
    for p in all_passages:
        if total_chars >= _MAX_RETRIEVED_CHARS:
            break
        marker = f"[Source {p.source_index}: {p.source_url} | {p.source_file} +{p.char_offset}]"
        part = f"{marker}\n{p.text}"
        context_parts.append(part)
        total_chars += len(part)
    grounded_context = "\n\n---\n\n".join(context_parts)
    source_lines = "\n".join(f"  Source {e.index}: {e.url}" for e in ctx.sources)
    conflict_note = ""
    if ctx.conflict_report.has_blocking_conflicts:
        conflict_note = "\n\nIMPORTANT: Sources contain contradictions. Surface them explicitly."
    elif ctx.conflict_report.conflicts:
        conflict_note = f"\n\nNote: {ctx.conflict_report.summary}"
    system = (
        "You are a skill compiler for LSD. Compiling from MULTIPLE sources. "
        "Every claim must cite [Source N]. Surface contradictions, never merge them silently."
    )
    user = f"""Sources ({len(ctx.sources)} total):
{source_lines}

Skill type: {skill_type}{conflict_note}

Retrieved passages:
---
{grounded_context}
---

Write exactly three sections:

## Core principle
[One sentence per source for {skill_type}, citing [Source N].]

## Workflow
[3-7 numbered steps citing [Source N]. Flag conflicts explicitly.]

## Output format
[3-6 bullets for {skill_type} output. Cite sources.]

Return only the three sections."""
    response = backend.complete(system=system, user=user, max_tokens=1500)
    core_principle, workflow, output_format = _parse_llm_sections(response)
    return _render_template_multi(ctx, core_principle, workflow, output_format, model_id=backend.model_id)


# ---------------------------------------------------------------------------
# Template renderers
# ---------------------------------------------------------------------------

def _slugify_name(text: str, max_len: int = 60) -> str:
    s = text.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-")
    return s[:max_len].rstrip("-")


def _allowed_tools_for_skill_type(skill_type: str) -> str:
    """Return a space-separated allowed-tools string appropriate for the skill type.

    Rules (agentskills spec: space-separated tool name patterns):
      reviewer / rewriter / reference_companion / semantic_reference
          → Read only (read documents to review; no writes)
      workflow_coach / integration_planner / ingestion_advisor
          → Read Write Edit Bash (may need to run commands or write output)
      data_pipeline / mcp_server / function_tool / api_wrapper
          → Read Write Bash (tool-building tasks)
      default
          → Read Write Edit
    """
    read_only = {"reviewer", "rewriter", "reference_companion", "semantic_reference"}
    code_tasks = {"data_pipeline", "mcp_server", "function_tool", "api_wrapper"}
    workflow_tasks = {"workflow_coach", "integration_planner", "ingestion_advisor"}
    if skill_type in read_only:
        return "Read"
    if skill_type in code_tasks:
        return "Read Write Bash"
    if skill_type in workflow_tasks:
        return "Read Write Edit Bash"
    return "Read Write Edit"


def _render_template(
    ctx: BuildContext,
    core_principle: str,
    workflow: str,
    output_format: str,
    model_id: str | None = None,
) -> str:
    from lsd import __version__ as lsd_version

    fetch = ctx.ingestion.fetch
    fit = ctx.source_fit
    opp = ctx.opportunity_map
    mode = ctx.ingestion.mode

    skill_type = opp.recommended_skill_type
    skill_type_display = skill_type.replace("_", " ").title()
    raw_name = f"{skill_type}-{_slugify_name(fetch.title)}"
    name = _slugify_name(raw_name)
    allowed_tools = _allowed_tools_for_skill_type(skill_type)
    caveat_block = _caveat_block(mode, model_id, opp)
    related_block = _related_skills_block(opp)
    tool_block = _tool_candidates_block(opp)

    metadata_block = (
        f"  lsd_version: \"{lsd_version}\"\n"
        f"  compiler_model: \"{model_id or 'heuristic'}\"\n"
        f"  source_url: \"{fetch.canonical_url}\"\n"
        f"  generated_at: \"{ctx.generated_at}\"\n"
        f"  skill_type: \"{skill_type}\"\n"
        f"  ingestion_mode: \"{mode}\"\n"
        f"  skill_fit_verdict: \"{opp.assessment.skill_fit_verdict if opp.assessment else 'unknown'}\""
    )

    return f"""---
name: {name}
description: >-
  Use this skill when working with content derived from: {fetch.title}.
  Skill type: {skill_type_display}. Trigger phrases: {skill_type_display.lower()},
  review with {skill_type.replace('_', ' ')}, apply {name}.
license: Apache-2.0
allowed-tools: {allowed_tools}
metadata:
{metadata_block}
---

## Purpose

Compiled by LSD from:
- URL: {fetch.canonical_url}
- Title: {fetch.title}
- Ingestion mode: {mode}
- Skill type: {skill_type_display}

## When to use

{_usage_hints(fit, skill_type)}

## Core principle

{core_principle}

## Workflow

{workflow}

## Output format

{output_format}

## Style rule

Be specific and actionable. Prefer direct language over hedged summaries.

## Caveats

{caveat_block}
{tool_block}
## Related skills

{related_block}

## Source

- Compiled from: {fetch.canonical_url}
- Source fit: {fit.overall_fit} (rule: {fit.rule_density}, procedure: {fit.procedure_density}, example: {fit.example_density})
- Notes: {fit.fit_notes}
"""


def _render_template_multi(
    ctx: MultiSourceBuildContext,
    core_principle: str,
    workflow: str,
    output_format: str,
    model_id: str | None = None,
) -> str:
    from lsd import __version__ as lsd_version

    opp = ctx.combined_opportunities
    skill_type = opp.recommended_skill_type
    skill_type_display = skill_type.replace("_", " ").title()
    name = _slugify_name(f"{skill_type}-multi")
    allowed_tools = _allowed_tools_for_skill_type(skill_type)
    caveat_block = _caveat_block("text-first", model_id, opp)
    related_block = _related_skills_block(opp)
    tool_block = _tool_candidates_block(opp)

    source_list = "\n".join(f"- Source {e.index}: {e.url}" for e in ctx.sources)
    conflict_section = ""
    if ctx.conflict_report.conflicts:
        conflict_section = f"\n## Source conflicts\n\n{ctx.conflict_report.summary}\n\nSee conflicts.md for full details.\n"

    source_urls = " ".join(e.url for e in ctx.sources)
    metadata_block = (
        f"  lsd_version: \"{lsd_version}\"\n"
        f"  compiler_model: \"{model_id or 'heuristic'}\"\n"
        f"  source_count: {len(ctx.sources)}\n"
        f"  source_urls: \"{source_urls[:200]}\"\n"
        f"  skill_type: \"{skill_type}\"\n"
        f"  skill_fit_verdict: \"{opp.assessment.skill_fit_verdict if opp.assessment else 'unknown'}\""
    )

    return f"""---
name: {name}
description: >-
  Multi-source skill for {skill_type_display.lower()} tasks, compiled from
  {len(ctx.sources)} sources. Use when performing {skill_type_display.lower()}
  tasks drawing on multiple reference documents.
license: Apache-2.0
allowed-tools: {allowed_tools}
metadata:
{metadata_block}
---

## Purpose

Compiled by LSD from {len(ctx.sources)} sources:
{source_list}
{conflict_section}
## When to use

{skill_type_display} tasks drawing on multiple reference sources.

## Core principle

{core_principle}

## Workflow

{workflow}

## Output format

{output_format}

## Style rule

Be specific and actionable. Cite sources for every claim ([Source N]).
Surface conflicts rather than silently resolving them.

## Caveats

{caveat_block}
{tool_block}
## Related skills

{related_block}

## Sources

{source_list}
"""


# ---------------------------------------------------------------------------
# Heuristic / offline fallbacks
# ---------------------------------------------------------------------------

def _compile_heuristic(ctx: BuildContext) -> str:
    core = "<!-- TODO: distil the source's central idea into one sentence. -->"
    workflow = (
        "<!-- TODO: expand from the source's procedure signals. -->\n"
        "1. Read the input in full.\n"
        "2. Apply the relevant checks or procedures from the source.\n"
        "3. Produce structured output."
    )
    output_format = (
        "<!-- TODO: define the expected output structure. -->\n"
        "Provide structured output with:\n"
        "- Finding or step name\n- Evidence or rationale\n- Recommended action"
    )
    return _render_template(ctx, core, workflow, output_format, model_id=None)


def _compile_heuristic_multi(ctx: MultiSourceBuildContext) -> str:
    core = "<!-- TODO: distil central ideas from each source. -->"
    workflow = (
        "<!-- TODO: synthesise procedures from all sources. -->\n"
        "1. Read all source files.\n"
        "2. Apply relevant checks or procedures.\n"
        "3. Produce structured output with source citations."
    )
    output_format = (
        "<!-- TODO: define the expected output structure. -->\n"
        "Provide structured output with:\n"
        "- Finding or step name [Source N]\n- Evidence\n- Recommended action"
    )
    return _render_template_multi(ctx, core, workflow, output_format, model_id=None)


# ---------------------------------------------------------------------------
# Section helpers
# ---------------------------------------------------------------------------

def _caveat_block(mode: str, model_id: str | None, opp: OpportunityMap) -> str:
    """Build the caveats section from assessment + ingestion mode."""
    lines: list[str] = []
    lines.append(
        "This skill was auto-generated by LSD and should be reviewed before use."
    )
    if model_id:
        lines.append(f"Core sections were compiled by `{model_id}`.")
    else:
        lines.append(
            "Core sections contain placeholder text — configure an LLM provider "
            "via LSD_LLM_PROVIDER + API key env vars for full compilation."
        )

    # Assessment-derived limitations
    if opp.assessment:
        a = opp.assessment
        if a.stability_warning:
            lines.append(f"\n**Source stability:** {a.stability_warning}")
            if a.recommended_rebuild_cadence:
                lines.append(f"Recommended rebuild cadence: {a.recommended_rebuild_cadence}.")
        if a.breadth_warning:
            lines.append(f"\n**Scope:** {a.breadth_warning}")
        for lim in a.limitations:
            lines.append(f"\n- {lim}")
        for alt in a.better_alternatives:
            lines.append(f"\n**Better alternative:** {alt}")

    # Ingestion mode note
    if mode == "hybrid":
        lines.append(
            "\nThe source was ingested in hybrid mode; visual artifacts are "
            "preserved alongside text. Check the visual/ directory if "
            "layout-dependent meaning matters."
        )
    elif mode == "visual-first":
        lines.append(
            "\nThe source was ingested in visual-first mode. Text extraction "
            "may be incomplete."
        )
    return "\n".join(lines)


def _tool_candidates_block(opp: OpportunityMap) -> str:
    """Render tool candidates section if any exist."""
    if not opp.tool_candidates:
        return ""
    lines = ["\n## Tool opportunities\n"]
    lines.append(
        "The following capabilities from this source require a tool, "
        "not just a skill:\n"
    )
    for tc in opp.tool_candidates:
        lines.append(f"### {tc.tool_type.replace('_', ' ').title()}")
        lines.append(f"**What it would do:** {tc.description}")
        lines.append(f"**Why a skill is insufficient:** {tc.why_not_skill}")
        lines.append(f"**Build effort:** {tc.effort}")
        if tc.reference_url:
            lines.append(f"**Reference:** {tc.reference_url}")
        lines.append("")
    return "\n".join(lines)


def _related_skills_block(opp: OpportunityMap) -> str:
    """List secondary skill candidates as related skills the agent can load."""
    secondaries = [
        c for c in opp.candidates
        if c.build_timing in ("now", "later") and c.type != opp.recommended_skill_type
    ]
    if not secondaries:
        return "No secondary skill opportunities identified."
    lines = [
        "The following skill types were also detected in this source. "
        "If the task calls for them, load or build the appropriate skill:"
    ]
    for c in secondaries[:5]:
        extras = f" (needs: {', '.join(c.needed_extras)})" if c.needed_extras else ""
        lines.append(
            f"- **{c.type.replace('_', ' ').title()}** "
            f"(confidence: {c.confidence}, timing: {c.build_timing}){extras} — {c.why_fit}"
        )
    return "\n".join(lines)


def _usage_hints(fit, skill_type: str) -> str:
    hints = []
    if fit.rule_density == "high":
        hints.append("- Reviewing or auditing content against rules or heuristics")
    if fit.procedure_density == "high":
        hints.append("- Following or planning a multi-step workflow")
    if fit.example_density == "high":
        hints.append("- Applying worked examples to a new problem")
    hints.append(f"- Tasks of type: {skill_type.replace('_', ' ')}")
    return "\n".join(hints) if hints else f"- General {skill_type.replace('_', ' ')} tasks"


def _parse_llm_sections(text: str) -> tuple[str, str, str]:
    section_re = re.compile(
        r"##\s*Core principle\s*\n(.*?)(?=##\s*Workflow|\Z)"
        r"|##\s*Workflow\s*\n(.*?)(?=##\s*Output format|\Z)"
        r"|##\s*Output format\s*\n(.*?)(?=##\s|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    core = workflow = output = ""
    for m in section_re.finditer(text):
        if m.group(1) is not None: core = m.group(1).strip()
        elif m.group(2) is not None: workflow = m.group(2).strip()
        elif m.group(3) is not None: output = m.group(3).strip()
    core = core or "<!-- LLM response did not include a core principle -->"
    workflow = workflow or "<!-- LLM response did not include a workflow -->"
    output = output or "<!-- LLM response did not include an output format -->"
    return core, workflow, output
