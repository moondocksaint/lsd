# Changelog

All notable changes to LSD are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

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
