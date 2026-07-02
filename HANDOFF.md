# LSD — Handoff Document

> This document records every significant decision made during the development of LSD (Link-to-Skill Distiller), from v0.1 through ongoing post-v0.5 review passes, with rationale. It is intended to be read alongside PROVENANCE.md (which records the build lineage — who/which session built what, terse and attribution-only) and CHANGELOG.md (which records what changed version by version, in full). This file should contain *why*, not *who* or *what* — if a new entry here starts re-narrating a change already described elsewhere, it belongs in one of those two files instead.

---

## Project summary

LSD converts URLs into installable, versioned AI skill packages conforming to the [Agent Skills open standard](https://agentskills.io). It ships as a Python CLI (`lsd`), a meta-skill (`skills/lsd-builder/`) that wraps the CLI for conversational use, and a test harness with an eval baseline.

**Current version:** 0.5.0  
**Test suite:** 116 tests passing (PROVENANCE.md has the session-by-session
count; the earlier "81 passing" predated added tests and a build-breaking
regression, see Decisions 19–23 and Bug 4 below)  
**Eval baseline:** 14/14 (Wikipedia AI-writing case, mercury-2, Inception dLLM).
Note: the committed `expected/` snapshot predates the `## Gotchas` section, so
`lsd eval` will now report a `DIFFER` on `SKILL.md` until the baseline is
regenerated.

> **Read this first.** "Architecture decisions" and "Meta-skill decisions" below
> were written at the original v0.5.0 handoff. "Decisions since v0.5.0" continues
> the same numbering for later review passes — including a critical import-breaking
> bug (see Bug 4 in the bugs table). This file only records *why*; see
> PROVENANCE.md for *who/when* and CHANGELOG.md for *what changed*.

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

## Decisions since v0.5.0

Continues the numbering above. These decisions came out of post-v0.5 review passes;
see PROVENANCE.md for which session/commit produced each one, and CHANGELOG.md for
the full change description — this section covers only the *why*.

### 19. `## Gotchas` is a required fourth compiler section, not optional metadata

**Decision:** The LLM compiler pass emits `## Gotchas` alongside Core principle,
Workflow, and Output format in every compiled `SKILL.md`. A missing or
`"none"`-equivalent answer renders a neutral placeholder note, not a raw TODO
comment.

**Rationale:** Community data identifies Gotchas (environment-specific facts, API
quirks, version/auth/rate-limit constraints, silent-failure modes) as the
highest-ROI content in a skill. Rendering a neutral note for an empty answer —
rather than an empty section or a TODO-looking placeholder — avoids it reading
as a bug when a source genuinely has none.

**Implementation:** `compiler._gotchas_block()` / `_parse_optional_section()`.
Tested in `test_compiler.py`.

### 20. Semantic-drift similarity is a swap seam, not a shipped feature

**Decision:** The drift classifier isolates its similarity computation behind
`cli._content_similarity(old_lines, new_lines, similarity_fn=None)`, defaulting
to a lexical `difflib.SequenceMatcher` ratio.

**Rationale:** Semantic drift (same words, reorganised meaning) is invisible to
lexical similarity, and an embedding-based cosine similarity is the fix — but no
embedding API is wired into any LSD backend (LLM backends are chat-only;
retrieval is lexical), and `scripts/check-drift.py` is deliberately `httpx`-only
so it runs via `uv` with no `lsd` install; a live embedding call would need a
provider + key + network and would break that standalone-script contract.
Isolating the seam lets a future `similarity_fn` swap in without touching the
rest of the drift path.

**Implementation:** `cli._content_similarity()`. Tested in `test_drift.py`.

### 21. Spec validation runs post-build; the dir-name/slug mismatch is a hint, not an error

**Decision:** `lsd build` runs `skills-ref`'s validator (via
`lsd.validation.validate_package()`) after writing the package and prints a
pass/warn panel. The validator's directory-name/slug-mismatch message is
surfaced as a hint, separate from the pass/fail verdict.

**Rationale:** `skills-ref` is an optional dev dependency, so validation must
degrade gracefully (a "spec check skipped" note) rather than fail the build when
it's absent. The directory-name/slug check is about *packaging*, not `SKILL.md`
content — `lsd build` writes into a user-chosen output directory, and `lsd
package` is what aligns the installable archive's root folder with the slug —
so a mismatch during `build` is expected, not a spec violation to block on.

**Implementation:** `lsd/validation.py`, `cli._print_validation()`. Tested in
`test_validation.py`.

### 22. `lsd eval --init` refuses to overwrite an existing baseline without `--force`

**Decision:** `lsd eval <case> --init` writes a fresh baseline into `expected/`;
if that directory already has content, it exits with an error unless `--force`
is also passed, in which case the directory is cleared first.

**Rationale:** An eval baseline is a manually reviewed, hand-approved snapshot
(see "How to add a new eval baseline" in PROVENANCE.md) — a bare `--init` re-run
must not silently clobber a reviewed baseline with an unreviewed one. `--force`
exists for the deliberate case (regenerating after a source or model change).

