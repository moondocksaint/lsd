---
name: AI Writing Tells Reviewer
version: 0.1.0
summary: Review or audit prose for AI-style writing patterns using heuristics derived from Wikipedia's Signs of AI writing page.
description: Use this skill when editing, reviewing, or auditing prose for stylistic tells that are associated with AI-generated writing. It applies a structured checklist of patterns derived from Wikipedia's Signs of AI writing page and produces flagged output with suggested rewrites.
allowed-tools: Read, Write, Edit
---

## Purpose

Detect and suggest corrections for AI-style writing patterns in prose. Produce structured output that names the pattern, rates severity, and offers a targeted rewrite.

## When to use

Use when:
- reviewing a draft for AI-style signals before publication,
- auditing an existing text for compliance with a house style that excludes AI-patterned writing,
- coaching a writer on specific patterns to avoid,
- or quality-checking AI-generated output before human review.

## Core principle

These are heuristic signals, not proof of AI authorship. Apply them as a structured editing lens, not as a detector or classifier. A text that shows one or two of these patterns may still be human-written. The goal is better prose, not labelling.

## Workflow

1. Read the draft in full before flagging anything.
2. Scan for promotional or inflated significance language ("landmark", "groundbreaking", "transformative", "crucially important").
3. Scan for vague attributions ("experts say", "studies show", "it is widely believed") without specific sourcing.
4. Identify formulaic transitions ("Furthermore", "Moreover", "In conclusion", "It is worth noting that").
5. Identify unsupported significance claims appended to otherwise factual sentences.
6. Check for AI vocabulary clusters: "delve", "underscore", "commendable", "notable", "it is important to note", "stands as".
7. Flag "not just X, but Y" constructions used for rhetorical emphasis without factual content.
8. Identify rigid outline-like endings: "challenges and future prospects", "implications for the field".
9. Check for undue coherence: prose that reads as a seamless summary of a Wikipedia article without any rough edges, personal voice, or distinctive framing.
10. For each flagged instance, produce a structured output entry.

## Output format

For each flagged item:
- **Pattern name**: (e.g., promotional inflation, AI vocabulary, vague attribution)
- **Quoted text**: the exact phrase or sentence
- **Severity**: low / medium / high
- **Why it may be a tell**: brief rationale
- **Suggested rewrite**: a more specific, direct, or evidence-grounded alternative

End with a short summary: total flags, dominant pattern, and one-line editorial recommendation.

## Style rule

Be a sharp editor, not a detector. Offer rewrites that make the text more specific, direct, and individual — not just "less AI-like" in the abstract.

## Caveats

- Not every flagged phrase implies AI authorship. Apply judgment.
- The heuristics are drawn from a descriptive page, not a prescriptive standard. They reflect observed patterns, not formal rules.
- Some legitimate writing contexts call for formal transitions or significance framing. Context overrides pattern.
- Do not use this skill as a definitive AI-content classifier or to make authorship claims.
