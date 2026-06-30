# Source Policy

## Canonical source
- URL: https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing
- Active source version: source_v1
- Local artifact: source.md

## Ingestion mode
- Mode: text-first
- Visual artifacts: none

## Update mode
- Mode: monitored
- Promotion policy: manual approval

## Refresh workflow
1. Fetch the current page.
2. Normalise into comparable text format.
3. Compare against the stored hash.
4. If changed, classify as trivial, moderate, or material.
5. Trivial: log only.
6. Moderate: prepare update candidate for review.
7. Material: prepare new source version, new skill draft, and changelog entry.
8. Never promote without review.

## Fallback order
1. Local source artifact
2. Wayback snapshot
3. Secondary archive
4. Previous approved version

## Change classification guidance
- New signal categories → material
- Changed caveats or scope warnings → material
- Rewording of existing signals → moderate
- Typos or minor phrasing → trivial
