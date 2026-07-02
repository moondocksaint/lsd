# LSD Roadmap

LSD (Link-to-Skill Designer) is a build tool that turns URLs into marketplace-ready AI skill
packages. It targets three distribution surfaces: a local CLI for developers, an installable
meta-skill for Claude/Cursor/Codex environments, and a hosted web product for everyone else.

---

## Architectural principles

These apply across the entire roadmap and should be enforced at every PR.

### LSD owns the contracts, not the implementations

Every stage that touches an external technique — visual rendering, retrieval, LLM compilation
— sits behind an ABC with a narrow, stable interface. The default implementation ships with
the package. Alternatives are drop-in: implement the interface, register in the factory,
done. Nothing upstream changes.

This pattern already exists in `backends/` for visual rendering. It extends to `retrieval/`
(v0.4) and will extend to `compiler/` if/when multiple LLM backends are needed.

### Swap-candidate criteria (universal)

Any pluggable component — visual backend, retrieval backend, or LLM compiler backend —
becomes a candidate for replacement when **any one** of the following is true:

1. **Quality regression**: the current implementation scores materially worse than an
   alternative on the regression harness (v0.4 eval suite). Threshold: >10% drop in rubric
   score on the standard case set, or a new technique demonstrably beats it by >15%.
2. **Maintenance signal**: no upstream releases for 6+ months, open CVEs, or the project
   is archived/abandoned.
3. **Constraint change**: a new deployment target (serverless, air-gapped, browser-native)
   makes the current dependency chain untenable.
4. **Paradigm shift**: a new approach collapses two pipeline steps into one with equal or
   better quality (e.g. a vision-native model that renders-and-reads in a single pass,
   eliminating the separate screenshot + embed steps).

When a trigger is met: implement the alternative behind the existing interface, run it
through the regression harness side-by-side with the current default, document the
delta, and promote only if the results justify the migration cost.

### The pipeline is the source of truth

`pipeline.build()` is the canonical implementation. The CLI, the web API, and the
meta-skill are all shells around it. Any change to pipeline behavior must be reflected
in all three surfaces and covered by the regression harness before merging.

---

## Where we are right now — v0.1 ✅

The text-first pipeline is fully implemented and working end-to-end.

- [x] Repo structure, meta-skill spec, two hand-authored reference packages
- [x] CLI entry point: `lsd build <url>`
- [x] Fetch → classify → route → normalise → map → compile → write pipeline
- [x] Package writer: all 7 output files (SKILL.md, source.md, skill-opportunities.md,
      metadata.json, source-policy.md, extraction-report.md, CHANGELOG.md)
- [x] Source-dependency tracking: canonical URL, normalized hash, update policy, fallback chain
- [x] 16 unit tests passing
- [x] Clean install: `pip install -e ".[dev]"` works

**Known gaps at v0.1:**
- `SKILL.md` compiler produces structural skeleton with `<!-- TODO -->` placeholders — not yet
  self-contained or usable
- PixelRAG backend adapter has wrong API surface (fixable, see v0.2)
- Single URL input only
- CLI only — no meta-skill packaging, no web product

---

## Immediate next steps — v0.2

### LLM compiler pass (highest priority)

Replace the `<!-- TODO -->` stubs in `compiler.py` with a real LLM call that fills in
`Core principle`, `Workflow`, and `Output format` from the source content. This is the
single biggest quality unlock — it's what makes the output self-contained and usable,
and it unblocks all three distribution surfaces.

Implementation notes:
- Add an optional `--model` flag (default: `claude-haiku-3-5` for cost; override to sonnet/opus)
- Compiler receives the full `source.md` content and the `OpportunityMap` as context
- Output is a filled SKILL.md that passes the existing 14-point quality rubric in `tests/rubric.md`
- Keep the heuristic skeleton as a fallback when no API key is present (offline mode)

### Visual rendering backend fix and modularity

