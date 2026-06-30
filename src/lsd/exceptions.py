"""LSD-specific exceptions."""

from __future__ import annotations


class LSDError(Exception):
    """Base exception for all LSD pipeline errors.

    Raised for user-actionable conditions (gated sources, unsupported
    source types, etc.) that should produce a clean CLI error message
    rather than a stack trace.
    """
