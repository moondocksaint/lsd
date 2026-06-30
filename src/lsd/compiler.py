"""Compile a SKILL.md from a BuildContext.

Two modes — selected automatically, no flag needed:

  LLM mode     An LLMBackend is available (configured via env vars or
               passed explicitly). Fills Core principle, Workflow, and
               Output format with source-specific content.

  Offline mode No backend available or the LLM call fails. Returns the
               heuristic skeleton with <!-- TODO --> placeholders so the
               build always succeeds.

Provider configuration (env vars):

  LSD_LLM_PROVIDER   anthropic (default) | openai-compat
  ANTHROPIC_API_KEY  Key for Anthropic
  LSD_LLM_BASE_URL   Base URL for openai-compat (OpenRouter, Inception, Ollama, …)
  LSD_LLM_API_KEY    Key for openai-compat
  LSD_MODEL          Model name override (provider-specific)

See lsd/llm/__init__.py for the full provider reference.
"""

from __future__ import annotations

import logging
import re

from lsd.llm.base import LLMBackend
from lsd.models import BuildContext, MultiSourceBuildContext

log = logging.getLogger(__name__)

# Maximum source characters sent to the LLM for single-source builds.
# Wikipedia pages can be 150K+; truncate to keep the prompt within a
# reasonable token budget while still giving the model enough signal.
_MAX_SOURCE_CHARS = 40_000

# Maximum retrieved context chars for multi-source compilation.
# Each passage is ~1200 chars; at k=10 that's ~12K chars of grounding
# context, leaving headroom for the prompt and response.
_MAX_RETRIEVED_CHARS = 15_000


def compile_skill(
    ctx: BuildContext,
    llm_backend: LLMBackend | None = None,
) -> tuple[str, str | None]:
    """Return (SKILL.md content, compiler_model_id).

    compiler_model_id is None when the heuristic fallback is used.

    Args:
        ctx:         The BuildContext from the pipeline.
        llm_backend: Optional explicit backend. If None, the factory in
                     lsd.llm resolves from env vars. If no backend is
                     configured, falls back to the heuristic skeleton.
    """
    backend = llm_backend
    if backend is None:
        try:
            from lsd.llm import get_llm_backend  # noqa: PLC0415
            backend = get_llm_backend()
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not initialise LLM backend (%s); using heuristic fallback.", exc)

    if backend is not None:
        try:
            content = _compile_with_llm(ctx, backend)
            return content, backend.model_id
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "LLM compiler failed with %s (%s); falling back to heuristic skeleton.",
                backend.model_id,
                exc,
            )

    return _compile_heuristic(ctx), None


def compile_skill_multi(
    ctx: MultiSourceBuildContext,
    llm_backend: LLMBackend | None = None,
    retrieval_backend=None,
) -> str:
    """Compile a SKILL.md from a multi-source BuildContext.

    Uses the retrieval backend to ground compilation in the most relevant
    passages across all sources, preserving provenance in the output.

    Args:
        ctx:               The MultiSourceBuildContext from build_multi().
        llm_backend:       Optional explicit LLM backend.
        retrieval_backend: Optional explicit RetrievalBackend. If None,
                           uses the default from retrieval/__init__.py.

    Returns:
        SKILL.md content as a string.
    """
    from lsd.models import IndexedSource
    from lsd.retrieval import get_retrieval_backend

    backend = llm_backend
    if backend is None:
        try:
            from lsd.llm import get_llm_backend  # noqa: PLC0415
            backend = get_llm_backend()
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not initialise LLM backend (%s); using heuristic fallback.", exc)

    ret_backend = retrieval_backend
    if ret_backend is None:
        ret_backend = get_retrieval_backend()

    # Build IndexedSource list from SourceEntry objects
    indexed = [
        IndexedSource(
            index=entry.index,
            url=entry.url,
            source_file=f"source-{entry.index}.md",
            text=entry.normalised,
        )
        for entry in ctx.sources
    ]

    # Build retrieval index
    try:
        ret_index = ret_backend.index(indexed)
    except Exception as exc:  # noqa: BLE001
        log.warning("Retrieval indexing failed (%s); falling back to heuristic.", exc)
        return _compile_heuristic_multi(ctx)

    if backend is not None:
        try:
            return _compile_multi_with_llm(ctx, backend, ret_backend, ret_index)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "LLM multi-source compiler failed (%s); falling back to heuristic.",
                exc,
            )

    return _compile_heuristic_multi(ctx)


# ---------------------------------------------------------------------------
# LLM path — single source
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
        "Your job is to read a source document and write three concise, "
        "source-specific sections for a reusable AI skill file. "
        "Be concrete. Do not use generic boilerplate. "
        "Every sentence must be grounded in the source content provided."
    )

    user = f"""Source URL: {fetch.canonical_url}
Source title: {fetch.title}
Skill type to build: {skill_type}
Source fit signals: {fit_summary}

Source content:
---
{source_excerpt}
---

Write exactly three sections in this format (use these exact headings):

## Core principle
[One sentence that distils the source's central, actionable idea. Be specific to this source.]

## Workflow
[3-7 numbered steps derived from the source's actual procedures or rules. Each step must reference something concrete from the source.]

## Output format
[3-6 bullet fields describing the structure of output when this skill is used. Be specific to the skill type: {skill_type}.]

Return only the three sections above. No preamble, no commentary."""

    response = backend.complete(system=system, user=user, max_tokens=1024)
    core_principle, workflow, output_format = _parse_llm_sections(response)
    return _render_template(ctx, core_principle, workflow, output_format, model_id=backend.model_id)


