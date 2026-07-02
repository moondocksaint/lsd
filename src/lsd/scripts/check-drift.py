#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27", "beautifulsoup4>=4.12", "markdownify>=0.13"]
# ///
"""LSD drift checker — runs standalone, no lsd install required.

Usage:
    uv run scripts/check-drift.py              # run from inside the package dir
    python scripts/check-drift.py              # if deps already installed
    uv run scripts/check-drift.py --json       # machine-readable output

Reads metadata.json from the parent directory (the skill package), re-fetches
each source URL, computes the normalized hash, and reports drift state.

Drift states:
    UNCHANGED   Hash identical — no action needed.
    MINOR       Content changed, structure likely intact — consider rebuild.
    SUBSTANTIAL Major change detected — review before rebuilding.
    GONE        URL unreachable (4xx/5xx/timeout) — do not overwrite package.
    REDIRECTED  URL permanently moved — update canonical URL before rebuilding.

Exit codes:
    0  All sources UNCHANGED
    1  One or more sources changed (MINOR, SUBSTANTIAL, REDIRECTED)
    2  One or more sources GONE or ERROR
    3  metadata.json missing or unreadable
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

try:
    import httpx
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: Missing dependencies. Run with: uv run scripts/check-drift.py")
    sys.exit(3)


def normalise(text: str, title: str = "", url: str = "") -> str:
    """Light normalisation matching lsd.normaliser.normalise() output."""
    # Strip volatile header lines (they contain fetched_at timestamp)
    lines = text.splitlines()
    cleaned = [ln for ln in lines if not ln.startswith("- Retrieved:")]
    return "\n".join(cleaned).strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def fetch_text(url: str, user_agent: str = "lsd-drift-checker/unknown") -> tuple[str, int, str]:
    """Fetch URL, return (body_text, http_status, final_url)."""
    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": user_agent},
            timeout=30,
            follow_redirects=True,
        )
        final_url = str(resp.url)
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
            tag.decompose()
        body = soup.get_text(" ", strip=True)
        return body, resp.status_code, final_url
    except Exception as exc:
        return "", -1, str(exc)


def classify_drift(
    stored_hash: str,
    new_text: str,
    http_status: int,
    original_url: str,
    final_url: str,
) -> tuple[str, str]:
    """Return (state, note)."""
    if http_status == -1:
        return "GONE", f"Fetch error: {final_url[:80]}"
    if http_status in (404, 410):
        return "GONE", f"HTTP {http_status}"
    if http_status in (401, 403):
        return "GONE", f"HTTP {http_status} — access denied"
    if http_status >= 400:
        return "GONE", f"HTTP {http_status}"

    # Detect redirect
    if final_url and final_url != original_url:
        from urllib.parse import urlparse
        orig_host = urlparse(original_url).hostname or ""
        final_host = urlparse(final_url).hostname or ""
        if orig_host != final_host or abs(len(final_url) - len(original_url)) > 20:
            return "REDIRECTED", f"→ {final_url[:80]}"

    new_hash = content_hash(new_text)
    if new_hash == stored_hash:
        return "UNCHANGED", "Hash identical"

    # Magnitude heuristic
    words = len(new_text.split())
    headings = re.findall(r"^#{1,3}\s+.+$", new_text, re.MULTILINE)
    if words < 200:
        return "SUBSTANTIAL", f"Very short result ({words} words) — possible gate or truncation"
    if words < 500:
        return "MINOR", f"Content changed ({words} words)"
    return "MINOR", f"Content changed ({words} words, {len(headings)} headings)"


def main() -> int:
    parser = argparse.ArgumentParser(description="LSD drift checker")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--package-dir", default=".", help="Package directory (default: .)")
    args = parser.parse_args()

    pkg = Path(args.package_dir)
    meta_path = pkg / "metadata.json"
    if not meta_path.exists():
        print(f"ERROR: No metadata.json found in {pkg.resolve()}", file=sys.stderr)
        return 3

    try:
        meta = json.loads(meta_path.read_text())
    except Exception as exc:
        print(f"ERROR: Could not read metadata.json: {exc}", file=sys.stderr)
        return 3

    _lsd_ver = meta.get("package", {}).get("lsd_version", "unknown")
    _user_agent = f"lsd-drift-checker/{_lsd_ver}"

    # Collect source dependencies — single or multi
    deps: list[dict] = []
    if "source_dependency" in meta:
        deps = [meta["source_dependency"]]
    elif "source_dependencies" in meta:
        deps = meta["source_dependencies"]
    else:
        print("ERROR: No source_dependency in metadata.json", file=sys.stderr)
        return 3

    # Also load motivation if present
    motivation_path = pkg / "motivation.json"
    motivation = None
    if motivation_path.exists():
        try:
            motivation = json.loads(motivation_path.read_text())
        except Exception:
            pass

    results = []
    exit_code = 0

    for dep in deps:
        url = dep.get("canonical_url") or dep.get("url", "")
        stored_hash = dep.get("normalized_hash", "")
        idx = dep.get("index", "")
        label = f"Source {idx}" if idx else url[:60]

        body, status, final_url = fetch_text(url, _user_agent)
        state, note = classify_drift(stored_hash, body, status, url, final_url)

        result = {
            "label": label,
            "url": url,
            "state": state,
            "note": note,
            "stored_hash": stored_hash,
        }
        results.append(result)

        if state in ("GONE", "ERROR"):
            exit_code = max(exit_code, 2)
        elif state != "UNCHANGED":
            exit_code = max(exit_code, 1)

    if args.json:
        output = {
            "results": results,
            "motivation_intent": motivation.get("intent") if motivation else None,
            "exit_code": exit_code,
        }
        print(json.dumps(output, indent=2))
        return exit_code

    # Human-readable output
    print(f"\nLSD drift check — {pkg.resolve().name}\n")
    width = max(len(r["label"]) for r in results) + 2
    for r in results:
        state_fmt = {
            "UNCHANGED": "✓ UNCHANGED ",
            "MINOR": "~ MINOR     ",
            "SUBSTANTIAL": "! SUBSTANTIAL",
            "GONE": "✗ GONE      ",
            "REDIRECTED": "→ REDIRECTED",
        }.get(r["state"], r["state"])
        print(f"  {r['label']:<{width}} {state_fmt}   {r['note']}")

    print()

    # Surface motivation on substantial change
    if any(r["state"] == "SUBSTANTIAL" for r in results) and motivation:
        intent = motivation.get("intent", "")
        if intent:
            print(f"  When you created this skill, you said:\n  \"{intent}\"")
            print("  Does the changed source still serve that purpose?\n")

    verdicts = {r["state"] for r in results}
    if verdicts == {"UNCHANGED"}:
        print("  All sources unchanged. No action needed.")
    elif "SUBSTANTIAL" in verdicts:
        print("  Action: Review source changes before rebuilding.")
        print("  Do not auto-overwrite — use a new output directory.")
    elif "GONE" in verdicts:
        print("  Action: Source URL unreachable. Package preserved.")
        print("  Check source-policy.md for fallback chain.")
    elif "REDIRECTED" in verdicts:
        print("  Action: Update canonical URL in metadata.json, then rebuild.")
    else:
        print("  Action: Minor changes detected. Consider rebuilding.")
        print("  Run: lsd build <url> --output <package-dir>")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
