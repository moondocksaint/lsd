---
name: lsd-builder
description: >
  Build a structured, versioned agent skill package from one or more source URLs
  using LSD (Link-to-Skill Distiller). Load this skill whenever the user says
  "build a skill from", "distill this URL into a skill", "run lsd build", "create
  a skill package from a link", "generate a skill from", or provides one or more
  URLs and asks to turn them into an agent skill. Also load when the user asks to
  check a skill package for staleness ("lsd check"), run an eval against a baseline
  ("lsd eval"), or inspect the source-dependency layer of a package. Use this skill
  even if the user does not explicitly say "skill" — any request to convert a URL
  into something an agent can use repeatedly is in scope.
license: Apache-2.0
compatibility: Requires lsd CLI (pip install lsd), bash, and at least one configured LLM provider via env vars (LSD_LLM_PROVIDER + LSD_MODEL). See references/provider-config.md.
metadata:
  lsd_version: "0.5.0"
  author: moondocksaint
---

# LSD Builder

LSD (Link-to-Skill Distiller) converts one or more source URLs into a versioned,
structured agent skill package ready for installation in Claude, VS Code Copilot,
Gemini, or any agent that supports the [Agent Skills open standard](https://github.com/agentskills/agentskills).

**Before doing anything else:** read `references/interview-guide.md` — it contains
the full interview flow, Guided/Express mode instructions, and the source fit
response taxonomy. Do not skip it.

Load `references/provider-config.md` for LLM provider setup.
Load `references/output-schema.md` for the full package file schema.
Load `references/rubric.md` for eval scoring criteria.

---

## Mode selection — ask this first

Before any other question, offer the user a choice of build mode. Do this in
a single sentence, not a paragraph:

> "Quick question before we start: do you want **Express mode** (I ask three
> quick questions then build) or **Guided mode** (I fetch the source first,
> share what I find, and we talk through it before building)? Express is faster;
> Guided catches mismatches between what you want and what the source actually
> contains."

If the user is in a hurry or has already provided a URL with clear intent, default
to Express and mention you're doing so. If the user's intent seems vague or the
URL looks like it might not be a good fit (news article, product page, homepage),
recommend Guided.

**Express mode:** run Phase 1 (three questions + name proposal), then build immediately.

**Guided mode:** run Phase 1 (three questions), fetch the URL in parallel while
asking, then run Phase 2 (post-fetch Socratic exchange, depth-limited to two
turns), then confirm name and build.

Full instructions for both modes are in `references/interview-guide.md`.

---

## What to do after building

After `lsd build` completes, always do the following steps **in order**:

1. **Show the verdict.** Read `metadata.json → opportunity_summary.recommended_action`.
   Map it to user language using the verdict playbook below. If action is `defer`,
   stop here — do not proceed to step 2.

2. **Show the fit score and skill type.** Report `overall_fit` and
   `recommended_skill_type` from `metadata.json`.

3. **Confirm the skill name.** Show the proposed slug from `SKILL.md` frontmatter
   and ask the user to confirm or rename.
   - In Express mode this is the first time you ask about the name.
   - In Guided mode you already agreed on a name; confirm the final slug matches.

4. **Surface tool candidates (if any).** Check `skill-opportunities.md` for a
   `## Tool candidates` section. If present, surface these explicitly:
   > "This source also triggered tool candidate detection: [type]. A [type] would
   > let you call the underlying capability live rather than just know about it.
   > Want me to help you decide whether to build the tool alongside the skill?"
   Do this before moving to secondary skills — tool candidates are higher priority.

5. **Show secondary skill opportunities.** Show the `## Skill candidates` list from
   `skill-opportunities.md` and ask if any secondary skills are worth queuing now.

6. **Flag quality issues.** If source fit is `low` or the build used the heuristic
   fallback (no LLM — `compiler_model` is `null` or `"heuristic"` in `metadata.json`),
   call this out explicitly before offering installation.

7. **Offer packaging — only if verdict is not `defer`.** Run:
   ```bash
   lsd package ./my-skill/ --zip
   ```
   to produce a ZIP for claude.ai installation. Do not offer this step if the
   verdict was `defer` or if the user explicitly declined the build.

8. **Remind the user about the maintenance scripts.** The package includes
   `scripts/check-drift.py` and `scripts/motivation-check.py`. Mention these:
   > "Your package includes two maintenance scripts in `scripts/`. Run
   > `check-drift.py` periodically to detect upstream source changes, and
   > `motivation-check.py` after any drift event to verify your original build
   > intent still applies."

---

## Verdict playbook

Use this table to translate `recommended_action` from `metadata.json` into agent
behaviour. The CLI also renders this as a coloured panel after each build.

| Action | User message | Agent behaviour |
|--------|-------------|-----------------|
| `build_one_skill` | "Build complete — source is a good fit." | Proceed through all post-build steps. |
| `build_multiple_skills` | "Build complete — source supports [N] skill types. This build covers [primary type]." | Proceed; note the secondary types in step 5. |
| `build_with_caveats` | "Build complete, but this source has known limitations. Review before promoting." | Proceed, but make step 4 (tool candidates) and step 6 (quality flags) prominent. Read and surface every item in `metadata.json → opportunity_summary.assessment.limitations`. |
| `defer` | "This source is not a good fit for a skill. [reason from assessment.summary]." | Do not run `lsd build`. Explain the reason. Offer to help the user find a better source. |

For `build_with_caveats`, always quote at least one limitation sentence verbatim
from `skill-opportunities.md → ## Assessment → Limitations`.

---

## Drift response playbook

After running `lsd check <package-dir>`, map the drift state to the following
agent actions. Do not skip states or merge behaviours — each state has a distinct
response.

