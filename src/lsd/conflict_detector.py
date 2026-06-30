"""Heuristic cross-source conflict detector for LSD v0.3.

Swap-candidate criteria (architectural principle):
  - Replace with embedding-based similarity when a hosted embeddings API
    is available and quality regression on the test suite is < 10 %.
  - Replace with LLM-based conflict detection when token costs fall enough
    that calling the LLM per source-pair is cheaper than maintaining these
    heuristics, or when heuristic false-positive rate exceeds 20 % on a
    curated eval set.
  - The interface (detect_conflicts(sources) -> ConflictReport) is the
    stable contract; swap the implementation behind it.
"""

from __future__ import annotations

import re

from lsd.models import Conflict, ConflictReport, SourceEntry


def detect_conflicts(sources: list[SourceEntry]) -> ConflictReport:
    """Analyse a list of SourceEntry objects for cross-source conflicts.

    Returns a ConflictReport with contradictions, gaps, and overlaps.

    Heuristics (v0.3, rule-based):
      1. Contradiction detection — negation patterns around shared key terms.
      2. Gap detection — headings in one source absent from another.
      3. Overlap detection — near-duplicate sentences across sources.
    """
    if len(sources) < 2:
        return ConflictReport(
            conflicts=[],
            summary="Single source — no conflicts to detect.",
            has_blocking_conflicts=False,
        )

    conflicts: list[Conflict] = []

    # 1. Extract headings from each source
    source_headings: list[set[str]] = []
    for s in sources:
        headings = set(re.findall(r"^#{1,4}\s+(.+)$", s.normalised, re.MULTILINE))
        source_headings.append({h.strip().lower() for h in headings})

    # 2. Gap detection: headings in one source missing from the other
    for i, headings_i in enumerate(source_headings):
        for j, headings_j in enumerate(source_headings):
            if i >= j:
                continue
            gaps = headings_i - headings_j
            if len(gaps) >= 3:
                conflicts.append(Conflict(
                    kind="gap",
                    description=(
                        f"Source {i + 1} covers {len(gaps)} topic(s) not found in "
                        f"source {j + 1}: "
                        + ", ".join(sorted(gaps)[:5])
                        + (" (and more)" if len(gaps) > 5 else "")
                    ),
                    source_indices=[i + 1, j + 1],
                    severity="medium",
                    suggestion=(
                        f"Review whether source {j + 1} intentionally omits these "
                        "topics or is simply less comprehensive."
                    ),
                ))

    # 3. Contradiction detection: negation near shared key terms
    def extract_key_terms(text: str) -> set[str]:
        backtick = set(re.findall(r"`([^`]+)`", text))
        bold = set(re.findall(r"\*\*([^*]+)\*\*", text))
        cap_phrases = set(re.findall(r"(?<=[a-z] )([A-Z][a-z]+ [A-Z][a-z]+)", text))
        return backtick | bold | cap_phrases

    _NEG_PATTERN = re.compile(
        r"(?:not|no|never|cannot|does not|don't|doesn't|isn't|aren't)",
        re.IGNORECASE,
    )

    def has_negation_near(text: str, term: str) -> bool:
        escaped = re.escape(term)
        pat = re.compile(
            rf"(?:{_NEG_PATTERN.pattern}).{{0,50}}{escaped}"
            rf"|{escaped}.{{0,50}}(?:{_NEG_PATTERN.pattern})",
            re.IGNORECASE,
        )
        return bool(pat.search(text))

    for i in range(len(sources)):
        for j in range(i + 1, len(sources)):
            shared = extract_key_terms(sources[i].normalised) & extract_key_terms(sources[j].normalised)
            contradicted = [
                t for t in shared
                if has_negation_near(sources[i].normalised, t)
                != has_negation_near(sources[j].normalised, t)
            ]
            if contradicted:
                conflicts.append(Conflict(
                    kind="contradiction",
                    description=(
                        f"Sources {i + 1} and {j + 1} appear to contradict each "
                        "other on: "
                        + ", ".join(sorted(contradicted)[:5])
                    ),
                    source_indices=[i + 1, j + 1],
                    severity="high",
                    suggestion=(
                        "Read both source sections carefully and decide which claim "
                        "is authoritative, or note the discrepancy explicitly in the "
                        "skill definition."
                    ),
                ))

    # 4. Overlap detection: near-duplicate sentences
    def extract_sentences(text: str) -> set[str]:
        return {
            s.strip().lower()
            for s in re.split(r"[.!?]\s+", text)
            if len(s.strip()) > 40
        }

    for i in range(len(sources)):
        for j in range(i + 1, len(sources)):
            overlap = extract_sentences(sources[i].normalised) & extract_sentences(sources[j].normalised)
            if len(overlap) >= 5:
                conflicts.append(Conflict(
                    kind="overlap",
                    description=(
                        f"Sources {i + 1} and {j + 1} share {len(overlap)} "
                        "near-identical sentences — they may be redundant."
                    ),
                    source_indices=[i + 1, j + 1],
                    severity="low",
                    suggestion=(
                        "Consider using only one of these sources or explicitly "
                        "noting they cover the same ground."
                    ),
                ))

    # Build summary
    n_high = sum(1 for c in conflicts if c.severity == "high")
    n_medium = sum(1 for c in conflicts if c.severity == "medium")
    n_low = sum(1 for c in conflicts if c.severity == "low")

    if not conflicts:
        summary = f"No significant conflicts detected across {len(sources)} sources."
    else:
        parts: list[str] = []
        if n_high:
            parts.append(f"{n_high} contradiction(s)")
        if n_medium:
            parts.append(f"{n_medium} gap(s)")
        if n_low:
            parts.append(f"{n_low} overlap(s)")
        summary = "Detected: " + ", ".join(parts) + f" across {len(sources)} sources."

    return ConflictReport(
        conflicts=conflicts,
        summary=summary,
        has_blocking_conflicts=n_high > 0,
    )
