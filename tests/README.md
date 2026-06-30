# Test Harness

This directory contains the regression test inputs and expected outputs for the LSD builder.

## Structure

```
tests/
├── README.md
├── cases/
│   ├── wikipedia-ai-writing/
│   │   ├── input.json           # URL + build parameters
│   │   └── expected/            # Expected output package for regression
│   └── pixelrag-repo/
│       ├── input.json
│       └── expected/
└── rubric.md                    # Skill quality evaluation rubric
```

## Running tests

Tests are manual at v0.1. They compare a new builder run against the expected package files in `cases/<name>/expected/`. Automated diffing will be added in v0.4.

## Adding a new test case

1. Create a new directory in `cases/`.
2. Write `input.json` with the URL and build parameters.
3. Run the builder and save the output as `expected/`.
4. Commit both input and expected output.