**Implementation:** `cli._init_baseline()`. Tested in `test_eval_init.py`.

### 23. The drift-check CI template is an example, not an active workflow

**Decision:** `examples/ci/drift-check.yml` is a copy-paste GitHub Actions
template, not a workflow LSD runs on itself.

**Rationale:** The template runs `scripts/check-drift.py` against a package's
`metadata.json` — but LSD's own repo is not a skill package (no `metadata.json`
at its root), so an active workflow here would just fail. It belongs in the repo
of whichever *skill package* it's watching. Related: a `lsd check --all-sources`
flag was considered and found unnecessary — `_check_package` already iterates
every entry in `metadata.json → source_dependencies` in one run.

**Implementation:** `examples/ci/drift-check.yml` + `examples/ci/README.md`.

---

## Known bugs resolved

Bugs 1–3 were discovered in the v0.5 final audit and closed in commit `db126dec`.
Bugs 4–5 were found in later review passes (see PROVENANCE.md for session/commit
attribution; CHANGELOG.md for the full fix description).

| Bug | Root cause | Fix |
|-----|-----------|-----|
| Bug 1: ToolCandidate properties | `tool_type`, `effort_level` were stored as raw Literal values; callers expected human-readable labels | Implemented as `@property` methods on the dataclass |
| Bug 2: `.verdict` AttributeError | `SourceAssessment` has `.skill_fit_verdict`, not `.verdict`; writer.py used the wrong attribute | Renamed all callsites to `.skill_fit_verdict` |
| Bug 3: Verdict panel action mismatch | `_render_verdict_panel` used string literals that didn't match the `Literal` values in models.py | Aligned action strings across models.py, cli.py, and SKILL.md |
| Bug 4: package unimportable | Commit `e5f02c2` left a mis-indented, redundant local `SkillType` import inside `compile_skill_multi()` — an `IndentationError` that broke the entire package and test suite despite docs claiming a green build | Removed the malformed import. Lesson: `pytest -q` (or `python -m compileall src/lsd`) catches this instantly — run it before committing |
| Bug 5: standalone drift checker always reported drift | `scripts/check-drift.py` hashed raw fetched text; LSD's stored `normalized_hash` is over the *normalised* markdown — the two could never match, so every run looked like drift regardless of whether the source had changed | Rewrote the script's extraction/normalisation to mirror `lsd.fetcher` + `lsd.normaliser` exactly; `test_drift_script_parity.py` guards against the two diverging again |

---

## What was deliberately not done

| Item | Why not done |
|------|-------------|
| Interactive CLI prompts | Would break pipeline-first design; the meta-skill provides the interactive layer |
| `lsd init` command | Not scoped; project started from a URL-in, package-out model |
| Skill composition (depend on other skills) | In ROADMAP.md as a future item; architecture needs to be designed |
| Hosted web product | Out of scope for v0.5; described in ROADMAP.md |
| `skills-ref validate` auto-run in pipeline | *(as of v0.5.0)* The `skills-ref` CLI is an external dependency not bundled with LSD; referenced in SKILL.md but not enforced programmatically. **Since done** — see Decision 21: `lsd build` now runs it via its Python API and surfaces results. |
| Blind A/B comparison eval | Anthropic skill-creator pattern; not applicable to LSD's regression-harness eval model |

---

## Suggestions for the next contributor (superseded)

This section originally tracked open TODOs as of v0.5.0. It has been superseded: most of
its items are now done (see "Decisions since v0.5.0" and the bugs table below), and
tracking live TODOs here duplicated — and eventually contradicted — the same list
maintained elsewhere. Live, actionable suggestions now live in two places, split by kind:

- **README.md § Suggested next steps** — near-term items, including anything blocked only
  on configuring an LLM provider or regenerating an eval baseline.
- **ROADMAP.md § Open gaps for the next contributor** — items blocked on an external
  dependency or upstream release (PixelRAG, retrieval backend upgrade, semantic-drift
  embedding similarity), plus unscheduled backlog (eval case expansion, description
  optimizer, MCP server scaffold).

This document remains the place for *why* decisions were made — the numbered decisions
above (including "Decisions since v0.5.0") and the bugs table below — not for tracking
what's left to do.

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

## Post-v0.5 process notes

Two smaller items from later review passes that don't fit the decision-log format
above: `.gitignore` was added (the editable install was dropping untracked
`*.egg-info/` and `__pycache__/` as noise in `git status`), and `AGENTS.md` +
`CLAUDE.md` were added as the agent-facing working guide (see AGENTS.md itself
for what it covers). Full change lists for every post-v0.5 round are in
CHANGELOG.md; session/commit attribution is in PROVENANCE.md.

---

## Provenance of this document

Written by Perplexity Computer (model: claude-sonnet-4-6) in the same session that produced v0.5.0, as part of the "prime-time readiness" review. The session thread is preserved in the project owner's Perplexity history at the canonical thread URL recorded in PROVENANCE.md.
