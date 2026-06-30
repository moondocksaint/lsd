"""Abstract base class for LSD retrieval backends.

Every retrieval backend must implement this interface. The compiler and
pipeline never call an embedding model or vector store directly — they
always go through retrieve().

The contract:
  1. Call index(sources) once to prepare the index.
  2. Call retrieve(index, query, k) one or more times to get passages.
  3. Passages always carry full provenance: source_url, source_file,
     char_offset — regardless of which backend produced them.

This is the seam that makes retrieval pluggable. Swap the backend by
implementing this ABC and registering it in retrieval/__init__.py.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from lsd.models import IndexedSource, Passage, RetrievalIndex


class RetrievalBackend(ABC):
    """Pluggable retrieval backend interface."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name, e.g. 'naive', 'bm25', 'colbert'."""

    @abstractmethod
    def index(self, sources: list[IndexedSource]) -> RetrievalIndex:
        """Prepare a retrieval index from a list of indexed sources.

        Called once per build. May chunk, embed, or otherwise preprocess
        the source texts. The returned RetrievalIndex is opaque to callers;
        pass it to retrieve() unchanged.

        Args:
            sources: List of IndexedSource objects (one per URL).

        Returns:
            A RetrievalIndex handle for subsequent retrieve() calls.
        """

    @abstractmethod
    def retrieve(
        self,
        index: RetrievalIndex,
        query: str,
        k: int = 5,
    ) -> list[Passage]:
        """Retrieve the k most relevant passages for a query.

        Args:
            index:  The RetrievalIndex returned by index().
            query:  Natural-language query string.
            k:      Maximum number of passages to return.

        Returns:
            List of Passage objects sorted by descending relevance score.
            Each Passage carries text, source provenance, and char_offset.
        """