| State | Meaning | Agent action |
|-------|---------|-------------|
| `UNCHANGED` | Hash identical to last build | Confirm no action needed. Offer to re-run `motivation-check.py` if time has elapsed. |
| `MINOR` | Content changed, heading structure intact | Offer to rebuild: "The source has changed. Want me to rebuild the skill now?" Run `lsd build <url> --output <package-dir>` only after confirmation. |
| `SUBSTANTIAL` | Major rewrite — new sections, large content shift | Warn: "The source has been substantially rewritten. Your original build motivation may no longer apply." Run `motivation-check.py` first. Do not rebuild without explicit user confirmation and a second look at the source fit. |
| `GONE` | URL unreachable (4xx/5xx/timeout) | Preserve the existing package. "The source URL is unreachable. Your existing package is intact. Check `source-policy.md` for the fallback chain." Do not overwrite. |
| `REDIRECTED` | URL permanently moved | "The source has moved to [new URL]. Want me to update the canonical URL in `metadata.json` and rebuild?" Only update after confirmation. |

For multi-source packages, any single-source drift state of `SUBSTANTIAL` or
`GONE` should be escalated to the user even if the other sources are `UNCHANGED`.

---

## CLI reference

```bash
# Single source — full package
lsd build https://example.com/docs/api --output ./my-skill/

# Single source — with explicit name (slug)
lsd build https://example.com/docs/api --output ./my-skill/ --name my-api-guide

# Multi-source — conflict detection runs automatically
lsd build https://source1.com https://source2.com --output ./my-skill/

# Check a package for drift
lsd check ./my-skill/              # package directory (reads metadata.json)
lsd check https://example.com      # single URL (classify + route, no drift state)

# Package for webapp/desktop installation (produces ZIP)
lsd package ./my-skill/ --zip

# Eval against committed expected/ snapshot
lsd eval tests/cases/my-case/

# Validate skill against agentskills spec
skills-ref validate ./my-skill/

# Run maintenance scripts (from package directory)
python scripts/check-drift.py
python scripts/motivation-check.py
```

---

## Package structure

Every `lsd build` run produces the following directory:

```
<package-dir>/
├── README.md               ← start here; agent entry point for versioning
├── SKILL.md                ← load this into your agent
├── source.md               ← normalised source text
├── source-policy.md        ← update policy, fallback chain
├── skill-opportunities.md  ← skill types + tool candidates + honest assessment
├── extraction-report.md    ← fit scores, routing rationale, limitations
├── metadata.json           ← machine-readable provenance (hash, model, timestamps)
├── CHANGELOG.md            ← human-readable version history
└── scripts/
    ├── check-drift.py      ← detect upstream source drift (run manually or in CI)
    └── motivation-check.py ← verify original build intent still applies post-drift
```

For multi-source builds, additional files are added:
`sources-index.md`, `source-1.md … source-N.md`, `conflicts.md`, `index.md`.

---

## Spec compliance (agentskills standard)

All skills generated by LSD must pass `skills-ref validate`. Key rules:

- `name` in `SKILL.md` frontmatter: lowercase, alphanumeric + hyphens only,
  max 64 chars, must match the folder name exactly.
- LSD-specific fields (`lsd_version`, `compiler_model`, `source_url`,
  `generated_at`) go in the `metadata:` map, not as top-level frontmatter keys.
- `compatibility` is a plain string, not a map.
- `allowed-tools` is a space-separated string of tool patterns.

LSD generates spec-compliant skills automatically. If you are manually editing
a generated `SKILL.md`, run `skills-ref validate` before installing.

---

## Installation paths

| Environment | How to install |
|---|---|
| Claude.ai / Claude desktop | `lsd package ./my-skill/ --zip` → Customize > Skills > + > Upload a skill |
| Claude Code | Place skill folder in `~/.claude/skills/<name>/` |
| VS Code Copilot | Place skill folder in `.agents/skills/<name>/` in your project |
| Gemini / ChatGPT | Paste `SKILL.md` body into custom instructions; attach other files as knowledge |

For webapp/desktop installation the folder name inside the ZIP must exactly match
the `name` field in `SKILL.md` frontmatter. `lsd package --zip` handles this.

---

## Source-dependency tracking

Every package records a `source_dependency` block in `metadata.json`. Running
`lsd check ./my-skill/` re-fetches the source and compares `normalized_hash`.
See the **Drift response playbook** above for per-state agent behaviour.

For multi-source packages, drift in any one source triggers a check report for
all sources.

---

## Multi-source conflict detection

When two or more URLs are passed, conflict detection runs automatically. Three
types are reported in `conflicts.md`:

| Type | Description |
|---|---|
| `gap` | A topic present in one source is absent from another |
| `contradiction` | Negation patterns near shared key terms suggest opposing claims |
| `overlap` | Near-duplicate sentences indicating redundant coverage |

Resolve conflicts before promoting the skill. `conflicts.md` includes resolution
guidance for each detected conflict.

---

## Modular backends — when to swap

All three backend layers follow the same swap-candidate pattern. Criteria are
documented in module docstrings; the summary:

**Retrieval backend** (`src/lsd/retrieval/`): swap when combined token estimate
exceeds 50K tokens and rubric score drops below 12/14, or when a
NotebookLM-quality RAG API becomes available via simple HTTP call.

**LLM backend** (`src/lsd/llm/`): swap or add when a new provider achieves
≥12/14 at meaningfully lower cost, or when a new API surface (e.g. new
OpenAI-compatible endpoint) is not covered by the existing `openai-compat` path.

**PixelRAG backend** (`src/lsd/backends/`): swap when a new screenshot-to-text
API achieves better extraction fidelity on JS-heavy pages, or when `pixelrag-render`
releases a breaking API change.

See `references/provider-config.md` for adding new LLM providers.
