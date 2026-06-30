# Source Policy

## Canonical source
- URL: https://github.com/StarTrail-org/PixelRAG
- Active source version: source_v1
- Local artifact: source.md

## Ingestion mode
- Mode: hybrid
- Visual artifacts: visual/rendered-page.png, visual/tiles/
- Reconciliation required: yes

## Update mode
- Mode: monitored
- Promotion policy: manual approval

## Refresh workflow
1. Fetch and normalise the current page text.
2. Compare against stored hash.
3. Refresh rendered visual artifacts when available.
4. Compare command tables, installation steps, workflow stages, and plugin framing.
5. Classify change as trivial, moderate, or material.
6. Command surface changes → material.
7. Plugin install or workflow changes → material.
8. Framing or description rewording → moderate.
9. Typos → trivial.
10. Prepare update candidate for review before any promotion.

## Fallback order
1. Local source artifact
2. Wayback snapshot
3. Secondary archive
4. Previous approved version

## Change classification guidance
- New pipeline stages → material
- Changed command syntax → material
- Changed plugin instructions → material
- Rewording of project framing → moderate
- Typos or minor phrasing → trivial
