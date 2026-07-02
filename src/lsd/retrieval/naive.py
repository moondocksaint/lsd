"""Naive retrieval backend for LSD v0.4.

Audit fix (v0.5): retrieve() now sets RetrievalIndex.was_truncated = True
when the token budget is hit, so callers (writer, CLI) can surface this
rather than silently discarding chunks.

Swap-candidate criteria: replace when any alternative scores >15% better
on grounding accuracy across the standard eval case set. First candidates:
BM25 (sparse keyword, no GPU, good for structured docs) or a dense
embedding backend once a hosted embeddings API is available.
"""

from __future__ import annotations

import logging

from lsd.models import IndexedSource, Passage, RetrievalIndex
from lsd.retrieval.base import RetrievalBackend

log = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 3.5
_DEFAULT_CHUNK_CHARS = 1_200
DEFAULT_TOKEN_THRESHOLD = 50_000


class NaiveRetrievalBackend(RetrievalBackend):
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
        chunks: list[Passage] = []
        total_chars = sum(len(s.text) for s in sources)
        estimated_tokens = total_chars / _CHARS_PER_TOKEN
        if estimated_tokens > self._token_threshold:
            log.warning(
                "Combined sources are ~%d estimated tokens (threshold: %d). "
                "The naive backend will truncate to the token budget.",
                int(estimated_tokens), self._token_threshold,
            )
        for source in sorted(sources, key=lambda s: s.index):
            text = source.text
            offset = 0
            while offset < len(text):
                chunks.append(Passage(
                    text=text[offset: offset + self._chunk_chars],
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
            was_truncated=False,
            _state={"chunks": chunks, "token_threshold": self._token_threshold},
        )

    def retrieve(self, index: RetrievalIndex, query: str, k: int = 5) -> list[Passage]:
        state = index._state
        chunks: list[Passage] = state["chunks"]
        token_threshold: int = state["token_threshold"]
        budget_chars = int(token_threshold * _CHARS_PER_TOKEN)
        selected: list[Passage] = []
        used_chars = 0
        for chunk in chunks:
            if len(selected) >= k:
                break
            if used_chars + len(chunk.text) > budget_chars:
                remaining = budget_chars - used_chars
                if remaining > 100:
                    selected.append(Passage(
                        text=chunk.text[:remaining] + "\n[...truncated by token budget]",
                        source_index=chunk.source_index,
                        source_url=chunk.source_url,
                        source_file=chunk.source_file,
                        char_offset=chunk.char_offset,
                        score=chunk.score,
                    ))
                # Audit fix: mark the index as truncated
                index.was_truncated = True
                break
            selected.append(chunk)
            used_chars += len(chunk.text)
        return selected


def estimate_tokens(text: str) -> int:
    return int(len(text) / _CHARS_PER_TOKEN)


def combined_token_estimate(sources: list[IndexedSource]) -> int:
    return estimate_tokens("".join(s.text for s in sources))
