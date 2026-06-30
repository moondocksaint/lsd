# Extraction Report

## Decision

The source is strongly suitable for an ingestion-advisor skill and a good exemplar of hybrid ingestion.

## Why

The repository explicitly argues for screenshot-native retrieval and explains when visual preservation matters. It contains operational workflows, install commands, and pipeline stages. It is also directly relevant to the meta-skill's dual-ingestion design.

## Build plan

Build one narrow skill: Visual Web-Ingestion Advisor. Translate the repo's central idea into a reusable routing-decision skill rather than a mega-skill covering all of PixelRAG.

## Key workflow families extracted

- Text-first vs visual-first routing heuristics
- Screenshot rendering pipeline
- Chunk/embed/index/serve workflow
- Plugin-assisted page reading
- Visual artifact preservation strategy

## Maintenance note

If the repository changes its command surface, plugin flow, or central claims about when visual retrieval helps, review before updating the generated skill.