Rewrite `backends/pixelrag.py` against the actual `pixelrag` API surface:
- Install: `pip install pixelrag` (core) or `pip install 'pixelrag[playwright]'` (full rendering)
- Render call: `from pixelrag_render import render_url; tiles = render_url(url, output_dir)`
- Output: tiled JPEGs at `<dir>/<stem>.png.tiles/tile_NNNN.jpg` + `tiles.json` manifest
- Use `--tile-height 1568 --wait-network-idle` for JS-heavy pages
- Update `pyproject.toml` visual extra: `pixelrag[playwright]`

The existing `backends/` adapter pattern already makes visual rendering modular — the
`IngestionBackend` ABC in `backends/base.py` is the seam. This is intentional and permanent:
LSD owns the pipeline contracts, not the rendering implementation. Future backends (a
native Playwright backend, a cloud screenshot API, a future vision-native renderer) are
drop-in replacements that implement `render()` and `is_available()` and register in
`backends/__init__.py`. Nothing upstream changes.

Swap-candidate triggers follow the universal criteria in the Architectural principles
section above. For this backend specifically, trigger #4 (paradigm shift) is the most
likely: a vision-native model that renders-and-reads in a single pass would eliminate
the screenshot-then-embed two-step. To swap: write `backends/<name>.py`, register it
in `backends/__init__.py`, run regression harness side-by-side, promote if justified.

### Source type expansion: links to non-HTML content

URLs don't always return HTML. LSD needs graceful handling for:

| Link type | Strategy |
|---|---|
| **PDF** (`/something.pdf`, `Content-Type: application/pdf`) | Use `pixelrag` PDF renderer (`pixelshot document.pdf`) — already supported by PixelRAG |
| **Image** (JPG, PNG, GIF, WebP) | Pass directly to visual backend; skip text extraction |
| **Google Docs / Slides / Sheets** | Export URL rewrite (`/export?format=pdf`) then treat as PDF |
| **LinkedIn posts/profiles** | HTML fetch works but requires User-Agent spoofing; flag as `social` source type with a stability warning |
| **Gated / auth-required pages** | Detect HTTP 401/403/redirect-to-login; emit a clear error with instructions for manual export |
| **YouTube / video URLs** | Out of scope for v0.2 — defer; emit "video source not yet supported" |

Each type is detected in `fetcher.py` via Content-Type + URL pattern before any parsing begins.

### Code cleanup

- Fix two remaining ruff warnings in `writer.py` (unused `re` import, unused `fit` local)
- Add a `lsd check <url>` smoke test that validates an existing package against a re-fetch
- Write a fetcher test using `pytest-httpx` (already declared but unused)

---

## v0.3 — Multi-source support

Multiple URLs as input is the next structural milestone. It affects models, pipeline, and output
schema — design it right here rather than migrating later.

### CLI

```
lsd build <url1> <url2> [<url3> ...]
```

Sources are fetched concurrently. Each gets its own classification pass.

### Source provenance (the "honest recall" principle)

When multiple sources are combined, provenance must be preserved at every level:

- **Separate source files**: `source-1.md`, `source-2.md`, ... with a `sources-index.md` that
  records title, URL, fetch date, and hash per source. Never merge sources into one file — this
  is what makes honest recall possible and allows per-source refresh.
- **`metadata.json` schema**: `source_dependency` becomes `source_dependencies: [...]`, each
  entry with its own canonical URL, hash, last-checked, and update policy.
- **`SKILL.md` attribution**: every claim or rule in the compiled skill that comes from a specific
  source is traceable. The compiler LLM prompt includes provenance markers in the context.

### Conflict detection

When multiple sources are provided, the opportunity mapper runs a conflict analysis pass:

- Detect contradictions: two sources that give opposing rules for the same situation
- Detect gaps: source A covers step 1-3, source B covers step 5-7, step 4 is unaddressed
- Detect overlap: near-duplicate rules across sources (flag for deduplication)

The output is a `conflicts.md` file in the package and a summary section in `skill-opportunities.md`.
The compiler is instructed to surface unresolved conflicts in the SKILL.md rather than silently
picking one source — the user decides how to resolve them before promoting the skill.

### RAG quality (deferred to v0.4, placeholder here)

