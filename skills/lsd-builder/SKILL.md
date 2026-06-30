---
name: lsd-builder
description: >
  Build a structured, versioned agent skill package from one or more source URLs
  using LSD (Link-to-Skill Distiller). Load this skill whenever the user says
  "build a skill from", "distill this URL into a skill", "run lsd build", "create
  a skill package from a link", "generate a skill from", or provides one or more
  URLs and asks to turn them into an agent skill. Also load when the user asks to
  check a skill package for staleness ("lsd check"), run an eval against a baseline
  ("lsd eval"), or inspect the source-dependency layer of a package.
compatibility:
  tools: [bash]
  requires_env: [LSD_LLM_PROVIDER, LSD_MODEL]
---

# LSD Builder Skill

LSD (Link-to-Skill Distiller) converts one or more source URLs into a versioned,
structured agent skill package. Each package contains a `SKILL.md` (loadable by
any agent), provenance metadata, source-dependency tracking, and optionally a
conflict report (multi-source builds).

Load `references/provider-config.md` for LLM provider setup.
Load `references/output-schema.md` for the full package file schema.
Load `references/rubric.md` for eval scoring criteria.

---

## Quick start

```bash
# Single source
lsd build https://example.com/docs/api --output ./my-skill/

# Multi-source (conflict detection enabled automatically)
lsd build https://source1.com https://source2.com --output ./my-skill/

# Check a package for drift (normalized_hash changed)
lsd check ./my-skill/

# Eval against a committed expected/ snapshot
lsd eval tests/cases/my-case/
```

---

## Installation

```bash
pip install lsd
# or from source:
git clone https://github.com/moondocksaint/lsd
cd lsd && pip install -e .
```

---

## LLM provider setup

LSD uses environment variables for all provider configuration. No config file
is needed. See `references/provider-config.md` for the full list of providers
and env var combinations.

**Minimal setup (OpenAI-compatible provider):**
```bash
export LSD_LLM_PROVIDER=openai-compat
export LSD_LLM_BASE_URL=https://api.openai.com/v1   # or any compatible endpoint
export LSD_LLM_API_KEY=sk-...
export LSD_MODEL=gpt-4o
```

**Inception dLLM (mercury-2):**
```bash
export LSD_LLM_PROVIDER=openai-compat
export LSD_LLM_BASE_URL=https://api.inceptionlabs.ai/v1
export LSD_LLM_API_KEY=sk-...
export LSD_MODEL=mercury-2
export LSD_OMIT_MAX_TOKENS=1   # Inception does not support max_tokens
```

**Anthropic:**
```bash
export LSD_LLM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
export LSD_MODEL=claude-3-5-sonnet-20241022
```

---

## Output package structure

A single-source build produces:

```
<output-dir>/
  SKILL.md              # Loadable skill — Core principle, Workflow, Output format
  README.md             # Agent entry point: version, compiler_model, update workflow
  source.md             # Full normalized source text
  metadata.json         # Source dependency, compiler_model, artifact manifest
  source-policy.md      # Update policy and fallback chain
  skill-opportunities.md # Detected skill-building opportunities in the source
  extraction-report.md  # Pipeline run summary
  CHANGELOG.md          # Package-level change log
```

A multi-source build additionally produces:

```
  source-1.md … source-N.md   # Per-source normalized text
  sources-index.md             # Table of all sources with fetch status
  conflicts.md                 # Cross-source conflicts: gaps, contradictions, overlaps
  index.md                     # Package overview
```

See `references/output-schema.md` for field-level documentation.

---

## Source-dependency tracking (LSD moat)

Every package records a `source_dependency` block in `metadata.json`:

```json
{
  "source_dependency": {
    "url": "https://example.com/docs/api",
    "normalized_hash": "sha256:abc123...",
    "last_checked_at": "2026-06-30T10:00:00Z",
    "update_policy": "check-monthly",
    "fallback_chain": ["https://web.archive.org/..."]
  }
}
```

`lsd check` re-fetches the URL and compares `normalized_hash`. If the hash has
changed, it reports drift and recommends a rebuild. No other skill-building tool
tracks this layer.

`README.md` inside the package includes a "Version & update workflow" section
that any agent can read to determine whether the package needs refreshing.

---

## Multi-source conflict detection

When two or more URLs are passed to `lsd build`, the conflict detector runs
automatically and writes `conflicts.md`. Three conflict types are detected:

