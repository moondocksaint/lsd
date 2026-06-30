"""Abstract base class for all LSD ingestion backends."""

from __future__ import annotations

from abc import ABC, abstractmethod

from lsd.models import VisualResult


class IngestionBackend(ABC):
    """Contract every visual backend must fulfil.

    TextBackend does not subclass this — text fetching is handled
    directly by the fetcher. This ABC is only for visual backends
    that produce VisualResult artifacts.
    """

    @abstractmethod
    def render(self, url: str, output_dir: str) -> VisualResult:
        """Render a URL to screenshot tiles.

        Args:
            url: The canonical URL to render.
            output_dir: Directory to write tile files into.

        Returns:
            A VisualResult with paths to the full screenshot and tiles.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if this backend's dependencies are satisfied."""
        ...

    @property
    def name(self) -> str:
        """Human-readable backend name for logging."""
        return self.__class__.__name__
