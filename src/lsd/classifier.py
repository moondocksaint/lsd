"""Classify a FetchResult into a SourceFit.

This is a heuristic rule-based classifier. It uses simple signals
from the fetched content to score the source across six dimensions.

Future: replace or supplement with an LLM call for higher accuracy.
"""

from __future__ import annotations

import re

from lsd.models import FetchResult, SourceFit

# --- Signal word lists ---

RULE_SIGNALS = [
    r"\bshould\b", r"\bmust\b", r"\bavoid\b", r"\bnever\b",
    r"\balways\b", r"\bdo not\b", r"\brule\b", r"\bheuristic\b",
    r"\bguideline\b", r"\bsign of\b", r"\bindicator\b",
]

PROCEDURE_SIGNALS = [
    r"\bstep \d\b", r"\bfirst[,:]\b", r"\bthen[,:]\b",
    r"\binstall\b", r"\brun\b", r"\bconfigure\b", r"\bdeploy\b",
    r"\bpipeline\b", r"\bworkflow\b", r"\b```",
]

EXAMPLE_SIGNALS = [
    r"\bfor example\b", r"\be\.g\.\b", r"\bsuch as\b",
    r"\binstance\b", r"\bsample\b", r"\bdemonstrat",
]

STABILITY_LOW = [
    r"github\.com", r"changelog", r"release", r"version \d",
    r"latest", r"breaking change",
]

VISUAL_SIGNALS = [
    r"dashboard", r"screenshot", r"diagram", r"infographic",
    r"chart", r"canvas", r"render", r"pixel", r"tile",
    r"visual", r"ui component", r"layout",
]


def classify(fetch: FetchResult) -> SourceFit:
    text = fetch.text.lower()

    rule_score = _score(text, RULE_SIGNALS)
    proc_score = _score(text, PROCEDURE_SIGNALS)
    example_score = _score(text, EXAMPLE_SIGNALS)
    stability_risk = _score(text, STABILITY_LOW)
    visual_score = _score(text, VISUAL_SIGNALS)

    word_count = max(fetch.word_count, 1)

    rule_density = _bucket(rule_score / word_count * 1000)
    procedure_density = _bucket(proc_score / word_count * 1000)
    example_density = _bucket(example_score / word_count * 1000)
    stability = "low" if stability_risk > 5 else "medium" if stability_risk > 2 else "high"
    specificity = "high" if word_count > 1000 and rule_score + proc_score > 10 else "medium"
    composability = "high" if proc_score > 8 or visual_score > 5 else "medium"

    # Overall fit: high if at least two dimensions are high
    highs = sum([
        rule_density == "high",
        procedure_density == "high",
        example_density == "high",
    ])
    overall_fit = "high" if highs >= 2 else "medium" if highs >= 1 else "low"

    fit_notes = _build_notes(rule_density, procedure_density, example_density, visual_score)

    return SourceFit(
        overall_fit=overall_fit,
        rule_density=rule_density,
        procedure_density=procedure_density,
        example_density=example_density,
        stability=stability,
        specificity=specificity,
        composability=composability,
        fit_notes=fit_notes,
    )


def _score(text: str, patterns: list[str]) -> int:
    return sum(len(re.findall(p, text)) for p in patterns)


def _bucket(rate: float) -> str:
    if rate > 3:
        return "high"
    if rate > 1:
        return "medium"
    return "low"


def _build_notes(
    rule_density: str,
    procedure_density: str,
    example_density: str,
    visual_score: int,
) -> str:
    parts = []
    if rule_density == "high":
        parts.append("High rule density — good candidate for reviewer or rewriter skill.")
    if procedure_density == "high":
        parts.append("High procedure density — good candidate for workflow or integration skill.")
    if example_density == "high":
        parts.append("High example density — examples can anchor skill output format.")
    if visual_score > 5:
        parts.append("Visual signals detected — consider hybrid or visual-first ingestion.")
    return " ".join(parts) or "No strong signals; review manually."
