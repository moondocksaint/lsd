"""Tests for lsd.normaliser."""

from lsd.normaliser import content_hash, normalise
from lsd.models import FetchResult


def _make_fetch(**kwargs) -> FetchResult:
    defaults = dict(
        url="https://example.com",
        canonical_url="https://example.com",
        title="Test Page",
        text="Hello world. This is a test.",
        html="<html><body><p>Hello world.</p></body></html>",
        fetched_at="2026-06-30T00:00:00Z",
        http_status=200,
        word_count=6,
    )
    defaults.update(kwargs)
    return FetchResult(**defaults)


def test_normalise_contains_title():
    result = normalise(_make_fetch())
    assert "Test Page" in result


def test_normalise_contains_url():
    result = normalise(_make_fetch())
    assert "https://example.com" in result


def test_normalise_contains_text():
    result = normalise(_make_fetch())
    assert "Hello world" in result


def test_content_hash_stable():
    f = _make_fetch()
    assert content_hash(normalise(f)) == content_hash(normalise(f))


def test_content_hash_changes_on_text_change():
    f1 = _make_fetch(text="version one")
    f2 = _make_fetch(text="version two")
    assert content_hash(normalise(f1)) != content_hash(normalise(f2))
