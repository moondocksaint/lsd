# CI templates

Copy-paste workflows for repositories that hold an **LSD skill package** (the
output of `lsd build` — a directory with `metadata.json` and
`scripts/check-drift.py`). These do not belong in the LSD tool repo itself.

## `drift-check.yml` — scheduled source-drift monitoring

Watches every source recorded in your package's `metadata.json` and tells you
when a source page changes or disappears, so a skill built from it doesn't
silently go stale.

**Install:**

1. Copy `drift-check.yml` into your skill-package repo at
   `.github/workflows/drift-check.yml`.
2. If the package isn't at the repo root, run the workflow via
   *Actions → Source drift check → Run workflow* and set **package_dir**, or
   edit the `schedule`/`env` defaults.
3. Ensure the package still contains `scripts/check-drift.py` (LSD writes it on
   every build).

**Behaviour:** on a weekly schedule (and on demand) it runs the bundled
`scripts/check-drift.py` through [`uv`](https://docs.astral.sh/uv/) — no `lsd`
install required, since the script declares its own dependencies inline. If any
source changed (MINOR/SUBSTANTIAL/REDIRECTED) or is unreachable (GONE) it opens
(or updates) a single issue labelled `source-drift` with the JSON report, and
fails the run.

**Alternative:** if you prefer the full CLI, replace the "Run drift check" step
with `pip install lsd` and `lsd check "$PACKAGE_DIR"`.
