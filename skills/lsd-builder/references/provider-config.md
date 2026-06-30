# LSD Provider Configuration Reference

LSD selects its LLM backend entirely through environment variables. No config
file is required. All variables are optional; LSD falls back to an offline
heuristic skeleton if no provider is configured.

---

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `LSD_LLM_PROVIDER` | Yes (for LLM use) | `anthropic` or `openai-compat` |
| `LSD_MODEL` | Yes (for LLM use) | Model identifier string |
| `LSD_LLM_BASE_URL` | `openai-compat` only | API base URL (no trailing slash) |
| `LSD_LLM_API_KEY` | `openai-compat` only | API key for the provider |
| `ANTHROPIC_API_KEY` | `anthropic` only | Anthropic API key |
| `LSD_OMIT_MAX_TOKENS` | Optional | Set to `1` to suppress `max_tokens` in requests |

---

## Provider recipes

### OpenAI

```bash
export LSD_LLM_PROVIDER=openai-compat
export LSD_LLM_BASE_URL=https://api.openai.com/v1
export LSD_LLM_API_KEY=sk-...
export LSD_MODEL=gpt-4o          # or gpt-4o-mini, o3-mini, etc.
```

### Anthropic (Claude)

```bash
export LSD_LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
export LSD_MODEL=claude-3-5-sonnet-20241022   # or claude-opus-4, etc.
```

### OpenRouter (single API for 100+ models)

```bash
export LSD_LLM_PROVIDER=openai-compat
export LSD_LLM_BASE_URL=https://openrouter.ai/api/v1
export LSD_LLM_API_KEY=sk-or-...
export LSD_MODEL=anthropic/claude-3-5-sonnet   # OpenRouter model IDs
# Also valid: meta-llama/llama-3.1-405b-instruct, google/gemini-pro-1.5, etc.
```

### Inception dLLM (mercury diffusion models)

Inception's API is OpenAI-compatible but does not support `max_tokens`.
Set `LSD_OMIT_MAX_TOKENS=1` to suppress that parameter.

```bash
export LSD_LLM_PROVIDER=openai-compat
export LSD_LLM_BASE_URL=https://api.inceptionlabs.ai/v1
export LSD_LLM_API_KEY=sk-...
export LSD_MODEL=mercury-2
export LSD_OMIT_MAX_TOKENS=1
```

Known model IDs (as of 2026-06-30):
`mercury`, `mercury-2`, `mercury-coder`, `mercury-coder-small`, `mercury-small`

### Groq

```bash
export LSD_LLM_PROVIDER=openai-compat
export LSD_LLM_BASE_URL=https://api.groq.com/openai/v1
export LSD_LLM_API_KEY=gsk_...
export LSD_MODEL=llama-3.1-70b-versatile   # or mixtral-8x7b-32768, etc.
```

### Together AI

```bash
export LSD_LLM_PROVIDER=openai-compat
export LSD_LLM_BASE_URL=https://api.together.xyz/v1
export LSD_LLM_API_KEY=...
export LSD_MODEL=meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo
```

### Local / self-hosted (Ollama, LM Studio, vLLM)

```bash
export LSD_LLM_PROVIDER=openai-compat
export LSD_LLM_BASE_URL=http://localhost:11434/v1   # Ollama default
# export LSD_LLM_BASE_URL=http://localhost:1234/v1  # LM Studio default
export LSD_LLM_API_KEY=ollama                        # placeholder; Ollama ignores it
export LSD_MODEL=llama3.2:3b                         # any locally pulled model
```

---

## Offline fallback

If `LSD_LLM_PROVIDER` is not set, LSD uses a heuristic skeleton compiler that
fills `SKILL.md` sections from extracted headings and key sentences. This is
fast and deterministic but produces lower-quality output than the LLM path.
The rubric score for heuristic output is typically 6–8/14.

---

## Adding a new provider

1. If the provider exposes an OpenAI-compatible `/chat/completions` endpoint,
   it works with `openai-compat` immediately — no code changes needed.
2. If the provider has a proprietary API surface:
   - Subclass `LLMBackend` in `src/lsd/llm/`
   - Implement `complete(prompt: str, **kwargs) -> str`
   - Add a branch in `get_llm_backend()` in `src/lsd/llm/__init__.py`
   - Add a new env var convention (e.g. `LSD_LLM_PROVIDER=myvendor`)
3. Document the new provider in this file.

**Swap-candidate trigger:** A new provider or model achieves rubric ≥ 13/14 on
the eval suite at meaningfully lower cost than the current default, or offers a
capability (structured output, longer context, faster latency) that closes a
known gap in the distillation quality.
