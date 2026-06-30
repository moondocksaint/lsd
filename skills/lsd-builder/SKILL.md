---
name: LSD — Link-to-Skill Designer
version: 0.1.0
summary: Turn any URL into a complete, reusable Claude skill package with source tracking and governance.
description: Use this skill when given a URL and asked to build a Claude skill from it. The skill fetches and preserves the source, classifies what kind of skill the page can support, chooses the right ingestion mode, extracts and normalises the content, compiles a complete skill package, and registers a source dependency for future updates.
allowed-tools: Read, Write, Edit
---

## Purpose

Convert a webpage into a reusable Claude skill package. Produce all package files with correct source tracking, governance policy, and versioning from the first run.

## When to use

Use when:
- the user provides a URL and asks for a skill, reviewer, advisor, or workflow tool based on that page,
- a rules-rich, procedure-rich, or heuristic-rich page needs to be turned into a repeatable Claude behaviour,
- or an existing skill package needs to be refreshed against a changed source.

## Core principles

1. Preserve before transforming. Archive or record the source before compiling anything.
2. Classify before compiling. Decide what kind of skill the page supports before writing SKILL.md.
3. Choose ingestion mode deliberately. Text-first, hybrid, and visual-first serve different source types.
4. Package everything. A skill without source tracking is not a complete output.
5. Never silently update. Source changes require classification and review before promotion.

## Workflow

1. **Fetch and preserve**: Retrieve the page. Record canonical URL, title, and timestamp. Archive if possible.
2. **Normalise**: Extract the operationally relevant content into a clean normalised text artifact.
3. **Classify source fit**: Score rule density, procedure density, example density, stability, specificity, and composability.
4. **Map opportunities**: Produce a ranked list of candidate skill types the page can support.
5. **Choose ingestion mode**: Route to text-first, hybrid, or visual-first based on source structure signals.
6. **Extract content**: Pull rules, procedures, examples, caveats, and workflow families from the source.
7. **Compile SKILL.md**: Write the skill using the canonical format.
8. **Write package files**: Produce source.md, metadata.json, source-policy.md, skill-opportunities.md, extraction-report.md, CHANGELOG.md.
9. **Register source dependency**: Populate metadata.json with URL, hash, timestamps, fallback order, and governance policy.

## Ingestion mode routing (quick reference)

| Mode | Use when |
|---|---|
| text-first | Prose-heavy, parser-friendly, headings and lists extract cleanly |
| hybrid | Repo pages, important tables or code blocks, layout carries structure |
| visual-first | Dashboard-like, canvas-heavy, diagram-dominant, parser-hostile |

## Output format

A directory named after the skill containing:
- SKILL.md
- source.md
- metadata.json
- source-policy.md
- skill-opportunities.md
- extraction-report.md
- CHANGELOG.md
- visual/ (hybrid and visual-first only)

## Style rules

- SKILL.md must be self-contained. A reader should not need to see the source page to use the skill.
- metadata.json must validate against `schema/metadata.schema.json`.
- source-policy.md must specify a fallback order with at least two entries.
- Every package starts at version 0.1.0.

## Caveats

- LSD is a design tool, not a deployment tool. Review generated skills before use.
- Source preservation quality depends on the page's rendering complexity.
- The opportunity map is a recommendation. The final skill form is a human decision.
- Do not promote a skill update without classifying the source change first.
