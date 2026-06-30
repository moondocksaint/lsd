# Skill Quality Rubric

Use this rubric to evaluate a generated skill package.

## 1. Source preservation (0-2)
- 0: No source artifact or policy
- 1: Source artifact present but policy is incomplete
- 2: Both source.md and source-policy.md are complete with fallback order and refresh workflow

## 2. Ingestion mode appropriateness (0-2)
- 0: Wrong ingestion mode for the source type
- 1: Correct mode but routing rationale is missing
- 2: Correct mode with clear routing rationale in extraction-report.md

## 3. Skill completeness (0-3)
- 0: SKILL.md is missing key sections
- 1: SKILL.md has all required sections but workflow or output format is vague
- 2: SKILL.md is complete; workflow is actionable and output format is specific
- 3: SKILL.md is complete, self-contained, well-caveated, and immediately usable

## 4. Opportunity mapping (0-2)
- 0: No opportunity map
- 1: Opportunity map present but ranking or rationale is thin
- 2: Ranked opportunities with confidence, timing, and needed-extras for each

## 5. Governance (0-2)
- 0: No governance policy
- 1: Governance policy present but change classification is missing
- 2: Full governance policy with change classification, promotion policy, and fallback order

## 6. Caveat faithfulness (0-2)
- 0: Source caveats are ignored
- 1: Some caveats are present
- 2: All material caveats from the source are preserved in the skill

## 7. Metadata validity (0-1)
- 0: metadata.json is missing or invalid
- 1: metadata.json validates against schema/metadata.schema.json

## Maximum score: 14

## Thresholds
- 12-14: Production-ready package
- 9-11: Usable but needs review
- 6-8: Needs significant rework
- Below 6: Do not promote
