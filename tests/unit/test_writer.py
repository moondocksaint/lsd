"""Tests for lsd.writer — checks that all expected files are created."""

import json
from pathlib import Path

from lsd.models import (
    BuildContext, FetchResult, IngestionResult, OpportunityMap,
    SkillCandidate, SourceFit, ToolCandidate,
)
from lsd.writer import write_package


def _build_ctx(tmp_path: Path) -> BuildContext:
    fetch = FetchResult(
        url="https://example.com",
        canonical_url="https://example.com",
        title="Example Page",
        text="You should always avoid this heuristic. For example, do not use passive voice.",
        html="",
        fetched_at="2026-06-30T00:00:00Z",
        http_status=200,
        word_count=16,
    )
    ingestion = IngestionResult(
        fetch=fetch,
        visual=None,
        mode="text-first",
        routing_notes="Prose-dominant source.",
    )
    fit = SourceFit(overall_fit="high", rule_density="high")
    opp = OpportunityMap(
        recommended_action="build_one_skill",
        recommended_skill_type="reviewer",
        candidates=[
            SkillCandidate(type="reviewer", confidence="high", build_timing="now", why_fit="test"),
        ],
    )
    return BuildContext(
        ingestion=ingestion,
        source_fit=fit,
        opportunity_map=opp,
        output_dir=tmp_path / "out",
    )


def test_all_files_created(tmp_path: Path):
    ctx = _build_ctx(tmp_path)
    out = write_package(ctx)

    expected = [
        "SKILL.md",
        "source.md",
        "metadata.json",
        "source-policy.md",
        "skill-opportunities.md",
        "extraction-report.md",
        "CHANGELOG.md",
    ]
    for fname in expected:
        assert (out / fname).exists(), f"Missing {fname}"


def test_metadata_has_required_keys(tmp_path: Path):
    ctx = _build_ctx(tmp_path)
    out = write_package(ctx)
    meta = json.loads((out / "metadata.json").read_text())
    for key in ("package", "source_dependency", "ingestion", "source_fit",
                "opportunity_summary", "governance", "artifacts"):
        assert key in meta, f"metadata.json missing key: {key}"


def test_skill_md_contains_url(tmp_path: Path):
    ctx = _build_ctx(tmp_path)
    out = write_package(ctx)
    skill = (out / "SKILL.md").read_text()
    assert "https://example.com" in skill


def test_hybrid_creates_visual_dir(tmp_path: Path):
    ctx = _build_ctx(tmp_path)
    ctx.ingestion.mode = "hybrid"
    out = write_package(ctx)
    assert (out / "visual").is_dir()


def _add_mcp_candidate(ctx: BuildContext) -> BuildContext:
    ctx.opportunity_map.tool_candidates.append(
        ToolCandidate(
            tool_type="mcp_server",
            description="Expose the API as an MCP server for any MCP-compatible agent.",
            why_not_skill="MCP server enables live execution; a skill only encodes knowledge.",
            effort="high",
            reference_url="https://modelcontextprotocol.io/quickstart/server",
        )
    )
    return ctx


def test_no_mcp_scaffold_without_candidate(tmp_path: Path):
    ctx = _build_ctx(tmp_path)
    out = write_package(ctx)
    assert not (out / "mcp-server").exists()
    meta = json.loads((out / "metadata.json").read_text())
    assert meta["artifacts"]["mcp_scaffold"] is None


def test_mcp_scaffold_created_when_candidate(tmp_path: Path):
    ctx = _add_mcp_candidate(_build_ctx(tmp_path))
    out = write_package(ctx)

    server_dir = out / "mcp-server"
    for fname in ("server.py", "requirements.txt", "README.md"):
        assert (server_dir / fname).exists(), f"Missing mcp-server/{fname}"

    server_py = (server_dir / "server.py").read_text()
    assert "from mcp.server.fastmcp import FastMCP" in server_py
    assert "@mcp.tool()" in server_py
    assert "https://example.com" in server_py  # grounded in the source URL

    readme = (server_dir / "README.md").read_text()
    assert "MCP server enables live execution" in readme  # the why_not_skill rationale

    meta = json.loads((out / "metadata.json").read_text())
    assert meta["artifacts"]["mcp_scaffold"] == "mcp-server/"

    opportunities = (out / "skill-opportunities.md").read_text()
    assert "mcp-server/" in opportunities  # pointer to the scaffold


def test_mcp_scaffold_server_is_valid_python(tmp_path: Path):
    import ast

    ctx = _add_mcp_candidate(_build_ctx(tmp_path))
    out = write_package(ctx)
    server_py = (out / "mcp-server" / "server.py").read_text()
    ast.parse(server_py)  # raises SyntaxError if the scaffold is malformed
