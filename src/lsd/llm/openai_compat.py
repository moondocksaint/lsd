"""OpenAI-compatible backend for the LSD LLM compiler.

Works with any provider that implements the OpenAI /v1/chat/completions
API surface — no extra SDK required, just httpx (already a core dep).

Tested providers (set LSD_LLM_BASE_URL accordingly):

  Provider          Base URL
  --------          --------
  OpenAI            https://api.openai.com/v1
  OpenRouter        https://openrouter.ai/api/v1
  Inception dLLM    https://api.inceptionlabs.ai/v1
  Groq              https://api.groq.com/openai/v1
  Together AI       https://api.together.xyz/v1
  Ollama (local)    http://localhost:11434/v1
  LM Studio         http://localhost:1234/v1
  Any vLLM server   http://<host>:<port>/v1

No extra install needed — httpx is already in core deps.
"""

from __future__ import annotations

import httpx

from lsd.llm.base import LLMBackend

_DEFAULT_BASE_URL = "https://api.openai.com/v1"


class OpenAICompatBackend(LLMBackend):
    """LLM backend for any OpenAI /v1/chat/completions compatible API.

    Uses httpx directly — no openai SDK required.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: int = 120,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        # Some providers (e.g. OpenRouter) require extra headers for attribution
        self._extra_headers: dict[str, str] = extra_headers or {}

    @property
    def model_id(self) -> str:
        # Derive a friendly provider name from the base URL for logging
        provider = self._base_url.split("//")[-1].split("/")[0].split(".")[0]
        return f"{provider}/{self._model}"

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }
        payload = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        resp = httpx.post(
            f"{self._base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
