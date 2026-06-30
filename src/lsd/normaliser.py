"""Normalise a FetchResult into a clean source artifact."""

from __future__ import annotations

import hashlib
import re

from lsd.models import FetchResult


def normalise(fetch: FetchResult) -> str:
    """Return a clean normalised markdown string from a FetchResult.

    This is what gets written to source.md and hashed for change detection.
    """
    lines = [
        f"# Source — {fetch.title}",
        "",
        f"- Canonical URL: {fetch.canonical_url}",
        f"- Retrieved: {fetch.fetched_at}",
        f"- Word count: {fetch.word_count}",
        "",
        "## Content",
        "",
        _clean(fetch.text),
    ]
    return "\n".join(lines)


def content_hash(normalised: str) -> str:
    """Return a stable SHA-256 hex digest of the normalised content."""
    return hashlib.sha256(normalised.encode()).hexdigest()[:16]


def _clean(text: str) -> str:
    """Remove noise: collapse whitespace, strip lone punctuation lines."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    lines = [ln for ln in text.splitlines() if not re.fullmatch(r"[\W]+", ln.strip()) or not ln.strip()]
    return "\n".join(lines).strip()
