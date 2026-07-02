"""Tests for the heuristic conflict detector."""
from __future__ import annotations

from unittest.mock import MagicMock


from lsd.conflict_detector import detect_conflicts
from lsd.models import FetchResult, SourceEntry, SourceFit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_entry(index: int, content: str, url: str = "") -> SourceEntry:
    fetch = MagicMock(spec=FetchResult)
    fetch.source_type = "html"
    fit = MagicMock(spec=SourceFit)
    fit.overall_fit = "medium"
    return SourceEntry(
        url=url or f"https://source-{index}.example.com",
        fetch_result=fetch,
        fit=fit,
        source_type="html",
        normalised=content,
        ingestion_mode="text-first",
        index=index,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_single_source_no_conflicts():
    entry = _make_entry(1, "# Hello\n\nThis is content.")
    report = detect_conflicts([entry])
    assert not report.conflicts
    assert not report.has_blocking_conflicts
    assert "Single source" in report.summary


def test_empty_sources_treated_as_single():
    """Edge case: empty list → single-source branch."""
    report = detect_conflicts([])
    assert not report.conflicts
    assert not report.has_blocking_conflicts


def test_two_identical_sources_detect_overlap():
    sentences = [
        "This is a long sentence that appears in both documents and should be detected here.",
        "Another long sentence that is identical across both source documents for testing.",
        "Yet another long sentence that exists in both of the test sources we created here.",
        "A fourth long sentence that is duplicated between source one and source two here.",
        "The fifth long sentence is also duplicated to trigger the overlap threshold here.",
    ]
    content = "\n".join(sentences)
    e1 = _make_entry(1, content)
    e2 = _make_entry(2, content)
    report = detect_conflicts([e1, e2])
    overlap_conflicts = [c for c in report.conflicts if c.kind == "overlap"]
    assert len(overlap_conflicts) >= 1
    assert overlap_conflicts[0].severity == "low"
    assert 1 in overlap_conflicts[0].source_indices
    assert 2 in overlap_conflicts[0].source_indices


def test_contradiction_detected():
    content_a = "The system **supports** distributed transactions. `ACID` compliance is guaranteed."
    content_b = "The system does not **support** distributed transactions. `ACID` compliance is not guaranteed."
    e1 = _make_entry(1, content_a)
    e2 = _make_entry(2, content_b)
    report = detect_conflicts([e1, e2])
    contradiction_conflicts = [c for c in report.conflicts if c.kind == "contradiction"]
    assert len(contradiction_conflicts) >= 1
    assert contradiction_conflicts[0].severity == "high"
    assert report.has_blocking_conflicts


def test_gap_detected():
    content_a = "\n".join([
        "# Installation", "Steps to install.",
        "# Configuration", "How to configure.",
        "# Deployment", "How to deploy.",
        "# Monitoring", "How to monitor.",
        "# Troubleshooting", "How to troubleshoot.",
    ])
    content_b = "# Installation\n\nOnly installation."
    e1 = _make_entry(1, content_a)
    e2 = _make_entry(2, content_b)
    report = detect_conflicts([e1, e2])
    gap_conflicts = [c for c in report.conflicts if c.kind == "gap"]
    assert len(gap_conflicts) >= 1
    assert gap_conflicts[0].severity == "medium"


def test_no_false_positive_contradictions():
    content_a = "The system supports fast queries."
    content_b = "The system supports fast queries too."
    e1 = _make_entry(1, content_a)
    e2 = _make_entry(2, content_b)
    report = detect_conflicts([e1, e2])
    contradiction_conflicts = [c for c in report.conflicts if c.kind == "contradiction"]
    assert len(contradiction_conflicts) == 0


def test_conflict_report_summary_non_empty():
    content_a = "# Alpha\n# Beta\n# Gamma\n# Delta\n# Epsilon\n"
    content_b = "# Alpha\n"
    e1 = _make_entry(1, content_a)
    e2 = _make_entry(2, content_b)
    report = detect_conflicts([e1, e2])
    assert isinstance(report.summary, str)
    assert len(report.summary) > 0


def test_conflict_report_dataclass_fields():
    e1 = _make_entry(1, "# Hello\n")
    e2 = _make_entry(2, "# World\n")
    report = detect_conflicts([e1, e2])
    assert hasattr(report, "conflicts")
    assert hasattr(report, "summary")
    assert hasattr(report, "has_blocking_conflicts")
    assert isinstance(report.conflicts, list)
    assert isinstance(report.has_blocking_conflicts, bool)


def test_three_sources_pairwise_gaps():
    """Gap detection should run on all pairs, not just consecutive ones."""
    a = "# Alpha\n# Beta\n# Gamma\n# Delta\n# Epsilon\n"
    b = "# Alpha\n"
    c = "# Alpha\n"
    e1 = _make_entry(1, a)
    e2 = _make_entry(2, b)
    e3 = _make_entry(3, c)
    report = detect_conflicts([e1, e2, e3])
    gap_conflicts = [c for c in report.conflicts if c.kind == "gap"]
    # Should detect gaps between (1,2) and (1,3) at minimum
    involved_pairs = {tuple(sorted(c.source_indices)) for c in gap_conflicts}
    assert (1, 2) in involved_pairs
    assert (1, 3) in involved_pairs


def test_has_blocking_conflicts_false_when_no_contradictions():
    content_a = "# Only gaps\n# Section A\n# Section B\n# Section C\n# Section D\n"
    content_b = "# Only gaps\n"
    e1 = _make_entry(1, content_a)
    e2 = _make_entry(2, content_b)
    report = detect_conflicts([e1, e2])
    # Gaps are medium severity, never blocking
    assert not report.has_blocking_conflicts
