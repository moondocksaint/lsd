# LSD Build Provenance

This file documents the lineage of this repository — which tools, models,
and sessions produced each major artifact. It exists so future contributors
understand where things came from and can interpret `compiler_model` fields
in generated skill packages correctly.

---

## Repository origin

**Session:** Perplexity Computer (chat session, 2026-06-30)
**Model:** Unknown — Perplexity auto-selected the best available model for
the task. The session is preserved as a Markdown attachment in the project
owner's Perplexity history.

**What was built in that session:**
- Initial repo scaffold (`b2e4e3e8`) — full directory structure, README,
  spec, examples, test harness
- CLI stub with adapter architecture, models, backends, pipeline stages
  (`05934239`)

The skill package artifacts from that session (any SKILL.md generated
interactively during exploration) were produced by Perplexity's auto-selected
model. No `compiler_model` field exists on those artifacts because the field
was not yet part of the schema.

---

## v0.1 — Pipeline fixes and first green build

**Session:** Perplexity Computer (same thread, 2026-06-30)
**Commits:** `cad6f154` through `21c92bc9`
**Work done by:** Perplexity Computer agent (bash + GitHub API push pattern)

- Fixed `pyproject.toml` build-backend (hard blocker)
- Ran `lsd build` on Wikipedia AI-writing URL — confirmed 7-file output
- Fixed duplicate CLI command, double-fetch, unused import
- Wrote comprehensive ROADMAP.md with architectural principles

**First real `lsd build` output:** Generated using the heuristic skeleton
(no LLM configured). `compiler_model` = null / not yet tracked.

---

## v0.2 — LLM compiler + multi-provider LLM backend

**Session:** Perplexity Computer (same thread, 2026-06-30)
**Commits:** `fc8f6bba`, `26b0b7c5`, `78ac411e`
**Work done by:** Perplexity Computer agent (bash + GitHub API)

- `compiler.py`: LLM pass with offline heuristic fallback
- `fetcher.py`: source type detection
- `models.py`: `SourceType` + `source_type` field on `FetchResult`
- `llm/` subpackage: `LLMBackend` ABC, `AnthropicBackend`,
  `OpenAICompatBackend` (covers OpenRouter / Inception / Groq /
  Together / Ollama / LMStudio / vLLM)
- Test suite: 42 tests total

---

## v0.3 — Multi-source build + conflict detection

**Session:** Perplexity Computer (same thread, 2026-06-30)
**Commit:** `6990ffe0`
**Work done by:** Perplexity Computer agent (bash + GitHub API)

- `models.py`: `SourceEntry`, `Conflict`, `ConflictReport`,
  `MultiSourceBuildContext`
- `conflict_detector.py`: heuristic gap / contradiction / overlap analysis
- `pipeline.py`: `build_multi()` with parallel fetch via ThreadPoolExecutor
- `opportunity_mapper.py`: `map_opportunities_multi()`
- `writer.py`: `write_multi_package()` — per-source files, conflicts.md,
  sources-index.md
- `cli.py`: `build` command accepts multiple URLs (`nargs=-1`)
- Tests: 57 total

---

## v0.4 — Modular retrieval backend + eval harness

**Session:** Perplexity Computer (same thread, 2026-06-30)
**Commits:** `f3708537`, `9504ad98`, `37ab2f04`
**Work done by:** Perplexity Computer agent (bash + GitHub API)

- `retrieval/` subpackage: `RetrievalBackend` ABC, `NaiveRetrievalBackend`
  (full-context stuffing, 50K token threshold), factory + registry
- `compiler.py`: `compile_skill_multi()` with retrieval-grounded LLM pass,
  `[Source N]` provenance citations
- `pipeline.py`: retrieval wired into `build_multi()`
- `cli.py`: `--retrieval-backend`, `--token-threshold` flags; `lsd eval`
  command with rubric scoring + expected/ diff
- `compiler_model` added as first-class field in `SKILL.md` frontmatter,
  `metadata.json`, and `README.md`
- Tests: 81 total

**First LLM-compiled skill package (eval baseline):**
- URL: https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing
- Provider: Inception dLLM (`https://api.inceptionlabs.ai/v1`)
- Model: `mercury-2`
- Rubric score: 14/14
- Committed as: `tests/cases/wikipedia-ai-writing/expected/`
- `compiler_model` in that snapshot: `api/mercury-2`

**Note on `openai_compat.py`:** Inception dLLM only supports `temperature`
and `stop` sampling parameters — not `max_tokens`. Added `LSD_OMIT_MAX_TOKENS=1`
env var to handle this. Known Inception model IDs as of 2026-06-30:
`mercury`, `mercury-2`, `mercury-coder`, `mercury-coder-small`, `mercury-small`.

---

## Eval diff normalization policy

The `lsd eval` diff harness normalizes two volatile fields on **both sides**
before comparing, so the `expected/` snapshot never needs manual scrubbing:

1. **ISO-8601 timestamps** → `__TIMESTAMP__`
   (`generated_at`, `last_checked_at`, `last_successful_fetch_at`)

2. **Content hashes** → `__CONTENT_HASH__`
   (`source_dependency.normalized_hash` — changes when a live source page
   is edited between runs, e.g. Wikipedia)

`SKILL.md` is the **only intentional DIFFER** between runs: the LLM compiler
is non-deterministic, so the structure is stable but the prose differs. The
rubric score (target: ≥12/14) is the quality gate, not line-exact diff.

---

## How to add a new eval baseline

1. Run `lsd build <url> --output tests/cases/<case-name>/`
2. Manually review against `tests/rubric.md` (target ≥12/14)
3. Confirm score with `lsd eval tests/cases/<case-name>/`
4. If ≥12/14: commit `tests/cases/<case-name>/expected/` (all files except
   `source.md` — too large, not useful for diffing)
5. Record in this file under a new dated entry
