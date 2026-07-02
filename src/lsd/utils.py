"""Shared utilities for LSD.

Canonical home for helpers that would otherwise be duplicated across modules:

  - ``slugify``            — one slug implementation used by both compiler.py
                             and cli.py.
  - ``CHARS_PER_TOKEN``    — one chars-per-token constant used by the pipeline
                             and the retrieval backend.
  - ``estimate_tokens`` /
    ``combined_token_estimate`` — one token-budget estimator used by the
                             single-source path, the multi-source path, and
                             the retrieval token-threshold checks.
"""

from __future__ import annotations

import re
from typing import Iterable, Protocol

# Rough chars-per-token estimate for budget calculations.
# Single source of truth — update here if calibration changes.
CHARS_PER_TOKEN: float = 3.5


class _HasText(Protocol):
    text: str


def estimate_tokens(text: str) -> int:
    """Rough token count for a string (``len(text) / CHARS_PER_TOKEN``)."""
    return int(len(text) / CHARS_PER_TOKEN)


def combined_token_estimate(sources: Iterable[_HasText]) -> int:
    """Estimated token count across objects exposing a ``.text`` attribute.

    Sums the character lengths first, then divides once, so the result matches
    ``estimate_tokens`` on the concatenated text rather than accumulating
    per-source rounding error.
    """
    return int(sum(len(s.text) for s in sources) / CHARS_PER_TOKEN)


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
