# LSD — Handoff Document

> This document records every significant decision made during the development of LSD (Link-to-Skill Distiller) from v0.1 through v0.5, with rationale and suggestions for the next contributor. It is intended to be read alongside PROVENANCE.md (which records the build lineage) and CHANGELOG.md (which records what changed version by version).

---

## Project summary

LSD converts URLs into installable, versioned AI skill packages conforming to the [Agent Skills open standard](https://agentskills.io). It ships as a Python CLI (`lsd`), a meta-skill (`skills/lsd-builder/`) that wraps the CLI for conversational use, and a test harness with an eval baseline.

**Current version:** 0.5.0  
**Test suite:** 104 tests passing (see *Post-handoff maintenance* below; the
earlier "81 passing" predated added tests and a build-breaking regression)  
**Eval baseline:** 14/14 (Wikipedia AI-writing case, mercury-2, Inception dLLM).
Note: the committed `expected/` snapshot predates the `## Gotchas` section, so
`lsd eval` will now report a `DIFFER` on `SKILL.md` until the baseline is
regenerated.

> **Read this first.** The sections below are the original decision log written
> at handoff. For what changed *after* handoff — including a critical fix — see
> [Post-handoff maintenance](#post-handoff-maintenance) at the end.

---

## Architecture decisions

### 1. Pipeline owns the canonical implementation

**Decision:** `pipeline.build()` and `pipeline.build_multi()` are the single source of truth. The CLI, meta-skill, and any future web API are shells around them.

**Rationale:** This was the first architectural principle laid down and has held throughout development. Every feature (multi-source, retrieval, opportunity mapping) was added to the pipeline first and surfaced through the CLI second. The meta-skill never calls internal Python directly — it calls `lsd` subcommands.

**Implication for contributors:** If you add a pipeline capability, add it to `pipeline.py` first, add a CLI flag second, add a test third. Do not add CLI-only features that bypass the pipeline.

### 2. ABC-first design for all pluggable components

**Decision:** Visual backend, retrieval backend, and LLM backend all sit behind ABCs with factory/registry patterns. No feature code imports a concrete implementation directly.

**Rationale:** The user explicitly required modularity for v0.4 (retrieval) and visual backends. The design was extended to LLM backends in v0.2 when multi-provider support was requested. The swap-candidate criteria (documented in ROADMAP.md and SKILL.md) define when a swap is warranted.

**Current implementations:**
- Visual: `TextBackend` (default), `PixelRAGBackend` (stub — see known limitations)
- Retrieval: `NaiveRetrievalBackend` (default) — full-context stuffing with 50K token guard
- LLM: `AnthropicBackend`, `OpenAICompatBackend` (covers OpenRouter, Inception, Groq, Together, Ollama, any OpenAI-compatible surface)

**Swap criteria:** documented in `ROADMAP.md § Swap-candidate criteria` and in `skills/lsd-builder/SKILL.md § Modular backends`. Read these before replacing any backend.

### 3. `compile_skill_multi()` returns `(str, str | None)` tuple

**Decision:** The multi-source compiler returns `(skill_content, readme_content)` as a two-element tuple. Single-source `compile_skill()` returns a plain string.

**Rationale:** This asymmetry exists because multi-source builds require a `README.md` entry-point file that single-source builds also produce but through a different path. The tuple was introduced to fix a gap (G2) where multi-source README generation was missing. The `MUST` constraint was added by the user after a regression.

**Watch out:** Code that calls `compile_skill_multi()` must unpack both elements. The `_readme_multi()` helper generates the README content. Never overwrite the README in a multi-source build without going through `_readme_multi()`.

### 4. `_readme_multi()` is the canonical README generator for multi-source

**Decision:** Introduced as a dedicated function after the tuple refactor. Any multi-source README must use it; do not inline README generation.

**Rationale:** Consistency and testability. The function is tested in `test_compiler.py`.

### 5. Opportunity mapping is integrated, not post-hoc

**Decision:** The opportunity mapper runs as a pipeline stage before compilation. Its output (`SourceAssessment`, `OpportunityMap`) feeds the compiler's `_caveat_block`, `_tool_candidates_block`, and `_related_skills_block` directly.

**Rationale:** Early designs treated opportunity mapping as advisory output only. In v0.5, the assessment became actionable — the `recommended_action` field in `SourceAssessment` drives the CLI verdict panel and the meta-skill's post-build flow.

**Key model relationships:**
- `ToolCandidate` has derived properties: `.type` (label), `.confidence` (inverted from effort), `.why_fit` (alias for description), `.build_timing` (now/later from effort)
- `SourceAssessment` has `.skill_fit_verdict` (not `.verdict` — this caused Bug 2)
- `opportunity_map_only` was removed from the `Literal` type (was dead code)
- `SourceAssessment.tool_candidates` was removed (candidates live on `OpportunityMap`)

### 6. The CLI verdict panel is the user-facing surface for opportunity data

**Decision:** `_render_verdict_panel()` in `cli.py` translates `recommended_action` into a coloured Rich panel. Action strings must exactly match the Literal values in `models.py`.

**Rationale:** The panel was added to give users a clear signal at build time rather than requiring them to read `skill-opportunities.md`. Bug 3 (action string mismatch) was caused by a mismatch between the action Literal values and the panel's match logic.

**Current Literal values:** `build_one_skill`, `build_multiple_skills`, `build_with_caveats`, `defer`

### 7. Drift magnitude uses SequenceMatcher direct diff when source.md is available

**Decision:** `_classify_magnitude()` in `cli.py` diffs the live fetch against `source.md` directly using `difflib.SequenceMatcher`. When `source.md` is not available, it falls back to the proxy method (word count ratio + heading count comparison).

**Rationale:** The proxy was introduced first (v0.4) as it required no file I/O. The user explicitly requested the upgrade to direct diff in a follow-up. The `_content_lines()` helper strips the file header before diffing to avoid false-positive SUBSTANTIAL signals from timestamp differences in the header.

**Thresholds (direct diff):**
- `similarity < 0.60` → SUBSTANTIAL
- heading loss > 30% → SUBSTANTIAL  
- word ratio < 0.50 or > 2.50 → SUBSTANTIAL
- `similarity >= 0.95` → UNCHANGED
- Otherwise → MINOR

**Edge cases:** GONE (HTTP 4xx/5xx/timeout) and REDIRECTED (permanent redirect) are detected before drift magnitude is calculated.

### 8. `LSD_OMIT_MAX_TOKENS=1` for Inception dLLM compatibility

**Decision:** When this env var is set (any truthy value), the LLM backend does not pass `max_tokens` in the API call.

**Rationale:** Inception's `mercury-2` model does not accept `max_tokens` in the request body. Without this workaround, every build call returns a 400 error. The workaround was discovered during the eval baseline run.

**Note:** This is an Inception-specific quirk. Other OpenAI-compatible providers handle `max_tokens` normally.

### 9. Eval baseline is mercury-2 at 14/14

**Decision:** The committed `expected/` snapshot in `tests/cases/wikipedia-ai-writing/` was generated using the Inception dLLM `mercury-2` model and scored 14/14 against the rubric.

**Rationale:** mercury-2 was the model being tested. The baseline represents a high-quality build from a known model and source, making it a meaningful regression anchor.

**Note:** The `expected/` snapshot was reviewed against an earlier snapshot generated by Perplexity's auto-selected model (the original session model, identity unknown). That comparison drove the rubric scoring in v0.4. The `compiler_model` field now tracks which model generated a given package.

### 10. `compiler_model` is first-class in all three output surfaces

**Decision:** `compiler_model` appears in `SKILL.md` YAML frontmatter (`metadata.compiler_model`), in `metadata.json` (`package.compiler_model`), and in `README.md` (provenance table). When the heuristic fallback is used (no LLM configured), the value is `"heuristic"`.

**Rationale:** Without this field, packages generated by different models are indistinguishable. The field is essential for triage when a package degrades after a rebuild with a different model.

### 11. `README.md` is a first-class package output

**Decision:** Every `lsd build` run generates a `README.md` alongside `SKILL.md`. This file is the agent's entry point for versioning, update workflow, and source provenance.

**Rationale:** Originally, README was not emitted. The user requested it as a first-class output so agents loading the package understand its lineage without reading `metadata.json` directly.

### 12. Diff normalization in `lsd eval`

**Decision:** `_diff_against_expected()` normalizes timestamps and content hashes on both sides before comparing. The `expected/` snapshot does not need to be manually scrubbed.

**Rationale:** Without normalization, every eval diff would show false positives on `generated_at` timestamps and `normalized_hash` values. The normalization is applied in memory — the committed `expected/` files are never modified by the eval command.

### 13. Source provenance in `[Source N]` markers

**Decision:** `compile_skill_multi()` inserts `[Source N]` provenance markers in all compiled output sections when building from multiple sources.

**Rationale:** Without markers, the user cannot tell which claim in the compiled skill came from which source. This is especially important when conflict detection flags a contradiction — the user needs to know which source made the contradicting claim.

### 14. `_allowed_tools_for_skill_type()` mapping

**Decision:** Allowed-tools strings are determined by skill type according to this mapping:

| Skill type | allowed-tools |
|-----------|--------------|
| `reviewer`, `rewriter` | `Read` |
| `workflow_coach`, `integration_planner` | `Read Write Edit Bash` |
| Code-related types | `Read Write Bash` |
| Default | `Read Write Edit` |

**Rationale:** The mapping was derived from the skill types' expected behavior. Reviewer/rewriter skills should not modify files; workflow and integration skills need full access; code skills need execution but not arbitrary editing.

---

## Meta-skill decisions

### 15. Three build modes: Express, Guided, (Socratic removed)

**Decision:** The meta-skill offers two modes: Express (3 questions then build) and Guided (fetch first, Socratic exchange, then build). Socratic as a standalone mode was removed after discussion — its interview logic was merged into Guided's Phase 2.

**Rationale:** Three modes confused the mode-selection UX. Express and Guided cover the spectrum from "I know what I want" to "I'm not sure if this source is a good fit." The Socratic exchange is depth-limited to two turns in Guided mode to prevent infinite refinement loops.

### 16. `motivation.json` schema

```json
{
  "intent": "...",
  "audience": "...",
  "key_concepts": ["..."],
  "skill_name_confirmed": "...",
  "build_mode": "express|guided",
  "socratic_notes": "...",
  "recorded_at": "ISO8601"
}
```

**Rationale:** This file captures the why behind the build. The `motivation-check.py` script reads it post-drift to determine whether the original intent still applies to the changed source.

### 17. SKILL.md body stays under 500 lines

**Decision:** The meta-skill SKILL.md is 275 lines. All detailed reference material (interview flow, provider config, output schema, rubric) lives in `references/`.

**Rationale:** Adherence to the spec's progressive disclosure recommendation. The 500-line limit is not a hard constraint but a strong recommendation from Anthropic's skill-creator skill.

### 18. Post-build 8-step flow

The meta-skill's post-build flow is fixed at 8 steps:
1. Show verdict (read `recommended_action`, apply verdict playbook)
2. Show fit score + skill type
3. Confirm skill name (slug)
4. Surface tool candidates (higher priority than secondary skills)
5. Show secondary skill opportunities
6. Flag quality issues (low fit, heuristic fallback)
7. Offer packaging (`lsd package --zip`) — only if verdict ≠ `defer`
8. Remind about maintenance scripts

**Rationale:** Steps 1 and 4 are ordered by priority (verdict first, tool candidates before secondary skills). Steps 7 and 8 are gated to avoid offering packaging when the build result is unusable.

---

## Known bugs resolved (v0.5)

All three bugs discovered in the final audit were closed in commit `db126dec`:

| Bug | Root cause | Fix |
|-----|-----------|-----|
| Bug 1: ToolCandidate properties | `tool_type`, `effort_level` were stored as raw Literal values; callers expected human-readable labels | Implemented as `@property` methods on the dataclass |
| Bug 2: `.verdict` AttributeError | `SourceAssessment` has `.skill_fit_verdict`, not `.verdict`; writer.py used the wrong attribute | Renamed all callsites to `.skill_fit_verdict` |
| Bug 3: Verdict panel action mismatch | `_render_verdict_panel` used string literals that didn't match the `Literal` values in models.py | Aligned action strings across models.py, cli.py, and SKILL.md |

---

## What was deliberately not done

| Item | Why not done |
|------|-------------|
| Interactive CLI prompts | Would break pipeline-first design; the meta-skill provides the interactive layer |
| `lsd init` command | Not scoped; project started from a URL-in, package-out model |
| Skill composition (depend on other skills) | In ROADMAP.md as a future item; architecture needs to be designed |
| Hosted web product | Out of scope for v0.5; described in ROADMAP.md |
| `skills-ref validate` auto-run in pipeline | The `skills-ref` CLI is an external dependency not bundled with LSD; referenced in SKILL.md but not enforced programmatically |
| Blind A/B comparison eval | Anthropic skill-creator pattern; not applicable to LSD's regression-harness eval model |

---

## Suggestions for the next contributor

### Priority 1 (closes known gaps)
- **Wire `skills-ref validate` into `pipeline.build()`** — import as a subprocess call if `skills-ref` is installed, warn gracefully if not. This is the single clearest signal of spec compliance.
- **Add `lsd eval --init`** — run a build and commit the output to `expected/`. Currently the only way to create a baseline is manually.

### Priority 2 (completes the maintenance story)
- **`lsd check --all-sources`** — iterate over all entries in `source_dependencies[]` in `metadata.json` and report a unified drift summary.
- **GitHub Actions example** — add `.github/workflows/drift-check.yml` that runs `lsd check` on a configured package and opens an issue on SUBSTANTIAL drift. This makes source-dependency tracking actionable in CI.

### Priority 3 (quality)
- **Retrieval backend upgrade** — `NaiveRetrievalBackend` is documented as the v0.4 placeholder. The swap criteria are in ROADMAP.md. When a better retrieval approach is available, it should implement `RetrievalBackend` and be registered in `retrieval/__init__.py`.
- **Expand the eval case set** — there is currently one eval case (Wikipedia AI-writing). Adding a hybrid case (code documentation) and a visual-first case (when PixelRAG is available) would give the regression harness broader coverage.
- **Description optimizer** — the meta-skill generates descriptions from source intent. Running the Anthropic `skill-creator`'s `run_loop.py`-style trigger optimization on generated descriptions would likely improve agent recall.

### Priority 4 (product)
- **MCP server scaffold** — when a `mcp_server` tool candidate is detected, offer to scaffold a minimal MCP server stub. The opportunity mapper already detects these.
- **Web product** — the ROADMAP.md describes the full vision. The pipeline is ready; the web surface needs a FastAPI or similar wrapper around `pipeline.build()`.

---

## Files to read first (for a new contributor)

1. `ROADMAP.md` — architectural principles and full vision
2. `docs/spec.md` — input/output contract and ingestion mode routing
3. `src/lsd/pipeline.py` — canonical implementation
4. `src/lsd/models.py` — data model (read before touching any other file)
5. `skills/lsd-builder/SKILL.md` — the meta-skill (user-facing interface)
6. `PROVENANCE.md` — build lineage (who built what and when)
7. `CHANGELOG.md` — version-by-version record

---

## Provenance of this document

Written by Perplexity Computer (model: claude-sonnet-4-6) in the same session that produced v0.5.0, as part of the "prime-time readiness" review. The session thread is preserved in the project owner's Perplexity history at the canonical thread URL recorded in PROVENANCE.md.

---

## Post-handoff maintenance

Changes made after this document was written, during a repo review pass.

### Critical fix — the package did not import

A refactor commit (`e5f02c2`, "6 modularity fixes") added
`from lsd.models import SkillType` inside `compile_skill_multi()` but mis-indented
the following line, producing an `IndentationError`. `SkillType` was already
imported at module scope and unused inside the function, so the whole `lsd`
package failed to import — every CLI command and the entire test suite were
broken despite docs claiming a green build. Fix: removed the redundant/malformed
local import. **Lesson:** run `pytest -q` (or at least `python -m compileall
src/lsd`) before committing; the suite catches this instantly.

### Stale tests repaired (green: 104 passing)

The same refactor left four test modules out of sync with the code they cover:

- `test_compiler.py` — treated `compile_skill()` as returning a string; it
  returns `(content, model_id)`. Tests now unpack the tuple.
- `test_retrieval.py` — imported `estimate_tokens` / `combined_token_estimate`
  from `retrieval/naive.py`, which the refactor deleted. Those helpers now live
  in `lsd.utils` (their proper single-source home; the "inlined" version had
  duplicated the math in `pipeline.py`), and the test imports them from there.
- `test_pipeline_multi.py` — referenced the removed `Routing` dataclass and
  patched `lsd.pipeline.*` names the refactor had pushed into function-local
  imports. `build_multi`'s cross-module deps are now imported at module scope
  (matching `build()`), and the helper returns the plain 5-tuple `prepare()`
  actually produces.
- `test_fetcher.py::test_login_redirect_raises_lsd_error` — registered its
  `httpx` mock for a different URL than `fetch()` requested; corrected.

### (a) `## Gotchas` section added to the compiler

The LLM compiler pass now emits a fourth grounded section — `## Gotchas` —
capturing environment-specific facts, API quirks, version/auth/rate-limit
constraints, and silent-failure modes. Community data flags this as the
highest-ROI content in a skill. A missing or `"none"` answer renders a neutral
note rather than a placeholder that looks like a bug (`_gotchas_block`,
`_parse_optional_section`). Covered by new tests in `test_compiler.py`.

### (b) Semantic-drift similarity — seam, not implementation

The throwaway note about swapping `SequenceMatcher` for embedding cosine
distance is a *correct but conditional* gap: no embedding API is wired into any
LSD backend (the LLM backends expose only `complete()`; retrieval is lexical),
and `scripts/check-drift.py` is intentionally `httpx`-only. Implementing a live
embedding call would need a provider + key + network and would break the
standalone drift checker. Instead, the similarity computation is isolated in
`cli._content_similarity(old_lines, new_lines, similarity_fn=None)` — the single,
now-tested swap point. Default behaviour is unchanged (lexical). When an
embeddings endpoint exists, inject an embedding-backed `similarity_fn`; if
several strategies emerge, graduate it to a `SimilarityBackend` ABC + registry
like `lsd.retrieval`. New coverage in `test_drift.py`.

### Repo hygiene

Added `.gitignore` (the editable install was dropping untracked `*.egg-info/`
and `__pycache__/`), `AGENTS.md` (full agent working guide) and `CLAUDE.md`
(pointer to it).

---

## Follow-up pass — LLM-independent gaps (post-merge)

After the above landed on `main`, a second pass closed the remaining gaps that
don't need a configured LLM or the original eval model. Suite: **116 passing**.

- **Spec validation wired into `build`.** `lsd/validation.py` (`validate_package`)
  wraps `skills-ref` and `lsd build` now runs it after writing the package,
  printing a pass/warn panel. Skipped gracefully when `skills-ref` is absent; the
  dir-name/slug mismatch is a benign hint (build output is a chosen dir; `lsd
  package` aligns the archive root). Tests: `test_validation.py`.
- **`lsd eval --init [--force]`.** Builds a case directly into `expected/` to
  create the baseline; guards against clobbering an existing one. Tests:
  `test_eval_init.py`.
- **CI drift-check template** at `examples/ci/drift-check.yml` (+ README). It
  belongs in a *skill-package* repo, not the LSD tool repo (LSD is not itself a
  skill package), so it's an example, not an active workflow here.
- **Bug fixed: the bundled `scripts/check-drift.py` reported drift on every run.**
  It hashed raw page text instead of the LSD-normalised markdown, so its hash
  never matched the stored `normalized_hash` (the `lsd check` CLI was fine; the
  standalone script — the one CI/`uv` users run — was not). It now mirrors
  `lsd.fetcher` + `lsd.normaliser` exactly and uses the same User-Agent.
  `test_drift_script_parity.py` fails if the two ever diverge again.
- **`lsd check --all-sources` was already satisfied** — `_check_package` iterates
  every `source_dependencies` entry and reports a unified table; no flag needed.

*Recorded by the repo-review pass on the `claude/link-skill-converter-review`
branch.*