# ---------------------------------------------------------------------------
# LLM path — multi-source with retrieval grounding
# ---------------------------------------------------------------------------

def _compile_multi_with_llm(
    ctx: MultiSourceBuildContext,
    backend: LLMBackend,
    ret_backend,
    ret_index,
) -> str:
    opp = ctx.combined_opportunities
    skill_type = opp.recommended_skill_type.replace("_", " ")

    # Retrieve relevant passages for each of the three compiled sections
    queries = [
        f"core principle and central idea for {skill_type}",
        f"step-by-step workflow and procedures for {skill_type}",
        f"output format and structure for {skill_type}",
    ]

    all_passages = []
    seen_offsets: set[tuple[int, int]] = set()
    for query in queries:
        for p in ret_backend.retrieve(ret_index, query, k=5):
            key = (p.source_index, p.char_offset)
            if key not in seen_offsets:
                seen_offsets.add(key)
                all_passages.append(p)

    # Build grounded context block with provenance markers
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

    # Source summary for prompt
    source_lines = "\n".join(
        f"  Source {e.index}: {e.url}" for e in ctx.sources
    )
    conflict_note = ""
    if ctx.conflict_report.has_blocking_conflicts:
        conflict_note = (
            "\n\nIMPORTANT: The sources contain contradictions. "
            "Surface these explicitly in the compiled skill rather than "
            "silently picking one source. The user will resolve them."
        )
    elif ctx.conflict_report.conflicts:
        conflict_note = f"\n\nNote: {ctx.conflict_report.summary}"

    system = (
        "You are a skill compiler for LSD (Link-to-Skill Designer). "
        "You are compiling a skill from MULTIPLE sources. "
        "Every claim in the compiled skill must be traced to a specific source passage "
        "(cite as [Source N]). "
        "Do not merge contradictions silently — surface them explicitly. "
        "Be concrete and source-specific. No generic boilerplate."
    )

    user = f"""Sources ({len(ctx.sources)} total):
{source_lines}

Skill type to build: {skill_type}{conflict_note}

Retrieved source passages (with provenance markers):
---
{grounded_context}
---

Write exactly three sections in this format (use these exact headings):

## Core principle
[One sentence per source that distils each source's central idea for {skill_type}. Cite each claim as [Source N].]

## Workflow
[3-7 numbered steps derived from the source procedures. Cite each step with [Source N]. If sources conflict on a step, note the conflict explicitly.]

## Output format
[3-6 bullet fields describing the output structure for {skill_type}. Cite sources.]

Return only the three sections above. No preamble, no commentary."""

    response = backend.complete(system=system, user=user, max_tokens=1500)
    core_principle, workflow, output_format = _parse_llm_sections(response)
    return _render_template_multi(
        ctx, core_principle, workflow, output_format, model_id=backend.model_id
    )


# ---------------------------------------------------------------------------
# Template renderers
# ---------------------------------------------------------------------------

def _render_template(
    ctx: BuildContext,
    core_principle: str,
    workflow: str,
    output_format: str,
    model_id: str | None = None,
) -> str:
    fetch = ctx.ingestion.fetch
    fit = ctx.source_fit
    opp = ctx.opportunity_map
    mode = ctx.ingestion.mode

    skill_type = opp.recommended_skill_type.replace("_", " ").title()
    name = f"{skill_type} — from {fetch.title[:60]}"
    caveat_block = _caveat_block(mode, model_id)
    compiler_model_field = f"\ncompiler_model: {model_id}" if model_id else ""

    return f"""---
name: {name}
version: 0.1.0
summary: Auto-generated by LSD from {fetch.canonical_url}
description: >-
  Use this skill when working with content derived from: {fetch.title}.
  Skill type: {skill_type}. Ingestion mode: {mode}.
allowed-tools: Read, Write, Edit{compiler_model_field}
---

## Purpose

This skill was compiled by LSD from the following source:
- URL: {fetch.canonical_url}
- Title: {fetch.title}
- Ingestion mode: {mode}
- Skill type: {skill_type}

Review and refine this file before use. The sections below are
seeded from source signals and should be expanded with domain knowledge.

## When to use

Use this skill when asked to perform tasks related to:
{_usage_hints(fit, opp.recommended_skill_type)}

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
    opp = ctx.combined_opportunities
    skill_type = opp.recommended_skill_type.replace("_", " ").title()
    source_list = "\n".join(
        f"- Source {e.index}: {e.url}" for e in ctx.sources
    )
    conflict_section = ""
    if ctx.conflict_report.conflicts:
        conflict_section = f"\n## Source conflicts\n\n{ctx.conflict_report.summary}\n\nSee conflicts.md for full details.\n"

    llm_note = (
        f"Core sections were compiled by {model_id}."
        if model_id
        else (
            "Core sections contain placeholder text — configure an LLM provider "
            "via LSD_LLM_PROVIDER + API key env vars for full compilation."
        )
    )

    return f"""---
