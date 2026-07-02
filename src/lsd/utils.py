"""Shared utilities for LSD.

Ponytail fix: _slugify_name (compiler.py) and _slugify (cli.py) were two
slightly different implementations of the same slug logic. Canonical version
lives here; both callers import from lsd.utils.

Pre-release fix: _CHARS_PER_TOKEN was duplicated in pipeline.py and
retrieval/naive.py. Canonical constant lives here; both import from lsd.utils.
"""

from __future__ import annotations

import re

# Rough chars-per-token estimate for budget calculations.
# ponytail: single source of truth — was duplicated in pipeline.py and
# retrieval/naive.py. Update here if calibration changes.
CHARS_PER_TOKEN: float = 3.5


def slugify(text: str, max_len: int = 60) -> str:
    """Return a lowercase hyphen-slug from text, max_len chars.

    Agentskills spec: lowercase alphanumeric + hyphens only, no consecutive
    hyphens, no leading/trailing hyphens, max 64 chars.
    """
    s = text.lower()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-")
    return s[:max_len].rstrip("-")
