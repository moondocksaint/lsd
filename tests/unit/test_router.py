"""Tests for lsd.router."""

from lsd.router import route
from lsd.models import FetchResult, SourceFit


def _make_fetch(url: str = "https://example.com") -> FetchResult:
    return FetchResult(
        url=url,
        canonical_url=url,
        title="Test",
        text="",
        html="",
        fetched_at="2026-06-30T00:00:00Z",
        http_status=200,
        word_count=0,
    )


def _neutral_fit() -> SourceFit:
    return SourceFit()


def test_text_first_default():
    mode, _ = route(_make_fetch(), _neutral_fit(), visual_backend_available=False)
    assert mode == "text-first"


def test_github_url_with_visual_backend_gives_hybrid():
    mode, _ = route(
        _make_fetch("https://github.com/owner/repo"),
        SourceFit(composability="high", procedure_density="high"),
        visual_backend_available=True,
    )
    assert mode == "hybrid"


def test_github_url_without_visual_backend_gives_text_first():
    mode, notes = route(
        _make_fetch("https://github.com/owner/repo"),
        SourceFit(composability="high", procedure_density="high"),
        visual_backend_available=False,
    )
    assert mode == "text-first"
    assert "pip install lsd[visual]" in notes


def test_mode_override_respected():
    mode, notes = route(
        _make_fetch(),
        _neutral_fit(),
        visual_backend_available=False,
        override="hybrid",
    )
    assert mode == "hybrid"
    assert "overridden" in notes
