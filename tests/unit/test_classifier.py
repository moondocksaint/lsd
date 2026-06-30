"""Tests for lsd.classifier."""

from lsd.classifier import classify
from lsd.models import FetchResult


def _make_fetch(text: str, word_count: int = 100) -> FetchResult:
    return FetchResult(
        url="https://example.com",
        canonical_url="https://example.com",
        title="Test",
        text=text,
        html="",
        fetched_at="2026-06-30T00:00:00Z",
        http_status=200,
        word_count=word_count,
    )


def test_rule_dense_source():
    text = " ".join(["you should always avoid this heuristic guideline rule"] * 20)
    fit = classify(_make_fetch(text, word_count=len(text.split())))
    assert fit.rule_density in ("high", "medium")


def test_procedure_dense_source():
    text = " ".join(["step 1 install run configure pipeline workflow ```"] * 20)
    fit = classify(_make_fetch(text, word_count=len(text.split())))
    assert fit.procedure_density in ("high", "medium")


def test_low_signal_source():
    text = "The quick brown fox jumps over the lazy dog. " * 20
    fit = classify(_make_fetch(text, word_count=len(text.split())))
    assert fit.overall_fit in ("medium", "low")
