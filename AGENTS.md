# AGENTS.md — working in the LSD repository

Guidance for AI coding agents (and humans) working in this repo. `CLAUDE.md`
points here. Keep this file current when you change architecture, commands, or
invariants.

## What LSD is

LSD (Link-to-Skill Designer / Distiller) turns a URL — or several — into an
installable, versioned **Agent Skill** package conforming to the
[Agent Skills spec](https://agentskills.io). It ships as:

- a Python CLI (`lsd`) — the build tool,
- a meta-skill (`skills/lsd-builder/`) that wraps the CLI for conversational use,
- a pytest suite plus an eval harness (`lsd eval`) with a committed baseline.

The pipeline is: **fetch → classify → route → ingest → map opportunities →
compile → write package**, and every package records a `normalized_hash` so
`lsd check` can detect source drift later.

## Repository layout

```
src/lsd/
  cli.py            Click CLI: build / check / package / eval / version.
                    Also owns drift classification (_classify_magnitude,
                    _content_similarity) and the post-build verdict panels.
  pipeline.py       Canonical build orchestration: build(), build_multi(),
                    prepare(). Everything else is a shell around these.
  fetcher.py        URL fetch + source-type detection (html/pdf/image/
                    google_doc/social/gated/unsupported).
  classifier.py     Heuristic SourceFit scoring (rule/procedure/example density…).
  router.py         Chooses ingestion mode (text-first / hybrid / visual-first).
                    APP_DOMAINS lives here (shared with opportunity_mapper).
  normaliser.py     FetchResult → clean source.md; content_hash() (timestamp-free).
  opportunity_mapper.py  Skill/tool candidate detection + honest SourceAssessment.
  conflict_detector.py   Cross-source gaps/contradictions/overlaps (multi-source).
  compiler.py       LLM compiler pass → SKILL.md sections (Core principle,
                    Workflow, Output format, Gotchas) + heuristic fallback.
  writer.py         Writes the full package to disk (single & multi-source).
  validation.py     Optional agentskills-spec check via skills-ref;
                    validate_package() is called by build() after writing.
  models.py         All LSD dataclasses/Literals. Read this before touching data.
  utils.py          slugify(), CHARS_PER_TOKEN, estimate_tokens(),
                    combined_token_estimate() — the shared-helper home.
  exceptions.py     LSDError (user-actionable, clean CLI message).
  backends/         Visual ingestion ABC + PixelRAG adapter (optional).
  llm/              LLMBackend ABC + Anthropic / OpenAI-compatible backends.
  retrieval/        RetrievalBackend ABC + NaiveRetrievalBackend + registry.
  scripts/          check-drift.py, motivation-check.py — copied into packages.
tests/              pytest unit tests + eval cases (tests/cases/<name>/).
skills/lsd-builder/ The meta-skill (SKILL.md + references/).
docs/               architecture, spec, ingestion-modes, cross-case comparison.
schema/             metadata.schema.json.
examples/           Two filled example packages, plus examples/ci/ — a
                    copy-paste CI template for skill-package repos.
```

Top-level narrative docs: `README.md` (product + spec-adherence table),
`ROADMAP.md` (vision + swap-candidate criteria), `HANDOFF.md` (decision log),
`PROVENANCE.md` (build lineage), `CHANGELOG.md`.

## Commands

```bash
# Install (editable) with dev tooling — pulls pytest, ruff, mypy, anthropic,
# skills-ref. The openai-compat LLM backend needs no extra install (httpx only).
python -m pip install -e '.[dev]'

pytest -q                          # full unit suite (no network; httpx is mocked)
pytest tests/unit/test_compiler.py # a single module
ruff check src tests               # lint — clean
python -m mypy src                 # types — clean under strict (pyproject sets strict = true)
                                   # use `python -m mypy`, not a bare `mypy`, so it
                                   # resolves deps from THIS environment (a global mypy
                                   # without the deps installed reports false import errors)

lsd build <url> [-o DIR] [--mode …] [--license …]   # single source; runs spec validation
lsd build <url1> <url2> … [-o DIR]                  # multi-source
lsd check <package-dir-or-url>                       # drift detection (all sources in a package)
lsd package <package-dir> --zip                      # validate + zip for install
lsd eval tests/cases/wikipedia-ai-writing            # re-run + score vs expected/
lsd eval <case-dir> --init [--force]                 # build straight into expected/ to create the baseline
```

**Before committing any change to product source, run `pytest -q`.** A prior
refactor shipped an `IndentationError` in `compiler.py` that made the entire
package unimportable while docs still claimed the suite was green — imports are
not free, so let the suite catch it.

## Architecture invariants (do not break these)

1. **Pipeline owns the implementation.** Add a capability to `pipeline.py`
   first, expose a CLI flag second, add a test third. The CLI and meta-skill
   never reimplement pipeline logic; the meta-skill calls `lsd` subcommands, not
   internal Python.
2. **Pluggable components sit behind an ABC + registry.** Visual (`backends/`),
   LLM (`llm/`), and retrieval (`retrieval/`) each expose an ABC and a factory.
   Feature code imports the factory, never a concrete backend. Adding a provider
   = one registry entry + one factory function.
3. **LSD's own types are the seam.** Backends translate their output into the
   dataclasses in `models.py`; nothing outside a backend package sees a
   provider's native types.
4. **`compile_skill()` and `compile_skill_multi()` return `(content, model_id)`
   tuples.** Always unpack — `writer.py` does. `model_id` is `None` on the
   heuristic fallback and becomes `compiler_model` in the frontmatter/metadata.
5. **Spec compliance is non-negotiable.** Generated `SKILL.md` frontmatter uses
   only spec keys (`name`, `description`, `license`, `allowed-tools`, `metadata`,
   `compatibility`); LSD-specific fields go under `metadata:`. The `name` slug
   must match the package directory (enforced by `lsd package`).

## Conventions & gotchas

- **Shared helpers live in `utils.py`.** `slugify`, `CHARS_PER_TOKEN`, and the
  token estimators are single-sourced there; don't reintroduce local copies.
- **`allowed-tools` is derived from skill type**, not hardcoded — see
  `compiler._allowed_tools_for_skill_type`.
- **`## Gotchas` is a first-class compiled section.** The LLM pass extracts
  environment-specific facts / quirks / constraints (highest-ROI skill content);
  a missing or `"none"` answer renders a neutral note, not a bug-looking
  placeholder (`compiler._gotchas_block` / `_parse_optional_section`).
- **Drift similarity has one swap point:** `cli._content_similarity`. It defaults
  to `difflib.SequenceMatcher` (lexical) and accepts an injected `similarity_fn`.
  Semantic drift (same words, reorganised meaning) needs an embedding-backed
  cosine `similarity_fn`; LSD ships none because no embedding API is wired into
  any backend and `scripts/check-drift.py` is intentionally httpx-only. Plug the
  function in there when an embeddings endpoint exists — nothing else changes.
- **LLM provider is env-configured.** `LSD_LLM_PROVIDER` (`anthropic` |
  `openai-compat`), `LSD_MODEL`, plus keys/base-url. No provider → heuristic
  fallback (TODO placeholders). `LSD_OMIT_MAX_TOKENS=1` for providers that reject
  `max_tokens` (e.g. Inception dLLM).
- **`skills-ref` is a Python API, not a CLI here.** `lsd.validation.validate_package`
  wraps `skills_ref.validate(Path(package_dir))` → list of error strings; `build`
  runs it after writing and surfaces problems (`cli._print_validation`). It is a
  dev/optional dependency, so validation degrades to "skipped" when absent. The
  directory-name/`name`-slug mismatch is treated as a benign hint (build output
  goes to a user-chosen dir; `lsd package` aligns the archive root).
- **Files under `src/lsd/scripts/` are hyphenated and NOT importable modules.**
  They are canonical script bodies copied verbatim into each package's
  `scripts/` by `writer._copy_scripts`. Edit them there; don't try to `import`
  them.
- **`scripts/check-drift.py` must mirror `lsd.fetcher` + `lsd.normaliser` exactly.**
  It recomputes the stored `normalized_hash` with no `lsd` install (it runs via
  `uv` in CI), so its `extract_title`/`extract_text`/`clean`/`normalise`/
  `content_hash` are faithful ports. If you change extraction or normalisation in
  `lsd`, update the script too — `tests/unit/test_drift_script_parity.py` fails
  on divergence. (This is the bug that made the script report drift on every run.)
- **Unit tests never hit the network.** `test_fetcher.py` uses `pytest-httpx`;
  mock URLs must match exactly what the code requests. `test_pipeline_multi.py`
  patches `lsd.pipeline.*` names, so cross-module deps used by `build_multi` are
  imported at module scope (keep them there).

## Where the real gaps are (see README "Suggested next steps" for detail)

Working today: the full build/check/package/eval flow, spec validation wired
into `build`, `lsd eval --init` for baselines, a CI drift-check template
(`examples/ci/`), spec-valid output, multi-source with conflict detection, and a
drift checker whose standalone script now matches `lsd check`. Remaining
limitations: heuristic compiler output (incl. Gotchas) until an LLM provider is
configured; `NaiveRetrievalBackend` is lexical; PixelRAG visual backend is a
stub pending upstream release; drift similarity is lexical (semantic-drift swap
seam exists but no embedding backend ships).
