"""Tests for multi-source pipeline (build_multi)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lsd.models import (
    ConflictReport,
    FetchResult,
    IngestionMode,
    MultiSourceBuildContext,
    OpportunityMap,
    SkillCandidate,
    SourceEntry,
    SourceFit,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fetch(url: str, content: str = "# Hello\n\nWorld.") -> FetchResult:
    return FetchResult(
        url=url,
        canonical_url=url,
        title="Test Page",
        text=content,
        html="<p>World.</p>",
        fetched_at="2026-01-01T00:00:00+00:00",
        http_status=200,
        word_count=2,
        source_type="html",
    )


def _make_fit() -> SourceFit:
    return SourceFit(overall_fit="medium")


def _make_routing(url: str, content: str = "# Hello\n\nWorld."):
    from lsd.pipeline import Routing
    return Routing(
        fetch=_make_fetch(url, content),
        source_fit=_make_fit(),
        visual_backend=None,
        mode="text-first",
        routing_notes="test",
    )


def _make_empty_conflict_report() -> ConflictReport:
    return ConflictReport(conflicts=[], summary="No conflicts.", has_blocking_conflicts=False)


def _make_empty_opp() -> OpportunityMap:
    return OpportunityMap(
        recommended_action="defer",
        recommended_skill_type="unknown",
        candidates=[],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@patch("lsd.pipeline.prepare")
@patch("lsd.pipeline.normalise", return_value="# Normalised\n\nContent.")
@patch("lsd.pipeline.detect_conflicts")
@patch("lsd.pipeline.map_opportunities_multi")
def test_build_multi_returns_multi_context(mock_opp, mock_conflicts, mock_norm, mock_prepare, tmp_path):
    mock_prepare.side_effect = lambda url, mo: _make_routing(url)
    mock_conflicts.return_value = _make_empty_conflict_report()
    mock_opp.return_value = _make_empty_opp()

    from lsd.pipeline import build_multi
    ctx = build_multi(["https://a.example.com", "https://b.example.com"], tmp_path)

    assert isinstance(ctx, MultiSourceBuildContext)
    assert len(ctx.sources) == 2


@patch("lsd.pipeline.prepare")
@patch("lsd.pipeline.normalise", return_value="# Normalised\n\nContent.")
@patch("lsd.pipeline.detect_conflicts")
@patch("lsd.pipeline.map_opportunities_multi")
def test_build_multi_preserves_url_order(mock_opp, mock_conflicts, mock_norm, mock_prepare, tmp_path):
    urls = [f"https://source-{i}.example.com" for i in range(5)]
    mock_prepare.side_effect = lambda url, mo: _make_routing(url)
    mock_conflicts.return_value = _make_empty_conflict_report()
    mock_opp.return_value = _make_empty_opp()

    from lsd.pipeline import build_multi
    ctx = build_multi(urls, tmp_path)

    for i, entry in enumerate(ctx.sources):
        assert entry.url == urls[i]
        assert entry.index == i + 1


@patch("lsd.pipeline.prepare")
@patch("lsd.pipeline.normalise", return_value="# Normalised\n\nContent.")
@patch("lsd.pipeline.detect_conflicts")
@patch("lsd.pipeline.map_opportunities_multi")
def test_build_multi_single_url_allowed(mock_opp, mock_conflicts, mock_norm, mock_prepare, tmp_path):
    mock_prepare.side_effect = lambda url, mo: _make_routing(url)
    mock_conflicts.return_value = ConflictReport(
        conflicts=[], summary="Single source.", has_blocking_conflicts=False
    )
    mock_opp.return_value = _make_empty_opp()

    from lsd.pipeline import build_multi
    ctx = build_multi(["https://only.example.com"], tmp_path)
    assert len(ctx.sources) == 1


@patch("lsd.pipeline.prepare")
@patch("lsd.pipeline.normalise", return_value="# Normalised\n\nContent.")
@patch("lsd.pipeline.detect_conflicts")
@patch("lsd.pipeline.map_opportunities_multi")
def test_build_multi_indices_are_one_based(mock_opp, mock_conflicts, mock_norm, mock_prepare, tmp_path):
    urls = ["https://first.example.com", "https://second.example.com"]
    mock_prepare.side_effect = lambda url, mo: _make_routing(url)
    mock_conflicts.return_value = _make_empty_conflict_report()
    mock_opp.return_value = _make_empty_opp()

    from lsd.pipeline import build_multi
    ctx = build_multi(urls, tmp_path)

    assert ctx.sources[0].index == 1
    assert ctx.sources[1].index == 2


@patch("lsd.pipeline.prepare")
@patch("lsd.pipeline.normalise", return_value="# Normalised\n\nContent.")
@patch("lsd.pipeline.detect_conflicts")
@patch("lsd.pipeline.map_opportunities_multi")
def test_build_multi_conflict_report_attached(mock_opp, mock_conflicts, mock_norm, mock_prepare, tmp_path):
    mock_prepare.side_effect = lambda url, mo: _make_routing(url)
    report = ConflictReport(
        conflicts=[],
        summary="Test summary.",
        has_blocking_conflicts=False,
    )
    mock_conflicts.return_value = report
    mock_opp.return_value = _make_empty_opp()

    from lsd.pipeline import build_multi
    ctx = build_multi(["https://a.example.com", "https://b.example.com"], tmp_path)

    assert ctx.conflict_report is report
    assert ctx.conflict_report.summary == "Test summary."


@patch("lsd.pipeline.prepare")
@patch("lsd.pipeline.normalise", return_value="# Normalised\n\nContent.")
@patch("lsd.pipeline.detect_conflicts")
@patch("lsd.pipeline.map_opportunities_multi")
def test_build_multi_output_dir_stored(mock_opp, mock_conflicts, mock_norm, mock_prepare, tmp_path):
    mock_prepare.side_effect = lambda url, mo: _make_routing(url)
    mock_conflicts.return_value = _make_empty_conflict_report()
    mock_opp.return_value = _make_empty_opp()

    from lsd.pipeline import build_multi
    ctx = build_multi(["https://a.example.com"], tmp_path)
    assert ctx.output_dir == tmp_path
