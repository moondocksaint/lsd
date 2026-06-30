# Expected output — wikipedia-ai-writing

This directory contains the reference expected output for the
`wikipedia-ai-writing` eval case.

## Status

Stub — populated on first green run. The eval harness (`lsd eval`) will
diff actual output against these files once they are committed.

## How to populate

Run the pipeline once with a known-good configuration, review the output
manually against the rubric in `tests/rubric.md`, and copy passing files
here:

```bash
lsd build https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing \
    --output tests/cases/wikipedia-ai-writing/expected/
```

Then commit the expected/ directory. Future runs of `lsd eval` will diff
against this snapshot.

## Minimum rubric threshold

A package must score ≥ 12/14 against `tests/rubric.md` before its output
is accepted as the reference expected output.

## Files expected

- SKILL.md
- source.md
- metadata.json
- source-policy.md
- skill-opportunities.md
- extraction-report.md
- CHANGELOG.md
