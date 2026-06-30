# Architecture

## Overview

LSD is a meta-skill builder that converts a URL into a reusable Claude skill package. It is designed around four separable concerns:

1. **Ingestion** — fetch and preserve the source
2. **Classification** — decide what kind of skill the page supports and what ingestion mode is appropriate
3. **Compilation** — extract, normalise, and generate the skill package
4. **Governance** — track the source dependency and manage updates

## Pipeline stages

```
URL
 └─► Fetch + archive
      └─► Normalise source
           └─► Classify source fit
                └─► Map skill opportunities
                     └─► Choose ingestion mode
                          └─► Extract rules / procedures / examples
                               └─► Compile SKILL.md
                                    └─► Write package (metadata.json, source-policy.md, ...)
                                         └─► Register source dependency
```

## Ingestion modes

| Mode | When to use | Visual artifacts |
|---|---|---|
| text-first | Prose-heavy, parser-friendly pages | No |
| hybrid | Repo pages, docs with tables/code/structure | Yes (screenshot + tiles) |
| visual-first | Dashboards, parser-hostile, diagram-dominant | Yes (primary) |

## Package structure

Every generated package is a directory containing:

```
<skill-name>/
├── SKILL.md                 # The compiled skill
├── source.md                # Normalised source notes
├── metadata.json            # Source dependency, fit, governance, artifacts
├── source-policy.md         # Refresh, fallback, promotion rules
├── skill-opportunities.md   # Ranked opportunity map
├── extraction-report.md     # Rationale for build decisions
├── CHANGELOG.md             # Package history
└── visual/                  # Optional: rendered-page.png, tiles/
```

## Routing logic

The ingestion mode router uses three primary signals:

- **Parser hostility**: does the page rely on layout, diagrams, or canvas to convey meaning?
- **Visual structure density**: are tables, code blocks, UI components, or images load-bearing?
- **Source category**: wiki/article → text-first; repo/dashboard → hybrid; interface/app → visual-first

## Source dependency tracking

Every package records:
- canonical URL and local normalised artifact
- last-checked and last-successful-fetch timestamps
- normalised hash for change detection
- archive URLs
- fallback order
- promotion policy and criticality

When the source changes, LSD compares the new normalised result against the stored hash, classifies the change as trivial/moderate/material, and produces an update candidate for review before any promotion.
