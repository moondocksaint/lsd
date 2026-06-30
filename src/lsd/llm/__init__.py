"""LLM backend factory for the LSD compiler.

Provider selection (in priority order):

1. Explicit backend instance passed to compile_skill(llm_backend=...) — for
   programmatic use and testing.

2. Environment variables:

   LSD_LLM_PROVIDER   "anthropic" (default) | "openai-compat"
   LSD_MODEL          Model name (provider-specific)
   ANTHROPIC_API_KEY  API key for Anthropic provider
   LSD_LLM_BASE_URL   Base URL for openai-compat provider
   LSD_LLM_API_KEY    API key for openai-compat provider

   OpenRouter example:
     LSD_LLM_PROVIDER=openai-compat
     LSD_LLM_BASE_URL=https://openrouter.ai/api/v1
     LSD_LLM_API_KEY=sk-or-...
     LSD_MODEL=anthropic/claude-3-haiku

   Inception dLLM example:
     LSD_LLM_PROVIDER=openai-compat
     LSD_LLM_BASE_URL=https://api.inceptionlabs.ai/v1
     LSD_LLM_API_KEY=...
     LSD_MODEL=mercury-coder-small

   Ollama (local, no key needed) example:
     LSD_LLM_PROVIDER=openai-compat
     LSD_LLM_BASE_URL=http://localhost:11434/v1
     LSD_LLM_API_KEY=ollama
     LSD_MODEL=llama3.2

3. Returns None if no provider can be configured → compiler falls back to
   the heuristic skeleton.

Adding a new provider:
  1. Create lsd/llm/<name>.py implementing LLMBackend.
  2. Add a branch in get_llm_backend() below.
  3. Document the env vars in this docstring.
  No other files need to change.
"""

from __future__ import annotations

import os

from lsd.llm.base import LLMBackend

# Default models per provider (overridden by LSD_MODEL)
_DEFAULTS: dict[str, str] = {
    "anthropic": "claude-haiku-3-5",
    "openai-compat": "gpt-4o-mini",
}


def get_llm_backend() -> LLMBackend | None:
    """Return the configured LLM backend, or None if no provider is available."""
    provider = os.environ.get("LSD_LLM_PROVIDER", "anthropic").lower()
    model = os.environ.get("LSD_MODEL", _DEFAULTS.get(provider, ""))

    if provider == "anthropic":
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return None
        from lsd.llm.anthropic import AnthropicBackend  # noqa: PLC0415
        return AnthropicBackend(api_key=api_key, model=model)

    if provider == "openai-compat":
        api_key = os.environ.get("LSD_LLM_API_KEY", "")
        base_url = os.environ.get("LSD_LLM_BASE_URL", "https://api.openai.com/v1")
        if not api_key:
            return None
        from lsd.llm.openai_compat import OpenAICompatBackend  # noqa: PLC0415
        return OpenAICompatBackend(api_key=api_key, model=model, base_url=base_url)

    # Unknown provider — warn and return None so the build doesn't crash
    import logging  # noqa: PLC0415
    logging.getLogger(__name__).warning(
        "Unknown LSD_LLM_PROVIDER=%r — falling back to heuristic skeleton. "
        "Valid values: anthropic, openai-compat",
        provider,
    )
    return None
