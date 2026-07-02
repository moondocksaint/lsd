"""Normalise a FetchResult into a clean source artifact.

Audit fix (v0.5): The hash is computed on content-only text, with the
fetched_at timestamp stripped before hashing. This makes normalized_hash
reproducible across runs on identical content — the previous version
included the timestamp in the hashed string, making every run produce a
different hash even on an unchanged page.
"""

from __future__ import annotations

import hashlib
import re

from lsd.models import FetchResult

# Marker line written into source.md for human readability but excluded
# from the hash computation.
_RETRIEVED_PREFIX = "- Retrieved:"


def normalise(fetch: FetchResult) -> str:
    """Return a clean normalised markdown string from a FetchResult.

    This is what gets written to source.md and hashed for change detection.
    The fetched_at timestamp line is included in the display output but
    excluded from the hash (see content_hash()).
    """
    lines = [
        f"# Source — {fetch.title}",
        "",
        f"- Canonical URL: {fetch.canonical_url}",
        f"{_RETRIEVED_PREFIX} {fetch.fetched_at}",   # display only, not hashed
        f"- Word count: {fetch.word_count}",
        "",
        "## Content",
        "",
        _clean(fetch.text),
    ]
    return "\n".join(lines)


def content_hash(normalised: str) -> str:
    """Return a stable SHA-256 hex digest of the normalised content.

    Excludes the fetched_at timestamp line so the hash is reproducible
    across runs on identical source content.
    """
    hashable = "\n".join(
        ln for ln in normalised.splitlines()
        if not ln.startswith(_RETRIEVED_PREFIX)
    )
    return hashlib.sha256(hashable.encode()).hexdigest()[:16]


def _clean(text: str) -> str:
    """Remove noise: collapse whitespace, strip lone punctuation lines."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    lines = [
        ln for ln in text.splitlines()
        if not re.fullmatch(r"[\W]+", ln.strip()) or not ln.strip()
    ]
    return "\n".join(lines).strip()
