# LSD Output Package Schema Reference

This document describes every file in an LSD output package. Files marked
**(single)** appear in single-source builds. Files marked **(multi)** appear
only in multi-source builds. Files marked **(both)** appear in both.

---

## SKILL.md (both)

A loadable agent skill file following Anthropic skill-creator anatomy.

**YAML frontmatter fields:**

| Field | Type | Description |
|---|---|---|
| `name` | string | Slug-style skill name (e.g. `wikipedia-ai-writing`) |
| `description` | string | Trigger description — what the skill does and when to load it |
| `compiler_model` | string | Model that generated this file (e.g. `api/mercury-2`) |
| `source_url` | string | Canonical source URL |
| `generated_at` | ISO-8601 | Build timestamp |
| `lsd_version` | string | LSD package version used |

**Body sections:**

- `## Core principle` — one-paragraph distillation of what the source teaches
- `## Workflow` — step-by-step process extracted from the source
- `## Output format` — expected agent output format when this skill is active
- `## Key concepts` — glossary of important terms
- `## Examples` — representative examples from the source (if present)

---

## README.md (both)

Agent entry point for versioning, update workflow, and provenance.

**Sections:**

- `## Package overview` — source URL, generated_at, lsd_version
- `## Provenance` — table with `compiler_model`, `source_type`, `token_count`
- `## Source dependency` — `normalized_hash`, `last_checked_at`, `update_policy`
- `## Version & update workflow` — instructions for checking drift and rebuilding
- `## Files in this package` — manifest of all package files

---

## metadata.json (both)

Machine-readable package manifest. Root keys:

```jsonc
{
  "schema_version": "0.4",
  "package": {
    "name": "...",
    "generated_at": "2026-06-30T10:00:00Z",
    "lsd_version": "0.4.0",
    "compiler_model": "api/mercury-2"   // null if heuristic fallback
  },
  "source_dependency": {               // single-source
    "url": "https://...",
    "normalized_hash": "sha256:...",
    "last_checked_at": "2026-06-30T10:00:00Z",
    "last_successful_fetch_at": "2026-06-30T10:00:00Z",
    "update_policy": "check-monthly",
    "fallback_chain": []
  },
  "source_dependencies": [...],        // multi-source: array of above
  "artifacts": {
    "skill_file": "SKILL.md",
    "readme_file": "README.md",
    "source_file": "source.md",        // single
    "source_files": ["source-1.md"],   // multi
    "metadata_file": "metadata.json",
    "policy_file": "source-policy.md",
    "opportunities_file": "skill-opportunities.md",
    "report_file": "extraction-report.md",
    "changelog_file": "CHANGELOG.md",
    "conflicts_file": "conflicts.md",  // multi only
    "index_file": "index.md"           // multi only
  }
}
```

---

## source.md (single) / source-N.md (multi)

Full normalized source text after fetch + HTML/PDF/image extraction.
Not committed to `expected/` snapshots in eval cases (too large, low diff value).

---

## source-policy.md (both)

Human and agent-readable update policy for the source dependency.

**Sections:**

- `## Update policy` — when and how to refresh the package
- `## Fallback chain` — ordered list of fallback URLs if primary goes offline
- `## Fetch configuration` — headers, auth hints, known gate status

---

## skill-opportunities.md (both)

A list of skill-building opportunities detected in the source. Each entry
includes a candidate skill name, rationale, and suggested trigger phrase.
Multi-source builds deduplicate across sources.

---

## extraction-report.md (both)

Pipeline run summary:

- Source type detected (`html`, `pdf`, `image`, `google_doc`, `social`, `gated`, `unsupported`)
- Token count estimate
- Retrieval backend used and token threshold
- LLM provider and model
- Fetch duration, compile duration
- Any warnings or errors during the run

---

## CHANGELOG.md (both)

Package-level changelog. Starts with a single entry at build time. Agents
appending new versions should follow Keep a Changelog format.

---

## conflicts.md (multi only)

Cross-source conflict report. Three sections:

### Gaps
Topics (headings) present in some sources but absent from others. Each entry
lists the missing topic, which source covers it, and which sources omit it.

### Contradictions
Pairs of sentences from different sources that appear to make opposing claims
about the same key term. Heuristic: negation words (`not`, `never`, `unlike`,
`instead`) near a shared noun or phrase.

### Overlaps
Near-duplicate sentences across sources (> 0.85 normalized edit similarity).
Indicates redundant coverage — may be intentional if sources cite each other,
or may indicate one source is derived from another.

**Resolution guidance** for each conflict type is included inline.

---

## sources-index.md (multi only)

Table of all sources: URL, fetch status, source type, token count, and whether
each source was successfully incorporated into the distilled `SKILL.md`.

---

## index.md (multi only)

Top-level package overview for multi-source builds: list of sources, conflict
summary counts, and links to all package files.
