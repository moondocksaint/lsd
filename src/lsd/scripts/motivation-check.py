#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Surface the recorded motivation for this skill — no dependencies required.

Usage:
    uv run scripts/motivation-check.py
    python scripts/motivation-check.py
    uv run scripts/motivation-check.py --json

Reads motivation.json from the package directory and prints the recorded
intent, audience, key concepts, and build mode. This is the drift anchor:
when lsd check detects a substantial source change, compare the new source
content against these recorded expectations to decide whether to rebuild.

Exit codes:
    0  motivation.json found and readable
    1  motivation.json missing (skill was built without interview flow)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="LSD motivation checker")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--package-dir", default=".", help="Package directory (default: .)")
    args = parser.parse_args()

    pkg = Path(args.package_dir)
    motivation_path = pkg / "motivation.json"

    if not motivation_path.exists():
        if args.json:
            print(json.dumps({"error": "motivation.json not found", "path": str(pkg.resolve())}))
        else:
            print(f"\nNo motivation.json found in {pkg.resolve()}")
            print("This skill was built without the lsd-builder interview flow.")
            print("To record motivation, rebuild using the lsd-builder skill and")
            print("answer the three pre-build questions.")
        return 1

    try:
        data = json.loads(motivation_path.read_text())
    except Exception as exc:
        print(f"ERROR: Could not read motivation.json: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(data, indent=2))
        return 0

    # Human-readable output
    print(f"\nSkill motivation — {pkg.resolve().name}\n")

    intent = data.get("intent", "(not recorded)")
    audience = data.get("audience", "(not recorded)")
    concepts = data.get("key_concepts", [])
    build_mode = data.get("build_mode", "(not recorded)")
    skill_name = data.get("skill_name_confirmed", "(not recorded)")
    recorded_at = data.get("recorded_at", "")
    socratic_notes = data.get("socratic_notes")

    print(f"  Intent:      {intent}")
    print(f"  Audience:    {audience}")
    print(f"  Skill name:  {skill_name}")
    print(f"  Build mode:  {build_mode}")
    if concepts:
        print(f"  Key concepts: {', '.join(concepts)}")
    if recorded_at:
        print(f"  Recorded:    {recorded_at}")
    if socratic_notes:
        print(f"\n  Open questions from build session:")
        print(f"  {socratic_notes}")

    print()
    print("  Use this to evaluate substantial source changes:")
    print(f"  Does the updated source still support: \"{intent}\"?")

    return 0


if __name__ == "__main__":
    sys.exit(main())
