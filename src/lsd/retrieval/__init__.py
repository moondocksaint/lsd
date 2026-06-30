"""Retrieval backend registry for LSD v0.4.

Usage:
    from lsd.retrieval import get_retrieval_backend
    backend = get_retrieval_backend()          # default (naive)
    backend = get_retrieval_backend("naive")   # explicit
    backend = get_retrieval_backend("bm25")    # future backend

To register a new backend, add an entry to _REGISTRY below.
No other file needs to change.

Swap-candidate criteria (architectural principle):
  Any backend becomes a candidate for replacement when it scores materially
  worse than an alternative on the v0.4 eval suite (grounding accuracy:
  claim → source passage hit rate). Threshold: >15% improvement on the
  standard case set. See ROADMAP.md § Swap-candidate criteria.
"""

from __future__ import annotations

from lsd.retrieval.base import RetrievalBackend
from lsd.retrieval.naive import NaiveRetrievalBackend

# Registry: name → callable that returns a RetrievalBackend instance.
# Add new backends here; nothing else in the pipeline needs to change.
_REGISTRY: dict[str, type[RetrievalBackend]] = {
    "naive": NaiveRetrievalBackend,
    # "bm25": BM25RetrievalBackend,        # future
    # "colbert": ColBERTRetrievalBackend,   # future
    # "pixelrag": PixelRAGRetrievalBackend, # future
    # "ollama": OllamaRetrievalBackend,     # future
}

_DEFAULT_BACKEND = "naive"


def get_retrieval_backend(name: str | None = None) -> RetrievalBackend:
    """Return a RetrievalBackend instance by name.

    Args:
        name: Backend name from the registry. If None, uses the default
              ("naive"). Can be overridden via --retrieval-backend CLI flag
              or LSD_RETRIEVAL_BACKEND env var.

    Raises:
        ValueError: If the requested backend name is not registered.
    """
    import os
    resolved = name or os.environ.get("LSD_RETRIEVAL_BACKEND") or _DEFAULT_BACKEND
    if resolved not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"Unknown retrieval backend {resolved!r}. Available: {available}"
        )
    return _REGISTRY[resolved]()


__all__ = ["RetrievalBackend", "get_retrieval_backend"]
