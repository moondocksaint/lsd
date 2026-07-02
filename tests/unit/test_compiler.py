"""Tests for lsd.compiler — covers offline fallback and LLM path via a stub backend."""

from __future__ import annotations

from pathlib import Path

from lsd.compiler import compile_skill
from lsd.llm.base import LLMBackend
from lsd.models import (
    BuildContext,
    FetchResult,
    IngestionResult,
    OpportunityMap,
    SkillCandidate,
    SourceFit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_ctx(tmp_path: Path, text: str = "Rules and heuristics example.") -> BuildContext:
    fetch = FetchResult(
        url="https://example.com",
        canonical_url="https://example.com",
        title="Example Skill Source",
        text=text,
        html="",
        fetched_at="2026-06-30T00:00:00Z",
        http_status=200,
        word_count=len(text.split()),
    )
    ingestion = IngestionResult(
        fetch=fetch,
        visual=None,
        mode="text-first",
        routing_notes="text-first selected",
    )
    fit = SourceFit(overall_fit="high", rule_density="high", example_density="high")
    opp = OpportunityMap(
        recommended_action="build_one_skill",
        recommended_skill_type="reviewer",
        candidates=[
            SkillCandidate(
                type="reviewer", confidence="high", build_timing="now",
                why_fit="High rule density",
            )
        ],
    )
    return BuildContext(
        ingestion=ingestion,
        source_fit=fit,
        opportunity_map=opp,
        output_dir=tmp_path / "out",
    )


class _StubLLMBackend(LLMBackend):
    """Deterministic stub — returns a fixed three-section response."""

    def __init__(self, response: str | None = None, raise_exc: Exception | None = None):
        self._response = response
        self._raise = raise_exc

    @property
    def model_id(self) -> str:
        return "stub/test-model"

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        if self._raise is not None:
            raise self._raise
        return self._response or _STUB_RESPONSE


_STUB_RESPONSE = """\
## Core principle
Always check each claim against the source rules before drawing a conclusion.

## Workflow
1. Read the source document in full.
2. Identify the applicable rule or heuristic.
3. Apply it to the input.
4. Record the finding with evidence.

## Output format
- Rule applied
- Evidence from input
- Verdict (pass / fail / unclear)
- Recommended action
"""


# ---------------------------------------------------------------------------
# Offline fallback (no backend)
# ---------------------------------------------------------------------------

def test_offline_fallback_contains_todo_placeholders(tmp_path):
    ctx = _build_ctx(tmp_path)
    result, _ = compile_skill(ctx, llm_backend=None)
    assert "<!-- TODO" in result


def test_offline_fallback_still_has_required_frontmatter(tmp_path):
    ctx = _build_ctx(tmp_path)
    result, _ = compile_skill(ctx, llm_backend=None)
    assert "name:" in result
    assert "version:" in result
    assert "allowed-tools:" in result


def test_offline_fallback_contains_source_url(tmp_path):
    ctx = _build_ctx(tmp_path)
    result, _ = compile_skill(ctx, llm_backend=None)
    assert "https://example.com" in result


def test_offline_caveat_mentions_env_var(tmp_path):
    ctx = _build_ctx(tmp_path)
    result, _ = compile_skill(ctx, llm_backend=None)
    assert "LLM_PROVIDER" in result or "placeholder" in result.lower()


# ---------------------------------------------------------------------------
# LLM path — using stub backend
# ---------------------------------------------------------------------------

def test_llm_path_fills_core_principle(tmp_path):
    ctx = _build_ctx(tmp_path)
    result, _ = compile_skill(ctx, llm_backend=_StubLLMBackend())
    assert "## Core principle" in result
    assert "claim" in result  # from stub response


def test_llm_path_fills_workflow(tmp_path):
    ctx = _build_ctx(tmp_path)
    result, _ = compile_skill(ctx, llm_backend=_StubLLMBackend())
    assert "## Workflow" in result
    assert "1." in result


def test_llm_path_fills_output_format(tmp_path):
    ctx = _build_ctx(tmp_path)
    result, _ = compile_skill(ctx, llm_backend=_StubLLMBackend())
    assert "## Output format" in result
    assert "Verdict" in result


def test_llm_path_no_todo_placeholders(tmp_path):
    ctx = _build_ctx(tmp_path)
    result, _ = compile_skill(ctx, llm_backend=_StubLLMBackend())
    assert "<!-- TODO" not in result


def test_llm_path_caveat_names_model(tmp_path):
    ctx = _build_ctx(tmp_path)
    result, _ = compile_skill(ctx, llm_backend=_StubLLMBackend())
    assert "stub/test-model" in result


# ---------------------------------------------------------------------------
# LLM failure → graceful fallback to heuristic skeleton
# ---------------------------------------------------------------------------

def test_llm_failure_falls_back_to_heuristic(tmp_path):
    ctx = _build_ctx(tmp_path)
    failing_backend = _StubLLMBackend(raise_exc=RuntimeError("API timeout"))
    result, _ = compile_skill(ctx, llm_backend=failing_backend)
    # Must not raise; must fall back to TODO skeleton
    assert "<!-- TODO" in result


def test_llm_failure_fallback_still_valid_skill_md(tmp_path):
    ctx = _build_ctx(tmp_path)
    failing_backend = _StubLLMBackend(raise_exc=ConnectionError("network error"))
    result, _ = compile_skill(ctx, llm_backend=failing_backend)
    assert "name:" in result
    assert "https://example.com" in result


# ---------------------------------------------------------------------------
# Malformed LLM response → graceful partial fill
# ---------------------------------------------------------------------------

def test_malformed_llm_response_uses_placeholder_for_missing_sections(tmp_path):
    ctx = _build_ctx(tmp_path)
    # Response that only has Core principle, missing Workflow and Output format
    partial_response = "## Core principle\nOnly check the most recent source.\n"
    result, _ = compile_skill(ctx, llm_backend=_StubLLMBackend(response=partial_response))
    assert "Only check the most recent source." in result
    # Missing sections should get placeholder comments
    assert "LLM response did not include" in result


def test_allowed_tools_accepts_valid_skill_types():
    from lsd.compiler import _allowed_tools_for_skill_type
    # All known SkillType values should return a non-empty string without error
    valid_types = [
        "reviewer", "rewriter", "reference_companion", "semantic_reference",
        "data_pipeline", "mcp_server", "function_tool", "api_wrapper",
        "workflow_coach", "integration_planner", "ingestion_advisor",
    ]
    for st in valid_types:
        result = _allowed_tools_for_skill_type(st)  # type: ignore[arg-type]
        assert isinstance(result, str) and len(result) > 0, f"empty result for {st!r}"


def test_skill_type_literal_importable():
    from lsd.models import SkillType  # noqa: F401 — just assert importable
    assert SkillType is not None


# ---------------------------------------------------------------------------
# Gotchas section
# ---------------------------------------------------------------------------

_STUB_WITH_GOTCHAS = """\
## Core principle
Check each claim against the source before concluding.

## Workflow
1. Read the source.
2. Apply the rule.

## Output format
- Rule applied
- Verdict

## Gotchas
- Requires the API key in the FOO_TOKEN env var; unset means silent 401.
- The v2 endpoint is rate-limited to 10 req/min.
"""


def test_gotchas_section_always_present(tmp_path):
    # Even the standard stub (no Gotchas) must still render the heading.
    ctx = _build_ctx(tmp_path)
    result, _ = compile_skill(ctx, llm_backend=_StubLLMBackend())
    assert "## Gotchas" in result


def test_gotchas_section_populated_from_llm(tmp_path):
    ctx = _build_ctx(tmp_path)
    result, _ = compile_skill(ctx, llm_backend=_StubLLMBackend(response=_STUB_WITH_GOTCHAS))
    assert "## Gotchas" in result
    assert "FOO_TOKEN" in result
    assert "rate-limited" in result


def test_gotchas_neutral_note_when_absent(tmp_path):
    # Standard stub response omits Gotchas → neutral note, not a TODO/bug marker.
    ctx = _build_ctx(tmp_path)
    result, _ = compile_skill(ctx, llm_backend=_StubLLMBackend())
    gotchas_body = result.split("## Gotchas", 1)[1].split("##", 1)[0]
    assert "No environment-specific gotchas" in gotchas_body
    assert "<!-- TODO" not in gotchas_body


def test_gotchas_none_answer_collapses_to_neutral_note(tmp_path):
    # A model that answers the required prompt with "None identified in the source."
    response = _STUB_RESPONSE.replace(
        "## Output format",
        "## Gotchas\nNone identified in the source.\n\n## Output format",
    )
    ctx = _build_ctx(tmp_path)
    result, _ = compile_skill(ctx, llm_backend=_StubLLMBackend(response=response))
    gotchas_body = result.split("## Gotchas", 1)[1].split("##", 1)[0]
    assert "No environment-specific gotchas" in gotchas_body


def test_heuristic_gotchas_has_todo(tmp_path):
    ctx = _build_ctx(tmp_path)
    result, _ = compile_skill(ctx, llm_backend=None)
    gotchas_body = result.split("## Gotchas", 1)[1].split("##", 1)[0]
    assert "<!-- TODO" in gotchas_body
