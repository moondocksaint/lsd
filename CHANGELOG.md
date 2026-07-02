# Changelog

All notable changes to LSD are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

### Docs
- **Fixed five doc/code mismatches found by auditing docs against the branch**,
  rather than assuming prior doc edits were accurate: HANDOFF.md's header said
  "104 tests passing" while the suite has 116 (and the file's own later section
  already said 116); AGENTS.md's repository-layout tree omitted `validation.py`
  entirely; AGENTS.md and README.md both said "two filled example packages" for
  `examples/`, omitting `examples/ci/`; ROADMAP.md undercounted the eval case set
  (`tests/cases/pixelrag-repo/` exists too, just unbaselined); and PROVENANCE.md —
  which explicitly instructs contributors to record new work — had no entry for
  any of the four rounds of doc/code work in this engagement, now added as one
  dated entry. Also corrected README's stated trigger for heuristic-fallback
  compiler output (it's a missing API key, not an unset `LSD_LLM_PROVIDER`, which
  defaults to `anthropic` either way) and a param-name mismatch in ROADMAP's
  reference to `cli._content_similarity()`.
- **Clarified the job of each top-level doc and removed the resulting duplication.**
  `HANDOFF.md`'s "Suggestions for the next contributor" section had gone stale and
  self-contradicting (it listed `skills-ref validate` and `lsd eval --init` as open
  suggestions while its own later sections recorded both as shipped). HANDOFF.md is
  now strictly a decision log; live actionable items live in exactly one place each:
  README.md § Suggested next steps (near-term / blocked only on LLM access) and
  ROADMAP.md § Open gaps for the next contributor (blocked on an external dependency,
  plus unscheduled backlog — eval case expansion, description optimizer, MCP server
  scaffold, carried over from HANDOFF's old list rather than dropped). Also corrected
  ROADMAP's stale claim that the v0.4 retrieval default uses embeddings/FAISS — the
  shipped default (`NaiveRetrievalBackend`) is lexical chunking with a token guard.

### Fixed
- **Critical:** `compiler.py` raised `IndentationError` on import (a malformed
  local `SkillType` import from commit `e5f02c2`), which broke the entire `lsd`
  package and the whole test suite. Removed the redundant/misindented import.
- Repaired four test modules left stale by the "ponytail" refactor so the suite
  is green again (104 passing): tuple-return unpacking in `test_compiler.py`,
  relocated token-estimator imports in `test_retrieval.py`, `Routing`-removal
  and patch-target fixes in `test_pipeline_multi.py`, and a mismatched mock URL
  in `test_fetcher.py`.

### Added
- **`## Gotchas` section in the compiler pass.** The LLM compiler now emits a
  fourth grounded section capturing environment-specific facts, API quirks,
  version/auth/rate-limit constraints, and silent-failure modes — the
  highest-ROI content in a skill. Neutral note when the source has none; TODO
  placeholder on the heuristic (no-LLM) path. (`_gotchas_block`,
  `_parse_optional_section`.)
- **Drift similarity swap seam.** `cli._content_similarity()` isolates the
  drift comparison and accepts an injectable `similarity_fn`, so an
  embedding-backed cosine similarity can replace the lexical `SequenceMatcher`
  when a low-latency embeddings endpoint is available — without touching the
  rest of the drift path. Default behaviour unchanged.
- `estimate_tokens()` / `combined_token_estimate()` in `lsd.utils` — single
  home for the token-budget math (was duplicated inline in `pipeline.py`).
- `AGENTS.md` + `CLAUDE.md` (agent working guide and pointer) and `.gitignore`.
- New tests: Gotchas coverage in `test_compiler.py`; `test_drift.py` for the
  drift classifier and similarity seam.

### Changed
- `build_multi()`'s cross-module dependencies are imported at module scope
  (matching `build()`); there was no circular-import reason for them to be
  function-local, and it restores the natural `lsd.pipeline.*` patch targets.

### Added (maintenance follow-up — LLM-independent gaps)
- **`skills-ref` spec validation wired into `lsd build`.** New `lsd/validation.py`
  (`validate_package`) wraps the reference validator; `build` runs it after
  writing and prints a pass/warn panel via `cli._print_validation`. Degrades to
  "spec check skipped" when `skills-ref` isn't installed; the directory-name/slug
  mismatch is treated as a benign hint (resolved by `lsd package`).
- **`lsd eval --init [--force]`.** Builds a case straight into `expected/` to
  create the eval baseline; refuses to clobber an existing baseline without
  `--force` (which clears stale files first).
- **`examples/ci/drift-check.yml`** — a copy-paste GitHub Actions template for a
  skill-package repo that runs the bundled drift checker on a schedule and
  opens/updates a `source-drift` issue on change. Plus `examples/ci/README.md`.

### Changed (type/lint cleanup)
- **`ruff check` and `python -m mypy src` (strict) are now clean.** Addressed the
  pre-existing debt with type-only / style-only changes: `Literal` narrowing in
  `classifier.py` and `opportunity_mapper.py` (dropping two `# type: ignore`s),
  generic type parameters (`dict[str, Any]`, `list[...]`, the `routing` tuple),
  missing annotations on internal helpers, `TextBlock` narrowing in the Anthropic
  backend, `RetrievalIndex._state: Any`, reformatted compact `if …: return`
  lines, and removed unused test imports. No behaviour change. `pyproject.toml`
  gains mypy overrides for the two stub-less optional deps (`pixelrag_render`,
  `skills_ref`). Run mypy as `python -m mypy src` so it uses the project env.

### Fixed (maintenance follow-up)
- **Bundled `scripts/check-drift.py` reported drift on every run.** It hashed the
  raw `soup.get_text()` body instead of the LSD-normalised markdown, so its hash
  never matched the stored `normalized_hash`. It now faithfully mirrors
  `lsd.fetcher` + `lsd.normaliser` (extraction → normalise → hash) and uses the
  same User-Agent. Guarded by `tests/unit/test_drift_script_parity.py`.
- New tests: `test_validation.py`, `test_eval_init.py`, `test_drift_script_parity.py`
  (116 passing).

---

## [0.4.0] — 2026-06-30

### Added
- `retrieval/` subpackage: pluggable `RetrievalBackend` ABC with `index()` +
  `retrieve()` contract
- `NaiveRetrievalBackend`: full-context stuffing, fixed-size chunking, 50K
  token budget guard, swap-candidate criteria documented
- `get_retrieval_backend()` factory + registry in `retrieval/__init__.py`;
  add new backends in one line
- `compile_skill_multi()` in `compiler.py`: retrieval-grounded LLM pass with
  `[Source N]` provenance markers in all multi-source compiled output
- `build_multi()` now builds a retrieval index and attaches it to the context
- `--retrieval-backend` and `--token-threshold` CLI flags on `build`
- `lsd eval <case-dir>`: re-runs the pipeline, scores output against 7-criterion
  rubric (max 14/14), diffs against `expected/` snapshot
- `README.md` generated as a first-class package output (agent entry point for
  versioning, update workflow, and source provenance)
- `compiler_model` field in `SKILL.md` YAML frontmatter, `metadata.json`, and
  `README.md` provenance table
- `LSD_OMIT_MAX_TOKENS=1` env var for providers that don't support `max_tokens`
  (e.g. Inception dLLM)
- Eval diff normalization: timestamps and content hashes normalized on both sides
  at diff time — no manual scrubbing of `expected/` needed
- First eval baseline: `tests/cases/wikipedia-ai-writing/` — 14/14, mercury-2
- `Passage`, `IndexedSource`, `RetrievalIndex` dataclasses in `models.py`
- 24 new tests in `tests/unit/test_retrieval.py` (81 total)

### Changed
- `write_package()` signature: accepts `compiler_model` and writes it to
  metadata and README
- `metadata.json` schema: `package.compiler_model` added; `artifacts` includes
  `readme_file`
- `_diff_against_expected()`: normalizes timestamps and content hashes before
  comparing; README.md package structure uses `<package-dir>/` placeholder

---

## [0.3.0] — 2026-06-30

### Added
- `SourceEntry`, `Conflict`, `ConflictReport`, `MultiSourceBuildContext`
  dataclasses in `models.py`
- `conflict_detector.py`: heuristic cross-source analysis — gap detection
  (heading coverage), contradiction detection (negation patterns near shared
  key terms), overlap detection (near-duplicate sentences)
- `build_multi(urls, output_dir)` in `pipeline.py`: parallel fetch via
  `ThreadPoolExecutor` (max 5 workers), conflict detection, merged opportunity
  map
- `map_opportunities_multi()` in `opportunity_mapper.py`: deduplicating union
  of per-source candidates
- `write_multi_package()` in `writer.py`: `source-N.md`, `sources-index.md`,
  `conflicts.md`, `skill-opportunities.md`, `metadata.json` (v0.3 schema with
  `source_dependencies` array), `index.md`
- `build` command now accepts multiple URLs (`nargs=-1`); single-URL path
  unchanged
- 6 tests in `test_pipeline_multi.py`, 9 in `test_conflict_detector.py`
  (57 total)

---

## [0.2.0] — 2026-06-30

### Added
- `compiler.py`: LLM compiler pass — fills Core principle, Workflow, Output
  format from source content; offline heuristic skeleton fallback
- `fetcher.py`: source type detection (`html`, `pdf`, `image`, `google_doc`,
  `social`, `gated`, `unsupported`)
- `llm/` subpackage: `LLMBackend` ABC, `AnthropicBackend`,
  `OpenAICompatBackend` (zero extra deps beyond httpx; covers OpenRouter,
  Inception, Groq, Together, Ollama, LM Studio, vLLM)
- Provider selection via env vars: `LSD_LLM_PROVIDER`, `LSD_MODEL`,
  `ANTHROPIC_API_KEY`, `LSD_LLM_BASE_URL`, `LSD_LLM_API_KEY`
- `SourceType` literal + `source_type` field on `FetchResult`
- `exceptions.py`: `LSDError` base exception
- `backends/pixelrag.py`: corrected API (`pixelrag_render.render_url()`)
- 13 tests in `test_fetcher.py`, 13 in `test_compiler.py` (42 total)

### Fixed
- `writer.py`: removed unused `re` import and unused `fit` local (ruff clean)

---

## [0.1.0] — 2026-06-30

### Added
- Full text-first pipeline: fetch → classify → route → normalise → map
  opportunities → write package
- 7-file output package: `SKILL.md`, `source.md`, `metadata.json`,
  `source-policy.md`, `skill-opportunities.md`, `extraction-report.md`,
  `CHANGELOG.md`
- `lsd build <url>` and `lsd check <url>` CLI commands
- `lsd version`
- 16 unit tests
- ROADMAP.md with architectural principles and universal swap-candidate
  criteria

### Fixed
- `pyproject.toml`: corrected invalid `build-backend` field (hard blocker)
- Eliminated duplicate `build` CLI command registration
- Eliminated double-fetch (prepare + build were each calling fetch)
- Removed unused import in pipeline

---

## [0.0.1] — 2026-06-30

### Added
- Initial repo scaffold: directory structure, README, spec, examples
- CLI stub with adapter architecture, models, backends, pipeline stages
- See `PROVENANCE.md` for the full origin story of this scaffold