name: {skill_type} — multi-source
version: 0.3.0
summary: Auto-generated by LSD from {len(ctx.sources)} sources
description: >-
  Multi-source skill compiled from {len(ctx.sources)} URLs.
  Skill type: {skill_type}.
allowed-tools: Read, Write, Edit
---

## Purpose

This skill was compiled by LSD from {len(ctx.sources)} sources:
{source_list}

Review and refine before use. Every claim is cited with [Source N].
{conflict_section}
## When to use

Use this skill for: {skill_type.lower()} tasks drawing on multiple reference sources.

## Core principle

{core_principle}

## Workflow

{workflow}

## Output format

{output_format}

## Style rule

Be specific and actionable. Cite sources for every claim. Surface conflicts
rather than silently resolving them.

## Caveats

Auto-generated by LSD. {llm_note} Review all [Source N] citations before
promoting this skill to production use.

## Sources

{source_list}
"""


# ---------------------------------------------------------------------------
# Heuristic / offline fallbacks
# ---------------------------------------------------------------------------

def _compile_heuristic(ctx: BuildContext) -> str:
    """Return a skeleton SKILL.md with TODO placeholders (no LLM required)."""
    core_principle = "<!-- TODO: distil the source's central idea into one sentence. -->"
    workflow = (
        "<!-- TODO: expand from the source's procedure signals. -->\n"
        "1. Read the input in full.\n"
        "2. Apply the relevant checks or procedures from the source.\n"
        "3. Produce structured output."
    )
    output_format = (
        "<!-- TODO: define the expected output structure. -->\n"
        "Provide structured output with:\n"
        "- Finding or step name\n"
        "- Evidence or rationale\n"
        "- Recommended action"
    )
    return _render_template(ctx, core_principle, workflow, output_format, model_id=None), None


def _compile_heuristic_multi(ctx: MultiSourceBuildContext) -> str:
    """Return a skeleton multi-source SKILL.md with TODO placeholders."""
    core_principle = "<!-- TODO: distil central ideas from each source. -->"
    workflow = (
        "<!-- TODO: synthesise procedures from all sources. -->\n"
        "1. Read all source files.\n"
        "2. Apply the relevant checks or procedures.\n"
        "3. Produce structured output with source citations."
    )
    output_format = (
        "<!-- TODO: define the expected output structure. -->\n"
        "Provide structured output with:\n"
        "- Finding or step name [Source N]\n"
        "- Evidence or rationale\n"
        "- Recommended action"
    )
    return _render_template_multi(ctx, core_principle, workflow, output_format, model_id=None)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _parse_llm_sections(text: str) -> tuple[str, str, str]:
    """Extract the three sections from the LLM response."""
    section_re = re.compile(
        r"##\s*Core principle\s*\n(.*?)(?=##\s*Workflow|\Z)"
        r"|##\s*Workflow\s*\n(.*?)(?=##\s*Output format|\Z)"
        r"|##\s*Output format\s*\n(.*?)(?=##\s|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    core = workflow = output = ""
    for m in section_re.finditer(text):
        if m.group(1) is not None:
            core = m.group(1).strip()
        elif m.group(2) is not None:
            workflow = m.group(2).strip()
        elif m.group(3) is not None:
            output = m.group(3).strip()

    core = core or "<!-- LLM response did not include a core principle -->"
    workflow = workflow or "<!-- LLM response did not include a workflow -->"
    output = output or "<!-- LLM response did not include an output format -->"
    return core, workflow, output


def _usage_hints(fit, skill_type: str) -> str:
    hints = []
    if fit.rule_density == "high":
        hints.append("- Reviewing or auditing content against a set of rules or heuristics")
    if fit.procedure_density == "high":
        hints.append("- Following or planning a multi-step workflow")
    if fit.example_density == "high":
        hints.append("- Applying worked examples to a new problem")
    hints.append(f"- Tasks of type: {skill_type.replace('_', ' ')}")
    return "\n".join(hints) if hints else "- General tasks related to the source domain"


def _caveat_block(mode: str, model_id: str | None) -> str:
    base = "This skill was auto-generated by LSD and should be reviewed before use."
    llm_note = (
        f" Core sections were compiled by {model_id}."
        if model_id
        else (
            " Core sections contain placeholder text — configure an LLM provider "
            "via LSD_LLM_PROVIDER + API key env vars for full compilation."
        )
    )
    suffix = base + llm_note
    if mode == "hybrid":
        return (
            f"{suffix} The source was ingested in hybrid mode; "
            "visual artifacts are preserved alongside text. "
            "Check the visual/ directory if layout-dependent meaning matters."
        )
    if mode == "visual-first":
        return (
            f"{suffix} The source was ingested in visual-first mode; "
            "the primary artifact is a rendered screenshot. "
            "Text extraction may be incomplete."
        )
    return suffix
