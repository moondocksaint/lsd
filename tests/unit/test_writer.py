"""Tests for lsd.writer — checks that all expected files are created."""

import json
from pathlib import Path

from lsd.models import (
    BuildContext, FetchResult, IngestionResult, OpportunityMap,
    SkillCandidate, SourceFit,
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
