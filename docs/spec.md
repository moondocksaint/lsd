# LSD Meta-Skill Specification

## Identity

- **Name**: Hyperlink-to-Skill Builder (LSD — Link-to-Skill Designer)
- **Version**: 0.1.0
- **Description**: Given a URL, produce a complete, reusable Claude skill package with source-dependency tracking, versioning, and governance.

## Purpose

LSD answers the question: *given a rules-rich, procedure-rich, or heuristic-rich webpage, what reusable Claude skill does this page support, and how should that skill be built, packaged, and maintained?*

## Core responsibilities

1. Preserve the source before transforming it.
2. Classify source fit and opportunity type.
3. Choose the right ingestion mode.
4. Extract and normalise operational content.
5. Compile a complete skill package.
6. Register a source dependency with refresh and governance policy.

## Input contract

| Field | Required | Description |
|---|---|---|
| url | yes | The canonical URL of the source page |
| output_mode | no | `skill_only`, `full_package` (default), `opportunity_map_only` |
| ingestion_mode_override | no | Force `text-first`, `hybrid`, or `visual-first` |
| context | no | Project memory, related skills, user intent |

## Output contract

| File | Always present | Description |
|---|---|---|
| SKILL.md | yes | The compiled skill |
| source.md | yes | Normalised source |
| metadata.json | yes | Full package metadata |
| source-policy.md | yes | Refresh and governance policy |
| skill-opportunities.md | yes | Opportunity map |
| extraction-report.md | yes | Build rationale |
| CHANGELOG.md | yes | Package history |
| visual/ | hybrid/visual-first only | Rendered artifacts |

## Ingestion mode routing

The builder selects ingestion mode before extracting any content.

**Prefer text-first when**:
- the page is prose-heavy and parser-friendly
- headings and lists extract cleanly
- tables are simple or nonessential

**Prefer hybrid when**:
- the page includes code blocks, tables, repo structure, cards, badges, or visual grouping
- text extraction is good but may miss emphasis or structure
- the source is important enough to justify a second preservation layer

**Prefer visual-first when**:
- the page is dashboard-like, parser-hostile, canvas-heavy, or diagram-dominant
- meaningful content is embedded in images or layout
- text extraction would clearly flatten away operational meaning

## Skill SKILL.md format

```yaml
---
name: <skill name>
version: <semver>
summary: <one sentence>
description: <when to use this skill>
allowed-tools: <comma-separated tool names or Read/Write/Edit>
---

## Purpose
## When to use
## Core principle
## Workflow (numbered steps)
## Output format
## Style rule
## Caveats
```

## metadata.json schema

See `schema/metadata.schema.json`.

## Source fit dimensions

| Dimension | Description |
|---|---|
| rule_density | Density of explicit heuristics and rules |
| procedure_density | Density of multi-step workflows |
| example_density | Density of worked examples |
| stability | How frequently the source is likely to change |
| specificity | How narrow and focused the operational guidance is |
| composability | Whether the skill could combine with other skills |

## Governance

- Every package uses monitored updates by default.
- Promotion requires manual approval for moderate and material changes.
- Trivial changes (typos, minor phrasing) are logged but do not block the active skill.
- All source changes are classified as trivial, moderate, or material before any update is prepared.

## Caveats

- LSD is a design and compilation tool, not an automatic deployer. All generated skills should be reviewed before use.
- Source preservation is advisory; some sources will be fetched in degraded form depending on rendering complexity.
- The skill opportunity map is a recommendation, not a guarantee.
