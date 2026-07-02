"""Tests for the v0.4 retrieval backend system."""
from __future__ import annotations

import pytest

from lsd.models import IndexedSource, Passage, RetrievalIndex
from lsd.retrieval import get_retrieval_backend
from lsd.retrieval.base import RetrievalBackend
from lsd.retrieval.naive import NaiveRetrievalBackend
from lsd.utils import combined_token_estimate, estimate_tokens


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_source(index: int, text: str, url: str = "") -> IndexedSource:
    return IndexedSource(
        index=index,
        url=url or f"https://source-{index}.example.com",
        source_file=f"source-{index}.md",
        text=text,
    )


# ---------------------------------------------------------------------------
# RetrievalBackend ABC
# ---------------------------------------------------------------------------

def test_naive_backend_implements_abc():
    backend = NaiveRetrievalBackend()
    assert isinstance(backend, RetrievalBackend)


def test_naive_backend_name():
    assert NaiveRetrievalBackend().name == "naive"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_get_retrieval_backend_default():
    backend = get_retrieval_backend()
    assert isinstance(backend, NaiveRetrievalBackend)


def test_get_retrieval_backend_by_name():
    backend = get_retrieval_backend("naive")
    assert isinstance(backend, NaiveRetrievalBackend)


def test_get_retrieval_backend_unknown_raises():
    with pytest.raises(ValueError, match="Unknown retrieval backend"):
        get_retrieval_backend("nonexistent_backend_xyz")


def test_get_retrieval_backend_env_override(monkeypatch):
    monkeypatch.setenv("LSD_RETRIEVAL_BACKEND", "naive")
    backend = get_retrieval_backend()
    assert backend.name == "naive"


# ---------------------------------------------------------------------------
# NaiveRetrievalBackend.index()
# ---------------------------------------------------------------------------

def test_index_returns_retrieval_index():
    backend = NaiveRetrievalBackend()
    sources = [_make_source(1, "Hello world. " * 10)]
    index = backend.index(sources)
    assert isinstance(index, RetrievalIndex)
    assert index.backend_name == "naive"
    assert index.source_count == 1


def test_index_stores_total_chars():
    backend = NaiveRetrievalBackend()
    text = "x" * 1000
    sources = [_make_source(1, text)]
    index = backend.index(sources)
    assert index.total_chars == 1000


def test_index_multiple_sources():
    backend = NaiveRetrievalBackend()
    sources = [
        _make_source(1, "a" * 500),
        _make_source(2, "b" * 700),
    ]
    index = backend.index(sources)
    assert index.source_count == 2
    assert index.total_chars == 1200


def test_index_empty_sources():
    backend = NaiveRetrievalBackend()
    index = backend.index([])
    assert index.source_count == 0
    assert index.total_chars == 0


# ---------------------------------------------------------------------------
# NaiveRetrievalBackend.retrieve()
# ---------------------------------------------------------------------------

def test_retrieve_returns_passages():
    backend = NaiveRetrievalBackend(chunk_chars=100)
    text = "Hello world. " * 50  # ~650 chars
    sources = [_make_source(1, text)]
    index = backend.index(sources)
    passages = backend.retrieve(index, "hello", k=3)
    assert isinstance(passages, list)
    assert all(isinstance(p, Passage) for p in passages)


def test_retrieve_respects_k():
    backend = NaiveRetrievalBackend(chunk_chars=50)
    text = "x" * 500  # 10 chunks
    sources = [_make_source(1, text)]
    index = backend.index(sources)
    passages = backend.retrieve(index, "anything", k=3)
    assert len(passages) <= 3


def test_retrieve_passage_provenance():
    backend = NaiveRetrievalBackend(chunk_chars=200)
    text = "Test content. " * 20
    sources = [_make_source(1, text, url="https://example.com")]
    index = backend.index(sources)
    passages = backend.retrieve(index, "test", k=1)
    assert len(passages) >= 1
    p = passages[0]
    assert p.source_url == "https://example.com"
    assert p.source_file == "source-1.md"
    assert p.source_index == 1
    assert p.char_offset == 0


def test_retrieve_char_offsets_increment():
    backend = NaiveRetrievalBackend(chunk_chars=100)
    text = "a" * 300
    sources = [_make_source(1, text)]
    index = backend.index(sources)
    passages = backend.retrieve(index, "a", k=10)
    assert passages[0].char_offset == 0
    assert passages[1].char_offset == 100
    assert passages[2].char_offset == 200


def test_retrieve_preserves_source_order():
    """Passages from source 1 should come before source 2."""
    backend = NaiveRetrievalBackend(chunk_chars=200)
    sources = [
        _make_source(1, "Source one content. " * 10),
        _make_source(2, "Source two content. " * 10),
    ]
    index = backend.index(sources)
    passages = backend.retrieve(index, "content", k=10)
    source_indices = [p.source_index for p in passages]
    # All source-1 chunks before source-2 chunks
    assert source_indices == sorted(source_indices)


def test_retrieve_respects_token_budget():
    """With a very tight budget, retrieve should truncate."""
    # 100-char budget = ~28 tokens
    backend = NaiveRetrievalBackend(chunk_chars=50, token_threshold=10)
    text = "x" * 500
    sources = [_make_source(1, text)]
    index = backend.index(sources)
    passages = backend.retrieve(index, "x", k=20)
    total_chars = sum(len(p.text) for p in passages)
    # Should be well under 500 chars (the full text)
    assert total_chars < 500


# ---------------------------------------------------------------------------
# Token estimation helpers
# ---------------------------------------------------------------------------

def test_estimate_tokens_rough():
    text = "a" * 350  # ~100 tokens at 3.5 chars/token
    assert estimate_tokens(text) == 100


def test_combined_token_estimate():
    sources = [
        _make_source(1, "a" * 350),
        _make_source(2, "b" * 350),
    ]
    assert combined_token_estimate(sources) == 200


def test_token_threshold_warning_logged(caplog):
    import logging
    backend = NaiveRetrievalBackend(token_threshold=10)
    # 100 chars >> 10-token threshold
    text = "Hello world. " * 10
    sources = [_make_source(1, text)]
    with caplog.at_level(logging.WARNING, logger="lsd.retrieval.naive"):
        backend.index(sources)
    assert any("token" in r.message.lower() for r in caplog.records)
