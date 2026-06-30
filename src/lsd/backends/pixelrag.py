"""PixelRAG visual backend — optional, requires `pip install lsd[visual]`.

This is a thin translation wrapper. It maps:
  - LSD's call contract  →  pixelrag's API
  - pixelrag's output    →  LSD's VisualResult

When (if) LSD forks and owns the full visual stack:
  1. Create lsd/backends/native_visual.py implementing IngestionBackend.
  2. Update get_visual_backend() in lsd/backends/__init__.py to prefer it.
  3. This file becomes a shim or gets removed.
  4. Nothing outside lsd/backends/ changes.

The fork path is entirely contained here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from lsd.backends.base import IngestionBackend
from lsd.models import VisualResult


class PixelRAGBackend(IngestionBackend):
    """Visual backend wrapping the pixelrag package."""

    def is_available(self) -> bool:
        try:
            import pixelrag  # noqa: F401, PLC0415
            return True
        except ImportError:
            return False

    def render(self, url: str, output_dir: str) -> VisualResult:
        """Render url to screenshot tiles via pixelrag.

        Translates pixelrag's output into LSD's VisualResult contract.
        If pixelrag's API changes, only this method needs updating.
        """
        import pixelrag  # noqa: PLC0415

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # --- pixelrag call ---
        # pixelrag.render() returns a RenderResult with .screenshot (Path)
        # and .tiles (list[Path]). Translate into LSD's VisualResult.
        result = pixelrag.render(url, output_dir=str(out))

        return VisualResult(
            url=url,
            rendered_at=datetime.now(timezone.utc).isoformat(),
            full_screenshot=Path(result.screenshot) if result.screenshot else None,
            tiles=[Path(t) for t in result.tiles],
            backend="pixelrag",
        )
