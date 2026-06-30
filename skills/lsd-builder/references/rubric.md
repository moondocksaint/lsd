# LSD Eval Rubric

Used by `lsd eval` to score a built package against 7 criteria, each worth 0–2
points (max 14/14). The target quality gate is **≥ 12/14**.

A score of 14/14 means production-ready. A score < 12/14 triggers a warning
and suggests either a rebuild with a stronger model or manual review.

---

## Criteria

### 1. SKILL.md completeness (0–2)

| Score | Meaning |
|---|---|
| 2 | All required sections present: frontmatter, Core principle, Workflow, Output format |
| 1 | Most sections present but one is missing or stub-level |
| 0 | SKILL.md is a skeleton with no LLM-generated content |

### 2. Core principle accuracy (0–2)

| Score | Meaning |
|---|---|
| 2 | Core principle accurately captures the main thesis of the source |
| 1 | Partially accurate — captures some key ideas but misses the central claim |
| 0 | Inaccurate or generic (could apply to any source) |

### 3. Workflow specificity (0–2)

| Score | Meaning |
|---|---|
| 2 | Workflow is specific to the source — contains steps that would not appear for an arbitrary topic |
| 1 | Workflow is partially generic but references some source-specific content |
| 0 | Workflow is generic boilerplate |

### 4. Source dependency tracking (0–2)

| Score | Meaning |
|---|---|
| 2 | `metadata.json` has `source_dependency` with `url`, `normalized_hash`, `last_checked_at`, `update_policy` |
| 1 | Some fields present but `normalized_hash` or `update_policy` missing |
| 0 | No source dependency block |

### 5. compiler_model provenance (0–2)

| Score | Meaning |
|---|---|
| 2 | `compiler_model` present in all three locations: SKILL.md frontmatter, metadata.json, README.md |
| 1 | Present in one or two locations only |
| 0 | Absent |

### 6. Output package completeness (0–2)

| Score | Meaning |
|---|---|
| 2 | All expected files present: SKILL.md, README.md, source.md, metadata.json, source-policy.md, skill-opportunities.md, extraction-report.md, CHANGELOG.md |
| 1 | One file missing |
| 0 | Two or more files missing |

### 7. Diff stability (0–2)

Measured by `lsd eval` against the `expected/` snapshot.

| Score | Meaning |
|---|---|
| 2 | Zero unexpected diffs after timestamp + hash normalization (SKILL.md is the only DIFFER) |
| 1 | One unexpected file differs |
| 0 | Two or more unexpected files differ |

---

## Quality gate

| Score range | Verdict |
|---|---|
| 14/14 | Production-ready |
| 12–13/14 | Acceptable — minor issues, no rebuild required |
| 10–11/14 | Marginal — review before shipping; consider stronger model |
| < 10/14 | Failing — rebuild required |

---

## Running the eval

```bash
lsd eval tests/cases/<case-name>/
```

The command:
1. Re-runs `lsd build` using the URL in `tests/cases/<case-name>/input.json`
2. Scores the output against the 7 criteria above
3. Diffs against `tests/cases/<case-name>/expected/` after normalization
4. Prints the rubric table, total score, and diff summary

### input.json format

```json
{
  "urls": ["https://..."],
  "retrieval_backend": "naive",
  "token_threshold": 50000
}
```

---

## Adding an eval baseline

1. Run `lsd build <url> --output tests/cases/<case-name>/`
2. Manually review output against this rubric (target ≥ 12/14)
3. Run `lsd eval tests/cases/<case-name>/` to confirm automated score
4. If ≥ 12/14: commit `tests/cases/<case-name>/expected/` (exclude `source.md`)
5. Document in `PROVENANCE.md` under a new dated entry
