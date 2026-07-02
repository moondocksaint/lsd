# Configuring an LLM provider (and keeping keys safe)

Without an LLM provider, `lsd build` falls back to a heuristic skeleton — every
compiled section (including `## Gotchas`) is a `<!-- TODO -->` placeholder.
Configuring a provider unlocks real compiler output. This page covers how, and how
to do it without leaking the key.

## How LSD reads the key

LSD reads configuration from the environment only (`src/lsd/llm/__init__.py`):

| Variable | Meaning |
|----------|---------|
| `LSD_LLM_PROVIDER` | `anthropic` (default) or `openai-compat` |
| `LSD_MODEL` | model name (provider-specific) |
| `ANTHROPIC_API_KEY` | key for the `anthropic` provider |
| `LSD_LLM_API_KEY` | key for the `openai-compat` provider |
| `LSD_LLM_BASE_URL` | endpoint for `openai-compat` (OpenAI, OpenRouter, Inception, Ollama…) |
| `LSD_OMIT_MAX_TOKENS` | set to `1` for providers that reject `max_tokens` (e.g. Inception dLLM) |

**What LSD does with the key:** it is read from `os.environ`, held in memory on the
backend instance, and sent only as an auth header (`Authorization: Bearer …` /
`x-api-key`) to the endpoint you configure. It is **never** written to a generated
package, `metadata.json`, or logs, and nothing outside `src/lsd/llm/` reads it.
The one thing to watch: only point `LSD_LLM_BASE_URL` at a host you trust — that is
where your key gets sent.

## Local setup (recommended for one-off runs and baseline refreshes)

1. `cp .env.example .env` and fill in real values. `.env` is gitignored (as are
   `.env.*`, `*.key`, `*.pem`); the real key never enters version control.
2. Load it for a run and go:
   ```bash
   set -a; source .env; set +a
   lsd build <url>
   ```
   Or use `direnv`, or export the vars inline for a single command. Prefer a
   per-project key with a spend cap, and rotate it periodically.
3. Never paste the key on a shared terminal, in a commit, or into a chat/PR.

## CI setup (only if you want provider-backed jobs to run automatically)

- Store the key as a GitHub Actions **encrypted secret** (repo or, better, an
  **Environment** secret) and reference it as `${{ secrets.ANTHROPIC_API_KEY }}`.
  GitHub encrypts secrets at rest and masks them in logs.
- **Never expose the secret to untrusted code.** The existing `green-gate` workflow
  runs on `pull_request` and deliberately uses **no secrets** (unit tests are offline
  and mock the network) — keep it that way. Any job that needs the key must be gated
  to a trusted context: `workflow_dispatch`, `push` to `main`, or an `environment:`
  with required reviewers. Do **not** use `pull_request_target` with a checkout of the
  PR head plus secrets — that is the classic secret-exfiltration hole for fork PRs.
- Avoid `echo`-ing the key, `set -x` around it, or DEBUG-level HTTP logging.
- Consider enabling GitHub secret scanning + push protection on the repo so an
  accidental key commit is blocked at push time.

## Regenerating eval baselines (Phase 1 #3)

Baseline regeneration needs a provider **and** network fetch access, so run it where
you have both — locally is simplest and keeps the key on one machine.

- **Wikipedia case** — to stay a meaningful regression anchor, rebuild it with the
  **same model** that produced the committed baseline (Inception dLLM `mercury-2`,
  per `HANDOFF.md`), then:
  ```bash
  lsd eval tests/cases/wikipedia-ai-writing --init --force
  ```
- **PixelRAG case** — no baseline exists yet; any configured provider works:
  ```bash
  lsd eval tests/cases/pixelrag-repo --init
  ```

Committed baseline files (`SKILL.md`, `metadata.json`, …) record the *model id*
(`compiler_model`) and generated content — never the key — so they are safe to commit.
