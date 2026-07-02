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

Ponytail fixes:
  - TextBackend removed: it was a marker class with no callers.
    "No visual backend" is represented as None throughout the pipeline.
  - get_visual_backend(): ImportError now caught separately from
    instantiation errors so backend construction failures propagate.
"""

from lsd.backends.base import IngestionBackend


def get_visual_backend() -> IngestionBackend | None:
    """Return the best available visual backend, or None.

    Priority order:
      1. PixelRAGBackend  (if pixelrag is installed)
      2. NativeVisualBackend  (future — not yet implemented)
      3. None  (caller should fall back to text-first)
    """
    try:
        from lsd.backends.pixelrag import PixelRAGBackend  # noqa: PLC0415
    except ImportError:
        return None
    b = PixelRAGBackend()
    if b.is_available():
        return b
    return None


__all__ = ["IngestionBackend", "get_visual_backend"]
