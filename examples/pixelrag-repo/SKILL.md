---
name: Visual Web-Ingestion Advisor
version: 0.1.0
summary: Advise whether a webpage or document should be ingested with text-first, hybrid, or visual-first mode and explain the trade-offs.
description: Use this skill when deciding how to ingest a webpage, repository page, document, or interface for extraction, review, or retrieval. It uses PixelRAG-informed routing heuristics but is not tied to any single implementation.
allowed-tools: Read, Write, Edit
---

## Purpose

Recommend the right ingestion mode for a source and explain the reasoning. Help users decide when text extraction is enough, when hybrid preservation is safer, and when visual-first is justified.

## When to use

Use when:
- evaluating a source for rules extraction or skill compilation,
- deciding whether PixelRAG-style screenshot reading is worth the cost,
- planning a hybrid ingestion pipeline,
- or explaining why a repo page, dashboard, PDF, or document may need visual preservation.

## Core principle

Do not flatten everything into text, and do not screenshot everything. Choose the ingestion path based on what the source actually communicates and how fragile it is to parsing.

## Workflow

1. Inspect the source type and apparent structure.
2. Determine whether important meaning is carried by prose, layout, tables, diagrams, screenshots, cards, badges, or UI structure.
3. Assess whether text extraction would preserve enough meaning for the intended use.
4. Choose one of three modes: text-first, hybrid, or visual-first.
5. Explain the trade-offs, risks, and preservation strategy.
6. If visual preservation is recommended, specify what artifacts should be saved.

## Routing heuristics

**Prefer text-first when**:
- the page is prose-heavy and headings/lists extract cleanly,
- tables are simple or nonessential,
- and the source normalises well into durable text.

**Prefer hybrid when**:
- the page includes important code blocks, tables, repo structure, cards, or visual grouping,
- text extraction is good but may miss emphasis or structure,
- or the source is important enough to justify a second preservation layer.

**Prefer visual-first when**:
- the page is dashboard-like, parser-hostile, canvas-heavy, or diagram-dominant,
- meaningful content is embedded in images or layout,
- or text extraction would clearly flatten away operational meaning.

## Output format

Provide:
- Recommended ingestion mode (one of: text-first, hybrid, visual-first)
- Why this mode fits
- What would likely be lost in text-only extraction
- What visual artifacts should be preserved, if any
- Whether reconciliation is needed
- Maintenance note for future source updates

## Style rule

Be practical and comparative. Choose the lightest ingestion path that preserves the source's meaning well enough for the intended use.

## Caveats

- Visual retrieval adds confidence and preservation, not just accuracy. On prose-heavy pages, text-first often remains primary even after a hybrid run.
- PixelRAG-based retrieval provides 18% accuracy gains on benchmarks but at higher operational cost. Use hybrid when the source structure justifies it.
- The routing heuristics are derived from one source and one research paper. Apply judgment.
