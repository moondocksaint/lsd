"""Text backend — always available, no optional dependencies.

This is LSD's baseline. It does not produce visual artifacts.
Used for text-first ingestion and as a fallback when no visual
backend is available.
"""

from __future__ import annotations


class TextBackend:
    """Marker class for text-only ingestion.

    The text backend is handled by the fetcher + normaliser directly;
    this class exists so the router and writer have a consistent object
    to reference rather than using None to mean 'text path'.
    """

    name: str = "text"

    def is_available(self) -> bool:
        return True