| Type | Description |
|------|-------------|
| `gap` | A heading/topic present in one source is absent from another |
| `contradiction` | Negation patterns near shared key terms suggest opposing claims |
| `overlap` | Near-duplicate sentences indicating redundant coverage |

The user (or agent) must resolve conflicts before the distilled `SKILL.md` can
be trusted. Resolution guidance is written into `conflicts.md`.

---

## Modular retrieval backend

Multi-source builds route through a pluggable retrieval backend:

```
src/lsd/retrieval/
  base.py          # RetrievalBackend ABC  (index / retrieve)
  naive.py         # NaiveRetrievalBackend — full-context stuffing, 50K token guard
  __init__.py      # get_retrieval_backend() factory + registry
```

**Swap-candidate criteria (when to replace NaiveRetrievalBackend):**
- Combined token estimate exceeds 50K tokens AND quality degrades (rubric < 12/14)
- A dense-vector or BM25 backend achieves measurably higher rubric scores at equal
  cost on the eval suite
- A NotebookLM-quality RAG API becomes accessible via a simple HTTP call

To add a new backend: subclass `RetrievalBackend`, implement `index()` and
`retrieve()`, and register it in `get_retrieval_backend()`.

**CLI flags:**
```bash
lsd build <urls> --retrieval-backend naive   # default
lsd build <urls> --token-threshold 100000    # override token budget
```

---

## Modular LLM backend

```
src/lsd/llm/
  base.py            # LLMBackend ABC
  anthropic.py       # AnthropicBackend
  openai_compat.py   # OpenAICompatBackend (covers OpenRouter, Inception,
                     #   Groq, Together, Ollama, LM Studio, vLLM, any
                     #   OpenAI-compatible surface)
  __init__.py        # get_llm_backend() factory
```

**Swap-candidate criteria (when to add a new LLM backend):**
- A new provider offers a substantially better price/quality ratio on the eval
  rubric (target: ≥12/14 at lower cost)
- A new diffusion LLM or structured-output-native model achieves higher rubric
  scores on the SKILL.md generation task
- OpenRouter gains a provider not yet covered by the `openai-compat` path

To add a new provider: subclass `LLMBackend`, implement `complete()`, and add
a branch in `get_llm_backend()`.

---

## Modular PixelRAG backend

```
src/lsd/backends/
  pixelrag.py        # PixelRAGBackend — renders URL to image tiles,
                     #   then extracts text via vision LLM
  text.py            # TextBackend — default HTTP fetch + HTML/PDF parse
```

**Swap-candidate criteria (when to replace PixelRAGBackend):**
- A new screenshot-to-structured-data API achieves better extraction fidelity on
  rendered/JS-heavy pages
- PixelRAG (PyPI: `pixelrag-render`) releases a version with a changed API surface
- A vision model substantially outperforms the current tile-based approach

**Note on PixelRAG API (as of v0.4):**
```python
from pixelrag_render import render_url
tiles = render_url(url, output_dir=str(out))
```
Package: `pixelrag-render` v0.3.0 (Berkeley SkyLab).

---

## Eval harness

```bash
lsd eval tests/cases/<case-name>/
```

Scores the current pipeline output against a committed `expected/` snapshot:

- Rubric scoring: 7 criteria × 2 points = 14 max (see `references/rubric.md`)
- Diff: normalizes timestamps → `__TIMESTAMP__` and content hashes →
  `__CONTENT_HASH__` on both sides before comparing
- `SKILL.md` is the only expected DIFFER (non-deterministic LLM prose)
- Quality gate: rubric ≥ 12/14

---

## Versioning and `compiler_model` provenance

`compiler_model` is a first-class field in three places:

1. `SKILL.md` YAML frontmatter: `compiler_model: api/mercury-2`
2. `metadata.json`: `package.compiler_model`
3. `README.md` provenance table

This lets any agent loading the skill package know which model generated the
distilled content, enabling reproducibility audits and trust calibration.

---

## v0.5 roadmap items

See `ROADMAP.md` in the repository root for the full backlog. Key upcoming items:

- **NotebookLM-quality RAG** — plug-in replacement for `NaiveRetrievalBackend`
  when the combined token budget is exceeded or rubric scores plateau
- **Timestamp-aware source watching** — agents check `README.md` → `normalized_hash`
  to detect drift without re-running the full pipeline
- **pyproject.toml version bump** — currently `0.2.0`, should track package version
