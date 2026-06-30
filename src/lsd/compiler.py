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
from lsd.models import BuildContext

log = logging.getLogger(__name__)

# Maximum source characters sent to the LLM. Wikipedia pages can be 150K+;
# truncate to keep the prompt within a reasonable token budget while still
# giving the model enough signal for concrete, source-specific content.
_MAX_SOURCE_CHARS = 40_000


def compile_skill(
    ctx: BuildContext,
    llm_backend: LLMBackend | None = None,
) -> str:
    """Return the SKILL.md content as a string.

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
            return _compile_with_llm(ctx, backend)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "LLM compiler failed with %s (%s); falling back to heuristic skeleton.",
                backend.model_id,
                exc,
            )

    return _compile_heuristic(ctx)


# ---------------------------------------------------------------------------
# LLM path
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


def _parse_llm_sections(text: str) -> tuple[str, str, str]:
    """Extract the three sections from the LLM response.

    Falls back to placeholder strings if parsing fails rather than crashing.
    """
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


# ---------------------------------------------------------------------------
# Shared template renderer
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

    return f"""---
name: {name}
version: 0.1.0
summary: Auto-generated by LSD from {fetch.canonical_url}
description: >-
  Use this skill when working with content derived from: {fetch.title}.
  Skill type: {skill_type}. Ingestion mode: {mode}.
allowed-tools: Read, Write, Edit
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


# ---------------------------------------------------------------------------
# Heuristic / offline fallback
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
    return _render_template(ctx, core_principle, workflow, output_format, model_id=None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
