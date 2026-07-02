"""Ingestion mode router.

Decides text-first, hybrid, or visual-first based on source signals
and backend availability. This is the only place in LSD that looks
at both the source classification AND the available backends together.
"""

from __future__ import annotations

from lsd.models import FetchResult, IngestionMode, SourceFit

# URL patterns that suggest a hybrid source even before content analysis
HYBRID_URL_PATTERNS = [
    "github.com",
    "gitlab.com",
    "npmjs.com",
    "pypi.org",
    "crates.io",
    "pkg.go.dev",
]

# ponytail: APP_DOMAINS exported so opportunity_mapper.py can import it —
# single source of truth for "this URL is an interactive app".
APP_DOMAINS = [
    "app.",
    "dashboard.",
    "console.",
    "studio.",
    "figma.com",
    "miro.com",
    "airtable.com",
]

VISUAL_FIRST_URL_PATTERNS = APP_DOMAINS  # identical for now; extend here if non-app visual patterns emerge


def route(
    fetch: FetchResult,
    fit: SourceFit,
    visual_backend_available: bool,
    override: IngestionMode | None = None,
) -> tuple[IngestionMode, str]:
    """Return (mode, routing_notes).

    Args:
        fetch: The fetch result for the source URL.
        fit: The source fit classification.
        visual_backend_available: True if a visual backend is installed.
        override: User-supplied mode override; skips routing logic if set.

    Returns:
        A tuple of (chosen mode, human-readable routing rationale).
    """
    if override:
        return override, f"Mode overridden by user to '{override}'."

    url = fetch.canonical_url.lower()
    notes: list[str] = []

    # --- Visual-first signals ---
    if any(p in url for p in VISUAL_FIRST_URL_PATTERNS):
        notes.append("URL pattern suggests a dashboard or app interface.")
        if visual_backend_available:
            return "visual-first", " ".join(notes)
        notes.append("No visual backend available — falling back to text-first.")
        return "text-first", " ".join(notes)

    # --- Hybrid signals ---
    url_hybrid = any(p in url for p in HYBRID_URL_PATTERNS)
    content_visual = fit.composability == "high" and fit.procedure_density == "high"

    if url_hybrid or content_visual:
        notes.append(
            "URL pattern suggests a repository page." if url_hybrid
            else "Content signals suggest visual structure."
        )
        if visual_backend_available:
            return "hybrid", " ".join(notes)
        notes.append(
            "Visual backend (pixelrag) not installed — using text-first. "
            "Run `pip install lsd[visual]` to enable hybrid ingestion."
        )
        return "text-first", " ".join(notes)

    # --- Default: text-first ---
    notes.append("Prose-dominant source; text-first ingestion selected.")
    return "text-first", " ".join(notes)
