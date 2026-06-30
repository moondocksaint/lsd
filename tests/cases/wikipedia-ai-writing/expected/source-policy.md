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
1. Fetch and normalise the current page.
2. Compare normalised hash against stored value.
3. Classify change: trivial / moderate / material.
4. Trivial: log only. Moderate: prepare update candidate. Material: new source version + skill draft.
5. Never promote without review.

## Fallback order
1. Local source artifact
2. Wayback snapshot
3. Secondary archive
4. Previous approved version
