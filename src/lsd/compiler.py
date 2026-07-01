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

Agentskills spec compliance (https://github.com/agentskills/agentskills):
  - name: lowercase alphanumeric + hyphens only, max 64 chars
  - ALLOWED_FIELDS in frontmatter: name, description, license, allowed-tools,
    metadata, compatibility
  - LSD-specific fields (lsd_version, compiler_model, source_url,
    generated_at) live inside the metadata: map, never as top-level keys
  - allowed-tools: space-separated tool-name patterns (no quotes, no commas)
"""

from __future__ import annotations

import logging
import re

from lsd.llm.base import LLMBackend
from lsd.models import BuildContext, MultiSourceBuildContext

log = logging.getLogger(__name__)

# Maximum source characters sent to the LLM for single-source builds.
_MAX_SOURCE_CHARS = 40_000

# Maximum retrieved context chars for multi-source compilation.
_MAX_RETRIEVED_CHARS = 15_000


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compile_skill(
    ctx: BuildContext,
    llm_backend: LLMBackend | None = None,
) -> tuple[str, str | None]:
    """Return (SKILL.md content, compiler_model_id).

    compiler_model_id is None when the heuristic fallback is used.
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
) -> tuple[str, str | None]:
    """Compile a SKILL.md from a multi-source BuildContext.

    Returns (SKILL.md content, compiler_model_id) — same tuple contract as
    compile_skill() so callers can always write compiler_model to metadata.json.
    compiler_model_id is None when the heuristic fallback is used.

    Swap-candidate criteria for the retrieval backend:
      Replace NaiveRetrievalBackend when combined token estimate exceeds
      50K tokens and rubric score falls below 12/14, or when a
      NotebookLM-quality RAG API becomes available via simple HTTP call.
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
        return _compile_heuristic_multi(ctx), None

    if backend is not None:
        try:
            content = _compile_multi_with_llm(ctx, backend, ret_backend, ret_index)
            return content, backend.model_id
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "LLM multi-source compiler failed (%s); falling back to heuristic.",
                exc,
            )

    return _compile_heuristic_multi(ctx), None


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
# Template renderers — agentskills spec compliant
# ---------------------------------------------------------------------------

def _slugify_name(text: str, max_len: int = 60) -> str:
    """Convert free-form text to a valid agentskills skill name.

    Rules: lowercase, alphanumeric + hyphens only, no consecutive hyphens,
    no leading/trailing hyphens, max max_len chars.
    """
    s = text.lower()
    s = re.sub(r"[^\w\s-]", "", s)          # strip special chars (keep word, space, hyphen)
    s = re.sub(r"[\s_]+", "-", s)           # spaces/underscores → hyphens
    s = re.sub(r"-{2,}", "-", s)            # collapse consecutive hyphens
    s = s.strip("-")                         # trim leading/trailing hyphens
    return s[:max_len].rstrip("-")           # truncate without splitting mid-hyphen


def _render_template(
    ctx: BuildContext,
    core_principle: str,
    workflow: str,
    output_format: str,
    model_id: str | None = None,
) -> str:
    """Render a spec-compliant single-source SKILL.md.

    Agentskills ALLOWED_FIELDS: name, description, license, allowed-tools,
    metadata, compatibility. All LSD-specific fields go in metadata:.
    """
    from lsd import __version__ as lsd_version  # noqa: PLC0415

    fetch = ctx.ingestion.fetch
    fit = ctx.source_fit
    opp = ctx.opportunity_map
    mode = ctx.ingestion.mode

    skill_type = opp.recommended_skill_type.replace("_", " ").title()
    # Derive name from skill_type + source title slug; keep it readable
    raw_name = f"{opp.recommended_skill_type}-{_slugify_name(fetch.title)}"
    name = _slugify_name(raw_name)

    caveat_block = _caveat_block(mode, model_id)
    # metadata: map — all LSD-specific provenance fields
    metadata_block = (
        f"  lsd_version: \"{lsd_version}\"\n"
        f"  compiler_model: \"{model_id or 'heuristic'}\"\n"
        f"  source_url: \"{fetch.canonical_url}\"\n"
        f"  generated_at: \"{ctx.generated_at if hasattr(ctx, 'generated_at') else ''}\"\n"
        f"  skill_type: \"{opp.recommended_skill_type}\"\n"
        f"  ingestion_mode: \"{mode}\""
    )

    return f"""---
name: {name}
description: >-
  Use this skill when working with content derived from: {fetch.title}.
  Skill type: {skill_type}. Trigger phrases: {skill_type.lower()},
  review with {opp.recommended_skill_type.replace('_', ' ')}, apply {name}.
license: Apache-2.0
allowed-tools: Read Write Edit
metadata:
{metadata_block}
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
    """Render a spec-compliant multi-source SKILL.md.

    Agentskills ALLOWED_FIELDS: name, description, license, allowed-tools,
    metadata, compatibility. All LSD-specific fields go in metadata:.
    """
    from lsd import __version__ as lsd_version  # noqa: PLC0415

    opp = ctx.combined_opportunities
    skill_type = opp.recommended_skill_type.replace("_", " ").title()
    # Name for multi-source: skill_type slug + "-multi"
    name = _slugify_name(f"{opp.recommended_skill_type}-multi")

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

    source_urls = " ".join(e.url for e in ctx.sources)
    metadata_block = (
        f"  lsd_version: \"{lsd_version}\"\n"
        f"  compiler_model: \"{model_id or 'heuristic'}\"\n"
        f"  source_count: {len(ctx.sources)}\n"
        f"  source_urls: \"{source_urls[:200]}\"\n"
        f"  skill_type: \"{opp.recommended_skill_type}\""
    )

    return f"""---
name: {name}
description: >-
  Multi-source skill for {skill_type.lower()} tasks, compiled from
  {len(ctx.sources)} sources. Use when performing {skill_type.lower()}
  tasks that draw on multiple reference documents. Trigger phrases:
  {skill_type.lower()}, multi-source {opp.recommended_skill_type.replace('_', ' ')},
  apply {name}.
license: Apache-2.0
allowed-tools: Read Write Edit
metadata:
{metadata_block}
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
    return _render_template(ctx, core_principle, workflow, output_format, model_id=None)


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
