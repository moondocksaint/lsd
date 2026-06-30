"""Ingestion backends for LSD.

The adapter pattern lives here. LSD's pipeline only ever sees
VisualResult (from lsd.models). Backends translate from their
own internal representations into that contract.

To add a new backend (including a future native fork):
  1. Create a new file in this directory.
  2. Subclass IngestionBackend from lsd.backends.base.
  3. Implement render() and is_available().
  4. Register it in get_visual_backend() below.

Nothing outside this package needs to change.
"""

from lsd.backends.base import IngestionBackend
from lsd.backends.text import TextBackend


def get_visual_backend() -> IngestionBackend | None:
    """Return the best available visual backend, or None.

    Priority order:
      1. PixelRAGBackend  (if pixelrag is installed)
      2. NativeVisualBackend  (future — not yet implemented)
      3. None  (caller should fall back to text-first)
    """
    try:
        from lsd.backends.pixelrag import PixelRAGBackend  # noqa: PLC0415
        b = PixelRAGBackend()
        if b.is_available():
            return b
    except ImportError:
        pass
    return None


__all__ = ["IngestionBackend", "TextBackend", "get_visual_backend"]
