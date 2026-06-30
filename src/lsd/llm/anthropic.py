"""Anthropic backend for the LSD LLM compiler.

Requires: pip install lsd[anthropic]  (or pip install anthropic>=0.100)
"""

from __future__ import annotations

from lsd.llm.base import LLMBackend


class AnthropicBackend(LLMBackend):
    """LLM backend using the Anthropic Python SDK."""

    def __init__(self, api_key: str, model: str = "claude-haiku-3-5") -> None:
        self._api_key = api_key
        self._model = model

    @property
    def model_id(self) -> str:
        return f"anthropic/{self._model}"

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "Anthropic SDK not installed. Run: pip install 'lsd[anthropic]'"
            ) from exc

        client = anthropic.Anthropic(api_key=self._api_key)
        message = client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text.strip()
