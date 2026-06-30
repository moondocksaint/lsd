"""PixelRAG visual backend — optional, requires `pip install lsd[visual]`.

This is a thin translation wrapper. It maps:
  - LSD's call contract  →  pixelrag's API
  - pixelrag's output    →  LSD's VisualResult

The actual pixelrag API (v0.3.0+):
  from pixelrag_render import render_url
  tiles = render_url(url, output_dir=str(out))
  # Returns a list of tile file paths.
  # Tiles are at: <output_dir>/<stem>.png.tiles/tile_NNNN.jpg
  # A tiles.json manifest is also written alongside the tiles.

Install:
  pip install pixelrag              # core render only
  pip install 'pixelrag[playwright]'  # full rendering with Playwright/CDP

Rendering notes:
  - Use tile_height=1568 for Claude vision (images > 1568px long-edge are downscaled
    and text becomes unreadable)
  - Use wait_network_idle=True for JS-heavy / SPA pages; without it the page may
    be captured before client-rendered content appears

When (if) LSD forks and owns the full visual stack:
  1. Create lsd/backends/native_visual.py implementing IngestionBackend.
  2. Update get_visual_backend() in lsd/backends/__init__.py to prefer it.
  3. This file becomes a shim or gets removed.
  4. Nothing outside lsd/backends/ changes.

Swap-candidate triggers: see ROADMAP.md § Architectural principles.
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
            from pixelrag_render import render_url  # noqa: F401, PLC0415
            return True
        except ImportError:
            return False

    def render(self, url: str, output_dir: str) -> VisualResult:
        """Render url to screenshot tiles via pixelrag.

        Translates pixelrag's output into LSD's VisualResult contract.
        If pixelrag's API changes, only this method needs updating.
        """
        from pixelrag_render import render_url  # noqa: PLC0415

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # render_url returns a list of tile file paths (str or Path).
        # Tile naming pattern: <out>/<stem>.png.tiles/tile_NNNN.jpg
        tile_paths = render_url(url, output_dir=str(out))

        tiles = [Path(t) for t in tile_paths]
        full_screenshot = tiles[0] if tiles else None

        return VisualResult(
            url=url,
            rendered_at=datetime.now(timezone.utc).isoformat(),
            full_screenshot=full_screenshot,
            tiles=tiles,
            backend="pixelrag",
        )
