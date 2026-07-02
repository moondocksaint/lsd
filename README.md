# LSD — Link-to-Skill Designer

> Turn any webpage into a reusable Claude skill.

LSD is a meta-skill builder. Give it a URL. It reads the page, classifies what kind of skill the page supports, chooses the right ingestion mode (text-first, hybrid, or visual-first), extracts and normalises the source, generates a complete skill package, and wires up source-dependency tracking so the skill can be refreshed when the page changes.

## Quick start

```
lsd build <url>
```

## Docs

See [`docs/`](docs/) for architecture, spec, and examples.

## Examples

See [`examples/`](examples/) for filled example packages:
- [`examples/wikipedia-ai-writing/`](examples/wikipedia-ai-writing/) — text-dominant source
- [`examples/pixelrag-repo/`](examples/pixelrag-repo/) — hybrid / visually structured source

## Status

v0.5.0 — active development. See [`ROADMAP.md`](ROADMAP.md) for the full vision and [`CHANGELOG.md`](CHANGELOG.md) for what's new.

## What LSD does and who it's for

LSD (Link-to-Skill Distiller) is a build tool and meta-skill that converts URLs into installable, versioned AI skill packages conforming to the [Agent Skills open standard](https://agentskills.io). It is aimed at:

- **Developers** who want to extract reusable procedural knowledge from documentation, API references, or internal wikis and package it as a skill once, then deploy it across Claude, Claude Code, VS Code Copilot, or any Agent Skills-compatible environment.
- **Power users** who encounter a page worth turning into a repeatable agent workflow and want a structured, governed package with source-dependency tracking rather than a one-off paste into a system prompt.
- **Teams** maintaining living skill libraries, where sources change over time and drift must be detected and managed.

### What the pipeline does

1. **Fetches** the URL and classifies source type (HTML, PDF, image, gated, social, unsupported).
2. **Routes** to an ingestion mode (text-first, hybrid, or visual-first) based on page structure.
3. **Normalises** the source into clean Markdown (`source.md`).
4. **Maps opportunities** — classifies the page into one or more skill types, assesses source fit, detects tool candidates, and determines whether to build, build-with-caveats, build-multiple, or defer.
5. **Compiles** a complete `SKILL.md` using an LLM backend (Anthropic or any OpenAI-compatible provider) with a heuristic skeleton fallback when no LLM is configured.
6. **Writes** a full package: `SKILL.md`, `source.md`, `metadata.json`, `source-policy.md`, `skill-opportunities.md`, `extraction-report.md`, `CHANGELOG.md`, `README.md`, and maintenance scripts.
7. **Tracks drift** — every package records a `normalized_hash` against which future `lsd check` runs compare the live source.

For multi-source builds, conflict detection (gaps, contradictions, overlaps) runs automatically and is reported in `conflicts.md`.

---

## Agentskills spec adherence

LSD targets full conformance with the [Agent Skills specification](https://agentskills.io/specification). The allowed frontmatter fields (sourced from [`skills-ref/src/skills_ref/validator.py`](https://github.com/agentskills/agentskills/blob/main/skills-ref/src/skills_ref/validator.py)) are: `name`, `description`, `license`, `allowed-tools`, `metadata`, `compatibility`. Any other top-level frontmatter key fails validation.

The table below records every known deviation — deliberate extensions that go beyond the spec — and confirms there are no violations.

| Area | Spec requirement | LSD behaviour | Status |
|------|-----------------|---------------|--------|
| `name` field | Lowercase alphanumeric + hyphens, max 64 chars, no leading/trailing/consecutive hyphens, must match directory name, cannot contain `anthropic` or `claude` | Enforced by `lsd package --zip`; the ZIP root directory is renamed to match the `name` slug. Names containing reserved words are rejected. | **Compliant** |
| `description` field | Max 1024 chars, non-empty, third-person, describes what and when, no XML tags | Generated and present in all output SKILL.md files | **Compliant** |
| `license` field | Optional, short string or file reference | Present in `lsd-builder` meta-skill (`Apache-2.0`); generated skills omit it (not required) | **Compliant** |
| `compatibility` field | Optional, plain string ≤ 500 chars, only if environment requirements exist | Used as a plain string in meta-skill; not emitted in generated skills unless required | **Compliant** |
| `metadata` field | Arbitrary key-value map | LSD-specific fields (`lsd_version`, `compiler_model`, `source_url`, `generated_at`) placed in `metadata:` map as specified | **Compliant** |
| `allowed-tools` field | Space-separated string, experimental | Used in `lsd-builder` meta-skill; generated skills omit it | **Compliant** |
| File structure | `SKILL.md` required; `scripts/`, `references/`, `assets/` optional | All present; LSD adds `source.md`, `metadata.json`, `source-policy.md`, `skill-opportunities.md`, `extraction-report.md`, `CHANGELOG.md`, `README.md` | **Extension** — additional files are spec-permitted ("any additional files or directories") |
| Progressive disclosure | Discovery (name+desc) → Activation (full SKILL.md) → Execution (resources) | Meta-skill loads `references/` files on demand with explicit `when-to-read` guidance; generated SKILL.md references `scripts/` and `source.md` on demand | **Compliant** |
| SKILL.md body length | < 500 lines / ~5,000 tokens recommended | `lsd-builder/SKILL.md` is 275 lines; generated SKILL.md files are typically 80–150 lines | **Compliant** |
| Directory name = `name` slug | Required | Enforced at packaging time | **Compliant** |

### Deviations from Anthropic skill-creator patterns

The Anthropic [`skill-creator`](https://github.com/anthropics/skills/tree/main/skills/skill-creator) represents Anthropic's recommended workflow for creating, testing, and iterating on skills via an eval-driven loop. LSD's approach differs in the following intentional ways:

| Pattern | skill-creator approach | LSD approach | Rationale |
|---------|----------------------|--------------|-----------|
| Skill creation trigger | Conversational / iterative eval loop | Source URL as structured input | LSD is a build tool; the URL fetch replaces the interview |
| Eval loop | Draft → parallel runs → human review → iterate | `lsd eval` against committed `expected/` snapshot with rubric scoring | LSD targets regression-harness eval, not interactive iteration |
| Description optimization | `run_loop.py` with 20-query trigger eval set, 60/40 train/test | Description written by LLM compiler from source intent | Different scope: LSD generates skill content, not triggering accuracy |
| Test cases | `evals/evals.json` with assertions, parallel with/without-skill runs | `tests/cases/` with `input.json` + `expected/` snapshot | LSD uses pytest-style unit tests throughout |
| Packaging | `package_skill.py` → `.skill` file | `lsd package --zip` → ZIP with inner folder named by slug | Both produce installable archives; format differs by target client |
| Source grounding | "Extract from hands-on task" / synthesize from artifacts | URL fetch + normalise pipeline | LSD automates the extraction step |
| "Gotchas" section | Recommended as highest-value content | Present in meta-skill (drift playbook, verdict playbook); **absent from generated SKILL.md** | Generated skills do not have a `## Gotchas` section — a future quality improvement |

These are by-design differences stemming from LSD's identity as a CLI build tool rather than a conversational skill assistant.

---

## Permanent open items and unresolvable gaps

The following items are structurally unresolvable — they arise from the architectural boundary between what a CLI can do and what a conversational skill can do. They are documented here so future contributors understand them as design decisions, not bugs.

### CLI / meta-skill interaction gaps (by design)

| Gap | Why unresolvable | Mitigation |
|-----|-----------------|------------|
| Interactive interview | The CLI has no interactive session; `lsd build` takes URLs and flags, not a multi-turn conversation | The `lsd-builder` meta-skill provides the interview layer on top of the CLI |
| Skill name confirmation | The CLI accepts `--name`; it cannot prompt the user mid-run | Post-build step in the meta-skill: the agent confirms the slug after build completes |
| Opportunity discussion | The CLI emits `skill-opportunities.md`; it cannot pause to negotiate with the user | Post-build step in the meta-skill: the agent surfaces the verdict and tool candidates |
| Source fit gate | The CLI will build even from low-fit sources (it only warns); it cannot refuse mid-pipeline | The meta-skill enforces the `defer` verdict by not calling `lsd build` |
| `motivation.json` recording | The CLI has no concept of build motivation; it records what, not why | The meta-skill writes `motivation.json` after the interview; the `motivation-check.py` script reads it |

### Known limitations (technical)

| Limitation | Detail |
|-----------|--------|
| PixelRAG backend is a stub | `src/lsd/backends/pixelrag.py` wraps the `pixelrag-render` package, which has not been publicly released. Visual-first ingestion falls back to text-first automatically. |
| `lsd eval` requires a committed `expected/` snapshot | The first baseline must be created manually (or by running a trusted build and committing the output). There is no `--init` command yet. |
| `skills-ref validate` is an external CLI | Validation is referenced in SKILL.md and docs but is not run by LSD itself during build. Users must install and run it separately. |
| Generated SKILL.md has no `## Gotchas` section | Community data shows Gotchas sections are the highest-value content for environment-specific facts. LSD does not generate them; adding this to the compiler is a near-term improvement. |
| No web product | ROADMAP.md describes a hosted web product; it does not exist yet. |
| No marketplace listing support | ROADMAP.md describes marketplace integration; not implemented. |

---

## Suggested next steps

These are the most valuable near-term investments, ordered by impact-to-effort ratio.

### High impact

1. **Add a `## Gotchas` section to the compiler** — The LLM compiler pass should extract environment-specific facts, API quirks, and non-obvious constraints from the source and emit them as a `## Gotchas` block in the generated `SKILL.md`. Community data consistently identifies this as the highest-ROI content in a skill.

2. **Activate `skills-ref validate` in the build pipeline** — Run the validator as a post-build subprocess call and surface warnings in the CLI output. This closes the gap between "we document spec compliance" and "we enforce it automatically."

3. **Add `lsd eval --init`** — Run a build and commit the output as the `expected/` snapshot. This removes the manual step that blocks first-time eval setup.

4. **PixelRAG backend** — When `pixelrag-render` becomes publicly available, wire it into the existing `PixelRAGBackend` adapter. The interface is already in place; only the import and method implementations need to be activated.

### Medium impact

5. **`lsd check --all-sources`** — `lsd check` currently works per-source. A flag that checks every source in `metadata.json → source_dependencies` and reports a unified drift summary would complete the multi-source maintenance workflow.

6. **`lsd check` CI integration example** — Add a GitHub Actions workflow in `.github/workflows/` that runs `lsd check` on a configured package directory and opens an issue on SUBSTANTIAL drift. This completes the maintenance story.

7. **Retrieval backend upgrade** — The `NaiveRetrievalBackend` (full-context stuffing with 50K token guard) is functional but basic. When a higher-quality embedding or chunking approach is available, the `RetrievalBackend` ABC makes it a drop-in swap. The swap criteria are documented in ROADMAP.md and SKILL.md.

### Longer term (from ROADMAP.md)

8. Hosted web product — drag-and-drop URL input, no CLI required
9. Marketplace listing support (claude.ai skill store, VS Code Marketplace)
10. Org skill library integration
11. Skill composition — build a skill that references other skills as dependencies
12. Offline mode — embed a local model for the LLM compiler pass