For multi-source compilation with large sources (combined token count > context window), a
lightweight RAG pass is needed to retrieve the most relevant chunks per compiled section.
Target: NotebookLM-quality grounding — every claim in the compiled skill is anchored to a
specific passage in a specific source file.

This is deliberately deferred to v0.4 to avoid premature complexity. For v0.3, the constraint
is: if combined sources exceed a threshold (configurable, default 50K tokens), LSD warns and
asks the user to either reduce sources or accept that the compiler will truncate.

---

## v0.4 — Quality, eval, and RAG

### Regression harness

Wire the existing `tests/cases/*/` structure into a real diff-based eval:
- `tests/cases/*/expected/` directories (currently absent) generated from reference packages
- `lsd eval <case>` command: re-runs the pipeline and diffs against expected output
- Quantitative scoring against `tests/rubric.md` (14-point quality rubric)
- CI gate: block merges if rubric score drops below threshold

### RAG-grounded compilation — modular retrieval backend

Retrieval techniques are improving fast. The implementation must be pluggable: a concrete
technique ships as the v0.4 default, but it can be swapped out entirely without touching
the compiler or any other pipeline stage.

The seam follows the same pattern as `backends/` for visual ingestion — an abstract base
class with a narrow interface:

```python
class RetrievalBackend(ABC):
    @abstractmethod
    def index(self, sources: list[IndexedSource]) -> RetrievalIndex: ...

    @abstractmethod
    def retrieve(self, index: RetrievalIndex, query: str, k: int) -> list[Passage]: ...
```

`Passage` always carries: text, source file path, canonical URL, and character offset —
provenance is never lost regardless of which backend produced it. The compiler never calls
an embedding model directly; it always calls `retrieve()`.

**v0.4 default implementation**: chunk → embed with a lightweight model → FAISS flat index
stored inside the package directory (no hosted infrastructure required). Passable quality,
zero operational overhead.

**Status note (current as of v0.5.0):** the shipped default is `NaiveRetrievalBackend` —
fixed-size chunking with a token-budget guard, not the embedding/FAISS default described
above. That upgrade remains open; see "Open gaps for the next contributor" below.

**Pluggable alternatives** (drop-in, same interface):
- `PixelRAGRetrievalBackend` — calls `api.pixelrag.ai` or a local PixelRAG serve instance;
  retrieves over screenshot tiles rather than text chunks (better for visual-heavy sources)
- `BM25RetrievalBackend` — sparse keyword retrieval; fast, no GPU, good for structured docs
- `ColBERTRetrievalBackend` — late-interaction dense retrieval; higher accuracy on long docs
- `HostedAPIRetrievalBackend` — delegates to any OpenAI-compatible `/embeddings` + vector DB
- `OllamaRetrievalBackend` — local embeddings via Ollama for offline / air-gapped mode

The active backend is selected via `--retrieval-backend` flag or `retrieval.backend` in a
project config file. New backends are registered in `retrieval/__init__.py` — no changes
needed anywhere else in the pipeline.

Swap-candidate triggers follow the universal criteria in the Architectural principles
section above. For retrieval specifically, trigger #1 (quality) is the most actionable:
the v0.4 eval suite scores every retrieval backend on grounding accuracy (claim → source
passage hit rate) and recall across the standard case set. Any new technique that beats
the default by >15% on that metric is a promotion candidate.

This is the path to NotebookLM-quality grounding. Every compiled section cites its source
passage + URL + character range, regardless of which backend produced the retrieval.

### Source refresh and diff

- `lsd refresh <package-dir>`: re-fetches canonical URL, compares normalized hash
- Classifies change as trivial / moderate / material (existing policy schema)
- Trivial: log only. Moderate: prepare update candidate. Material: new source version + skill draft.
- Outputs `CHANGELOG.md` entry and optionally re-runs the compiler if material change detected

---

## v0.5 — Distribution surfaces

### Meta-skill packaging (Claude / Cursor / Codex)

Package LSD itself as an installable skill for AI coding environments:

