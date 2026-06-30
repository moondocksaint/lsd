"""Naive retrieval backend for LSD v0.4.

Strategy: full-context stuffing — return the first k chunks from each
source in order, with no embedding or ranking. When combined source text
fits within the token budget, this is equivalent to sending everything
to the LLM.

This is the v0.4 default. It is intentionally simple: zero extra
dependencies, deterministic output, easy to test. Replace it via the
registry in retrieval/__init__.py when grounding accuracy matters more
than operational simplicity.

Swap-candidate criteria:
  Replace this backend when any alternative scores >15% better on the
  v0.4 eval suite's grounding accuracy metric (claim → source passage
  hit rate across the standard case set). The first strong candidates
  are BM25RetrievalBackend (sparse keyword, no GPU, good for structured
  docs) and a dense embedding backend once a hosted embeddings API is
  available. See ROADMAP.md § Swap-candidate criteria.
"""

from __future__ import annotations

import logging

from lsd.models import IndexedSource, Passage, RetrievalIndex
from lsd.retrieval.base import RetrievalBackend

log = logging.getLogger(__name__)

# Approximate chars-per-token for rough token budget estimation.
# Conservative estimate (English prose is ~4 chars/token; we use 3.5 to
# account for code, tables, and markdown symbols).
_CHARS_PER_TOKEN = 3.5

# Default chunk size in characters. Chosen to give ~350 tokens per chunk,
# which fits comfortably in most LLM context windows even at high k.
_DEFAULT_CHUNK_CHARS = 1_200

# Default token threshold: warn and truncate when combined sources exceed
# this many estimated tokens. Matches the 50K threshold in ROADMAP.md.
DEFAULT_TOKEN_THRESHOLD = 50_000


class NaiveRetrievalBackend(RetrievalBackend):
    """Full-context stuffing retrieval backend (v0.4 default).

    Chunks each source into fixed-size windows. retrieve() returns the
    top-k chunks by simple linear scan — first k chunks from sources
    sorted by original index. No embedding, no ranking.

    This gives adequate recall when combined sources are within the token
    budget. For larger corpora, replace with BM25 or a dense backend.
    """

    def __init__(
        self,
        chunk_chars: int = _DEFAULT_CHUNK_CHARS,
        token_threshold: int = DEFAULT_TOKEN_THRESHOLD,
    ) -> None:
        self._chunk_chars = chunk_chars
        self._token_threshold = token_threshold

    @property
    def name(self) -> str:
        return "naive"

    def index(self, sources: list[IndexedSource]) -> RetrievalIndex:
        """Chunk all sources and store chunks in the index state."""
        chunks: list[Passage] = []
        total_chars = sum(len(s.text) for s in sources)
        estimated_tokens = total_chars / _CHARS_PER_TOKEN

        if estimated_tokens > self._token_threshold:
            log.warning(
                "Combined sources are ~%d estimated tokens (threshold: %d). "
                "The naive backend will truncate to the token budget. "
                "Consider reducing the number of sources or switching to a "
                "RAG backend (--retrieval-backend bm25 or colbert) for "
                "better grounding on large corpora.",
                int(estimated_tokens),
                self._token_threshold,
            )

        for source in sorted(sources, key=lambda s: s.index):
            text = source.text
            offset = 0
            while offset < len(text):
                chunk_text = text[offset: offset + self._chunk_chars]
                chunks.append(Passage(
                    text=chunk_text,
                    source_index=source.index,
                    source_url=source.url,
                    source_file=source.source_file,
                    char_offset=offset,
                    score=0.0,
                ))
                offset += self._chunk_chars

        return RetrievalIndex(
            backend_name=self.name,
            source_count=len(sources),
            total_chars=total_chars,
            _state={"chunks": chunks, "token_threshold": self._token_threshold},
        )

    def retrieve(
        self,
        index: RetrievalIndex,
        query: str,
        k: int = 5,
    ) -> list[Passage]:
        """Return the first k chunks, respecting the token budget.

        The naive backend ignores the query (no ranking). It returns
        chunks in source order, capped at the token budget.

        Args:
            index:  RetrievalIndex from index().
            query:  Query string (ignored in naive mode).
            k:      Maximum chunks to return.

        Returns:
            Up to k Passage objects in source order.
        """
        state = index._state
        chunks: list[Passage] = state["chunks"]
        token_threshold: int = state["token_threshold"]

        # Cap to token budget
        budget_chars = int(token_threshold * _CHARS_PER_TOKEN)
        selected: list[Passage] = []
        used_chars = 0
        for chunk in chunks:
            if len(selected) >= k:
                break
            if used_chars + len(chunk.text) > budget_chars:
                # Include a truncated final chunk so context isn't hard-cut
                remaining = budget_chars - used_chars
                if remaining > 100:
                    truncated = Passage(
                        text=chunk.text[:remaining] + "\n[...truncated by token budget]",
                        source_index=chunk.source_index,
                        source_url=chunk.source_url,
                        source_file=chunk.source_file,
                        char_offset=chunk.char_offset,
                        score=chunk.score,
                    )
                    selected.append(truncated)
                break
            selected.append(chunk)
            used_chars += len(chunk.text)

        return selected


def estimate_tokens(text: str) -> int:
    """Rough token count estimate for a string. Not model-specific."""
    return int(len(text) / _CHARS_PER_TOKEN)


def combined_token_estimate(sources: list[IndexedSource]) -> int:
    """Estimate total tokens across all sources."""
    return estimate_tokens("".join(s.text for s in sources))
