"""Abstract base class for all LSD LLM compiler backends.

Every provider (Anthropic, OpenAI-compatible, future) implements this
single interface. The compiler calls complete() and never touches a
provider SDK directly.

Swap-candidate triggers: see ROADMAP.md § Architectural principles.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class LLMBackend(ABC):
    """Contract every LLM compiler backend must fulfil."""

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        """Send a system + user prompt and return the model's text response.

        Args:
            system: System prompt (instructions, persona, constraints).
            user:   User message (the actual task + source content).
            max_tokens: Maximum tokens to generate.

        Returns:
            The model's response as a plain string.

        Raises:
            LLMBackendError: On any provider-level failure (auth, rate limit,
                             network error, malformed response).
        """
        ...

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Human-readable model identifier for logging and SKILL.md caveats."""
        ...