- **Claude**: submit `skills/lsd-builder/` to the [Anthropic skills marketplace](https://github.com/anthropics/skills).
  The meta-skill accepts a URL (or list of URLs) as input and runs the full pipeline inline,
  without requiring a local CLI install. Evals and iteration loop per Anthropic skill-creator process.
- **Cursor**: `.cursor/rules` entry + shell script that calls `lsd build` if installed, or falls
  back to a bundled TypeScript stub that calls the hosted API.
- **Codex/ChatGPT**: GPT Action backed by the hosted API (see web product below).

### Web product

A hosted interface for users who don't want a CLI:

1. Paste one or more URLs
2. Agent classifies sources, shows the opportunity map, surfaces conflicts
3. User iterates in a chat: "focus on the reviewer skill", "add this second source", "resolve the
   conflict in section 3 by preferring source 1"
4. Download the skill package as a zip, or one-click install to Claude/Cursor

BYOK (Bring Your Own Key): users provide their own Anthropic/OpenAI/Gemini API key for the
compilation step. This removes hosting cost for the LLM calls and lets users choose their model.

Backend: FastAPI wrapper around `pipeline.build()` — the pipeline is already the reference
implementation. Frontend: minimal React/Next.js, no heavy framework.

The web product also serves as the GPT Action endpoint for Codex/ChatGPT integration.

---

## Larger vision

LSD's core bet is that **the web is already full of knowledge that should be skills** — API docs,
style guides, compliance pages, research papers, editorial guidelines, competitor playbooks —
and the workflow to turn any of them into a reusable, citable, version-controlled skill package
should take seconds, not hours.

The source-dependency layer is the permanent differentiator: every generated skill knows where
it came from, when it was last checked, what changed, and how to fall back if the source
disappears. No other skill-building tool tracks this. It's what makes LSD output appropriate
for teams and production use, not just personal productivity.

The longer arc:

- **Skill marketplace listings**: LSD-generated packages submitted to Claude, Cursor, and
  ChatGPT marketplaces, with LSD credited as the build tool (distribution + branding)
- **Skill update subscriptions**: users subscribe to source URLs; LSD monitors for material
  changes and proposes skill updates automatically
- **Organization skill libraries**: teams run LSD against their internal documentation, wikis,
  and runbooks to build a private skill library that stays in sync with the source docs
- **Skill composition**: combine two or more existing skill packages into a composite skill,
  with conflict detection and provenance preserved across the merge
- **Offline / air-gapped mode**: for enterprises that cannot send source content to external
  LLMs — runs the compilation step against a local model (Ollama, llama.cpp)

---

## Open gaps for the next contributor

Current, concrete gaps in the shipped implementation — as opposed to the aspirational
version-by-version narrative above, some of which was superseded by simpler decisions made
along the way (see the retrieval status note above). For the freshest actionable list —
including anything gated only on configuring an LLM provider or regenerating an eval
baseline, not on external dependencies — see README.md § Suggested next steps. HANDOFF.md
records the rationale behind past decisions.

### Blocked on an external dependency or upstream release

- **PixelRAG visual backend** — `src/lsd/backends/pixelrag.py` wraps `pixelrag-render`,
  which has not been publicly released. The `IngestionBackend` interface and adapter are
  already in place; visual-first ingestion falls back to text-first until the package ships.
- **Retrieval backend upgrade** — the shipped v0.4 default is `NaiveRetrievalBackend`
  (fixed-size chunking + a token-budget guard, no embeddings). `RetrievalBackend` (see
  `retrieval/base.py`) makes BM25, ColBERT, or a hosted-embeddings backend a drop-in swap
  once one is available and clears the swap-candidate criteria above.
- **Semantic-drift embedding similarity** — `lsd check` classifies drift with a lexical
  `difflib.SequenceMatcher` ratio, which is blind to *semantic drift* (same words,
  reorganised meaning). The swap point is `cli._content_similarity(old_lines, new_lines,
  similarity_fn=None)`: pass an embedding-backed cosine `similarity_fn` once a low-latency
  embeddings endpoint is available — nothing else in the drift path changes. No embedding
  API is wired into any LSD backend today (the LLM backends are chat-only; retrieval is
  lexical), and `scripts/check-drift.py` is deliberately `httpx`-only, so this can't be
  built as a live feature yet.

### Backlog — no external blocker, just unscheduled

- **Expand the eval case set** — there is currently one *baselined* eval case
  (`tests/cases/wikipedia-ai-writing/`, with a committed `expected/` snapshot).
  A second case directory, `tests/cases/pixelrag-repo/`, exists with an
  `input.json` but no baseline yet — `lsd eval tests/cases/pixelrag-repo --init`
  would establish one. A hybrid case (code documentation) and a visual-first
  case (once PixelRAG is available) would give the regression harness broader
  coverage still.
- **Description optimizer** — the meta-skill generates descriptions from source intent.
  Running the Anthropic `skill-creator`'s `run_loop.py`-style trigger optimization on
  generated descriptions would likely improve agent recall.
- **MCP server scaffold** — when the opportunity mapper detects an `mcp_server` tool
  candidate, offer to scaffold a minimal MCP server stub instead of just describing the
  opportunity in `skill-opportunities.md`.

---

## Execution plan (sequenced)

The order in which to work the gaps above and in README.md § Suggested next steps.
Phases are ordered by leverage and dependency — earlier phases unblock later ones. This
section only *sequences* the work; the detailed descriptions live in § Open gaps and
README § Suggested next steps, and are referenced by name here rather than repeated.

### Phase 0 — Reconciliation ✅ done

Docs reconciled with code; `main` is the single source of truth. The historical
divergence (a broken commit that reached `main` while docs claimed a green suite) is
what the CI gate in Phase 1 exists to prevent.

### Phase 1 — Guardrail + quality unlock (highest ROI, minimal code)

1. **CI gate ✅ shipped with this plan** — `.github/workflows/ci.yml` runs `ruff check`,
   `mypy --strict`, and `pytest -q` on every push to `main` and every PR. Nothing that
   fails the green gate can reach `main` again. *No external blocker.*
2. **Configure an LLM provider** — set `ANTHROPIC_API_KEY`, or point
   `LSD_LLM_PROVIDER=openai-compat` at an endpoint (env vars in `src/lsd/llm/__init__.py`).
   Converts the heuristic `<!-- TODO -->` compiler output — including `## Gotchas` — into
   real content. This gates all output quality. *Blocked only on a key.*
3. **Regenerate eval baselines** once (2) is set — the committed
   `tests/cases/wikipedia-ai-writing/expected/` snapshot predates `## Gotchas` and now
   reports `DIFFER`; rebuild it with the recorded model via `lsd eval … --init --force`,
   then baseline `tests/cases/pixelrag-repo/` (needs fetch access to the source URL).

### Phase 2 — Improve the reconciled codebase (no external blocker)

4. **Description optimizer** (§ Backlog).
5. **MCP server scaffold** (§ Backlog).
6. **Expand the eval case set** (§ Backlog) using a *stable, fetchable* source — avoid
   live pages whose content drifts and makes a committed baseline flaky.

### Phase 3 — Dependency-blocked seams (do when an embeddings endpoint exists)

7. **Retrieval backend upgrade** (§ Open gaps) — implement an embedding/BM25/ColBERT
   `RetrievalBackend` behind the existing ABC; promote per the swap-candidate criteria.
8. **Semantic-drift similarity** (§ Open gaps) — inject an embedding-backed cosine
   `similarity_fn` into `cli._content_similarity`; keep `scripts/check-drift.py` httpx-only.
9. **PixelRAG visual backend** (§ Open gaps) — activate when `pixelrag-render` ships.

### Phase 4 — Distribution surfaces (largest)

10. Meta-skill marketplace submission; web product (a FastAPI wrapper around
    `pipeline.build()` — the pipeline is already the single source of truth); Cursor/Codex
    actions. See § v0.5 — Distribution surfaces and § Larger vision.

---

## What is deliberately out of scope

- **Video / audio sources**: transcription is a different problem; defer indefinitely
- **Auth-gated sources**: LSD will never store credentials; gated pages must be exported manually
- **Real-time / live data sources**: skills are point-in-time snapshots; live feeds are not skills
- **Skill execution / runtime**: LSD builds skills; it does not run them or provide an agent runtime
