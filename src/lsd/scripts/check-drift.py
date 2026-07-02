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


# ---------------------------------------------------------------------------
# The functions below MUST stay byte-for-byte faithful to lsd.fetcher
# (_extract_title, _extract_text) and lsd.normaliser (_clean, normalise,
# content_hash). The stored normalized_hash was produced by those functions at
# build time; this script recomputes it with no `lsd` install, so any drift in
# the extraction/normalisation logic here silently breaks drift detection.
# tests/unit/test_drift_script_parity.py guards the parity.
# ---------------------------------------------------------------------------

_RETRIEVED_PREFIX = "- Retrieved:"


def extract_title(soup: BeautifulSoup) -> str:
    """Mirror lsd.fetcher._extract_title."""
    tag = soup.find("title")
    if tag:
        return tag.get_text(strip=True)
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return "Untitled"


def extract_text(soup: BeautifulSoup) -> str:
    """Mirror lsd.fetcher._extract_text (mutates soup — extract title first)."""
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    main = soup.find("main") or soup.find(id="bodyContent") or soup.find("article")
    target = main if main else soup.find("body") or soup
    lines = []
    for element in target.descendants:
        if hasattr(element, "name"):
            if element.name in ("h1", "h2", "h3", "h4"):
                text = element.get_text(" ", strip=True)
                if text:
                    prefix = "#" * int(element.name[1])
                    lines.append(f"\n{prefix} {text}\n")
            elif element.name in ("p", "li", "td", "th", "dd", "dt"):
                text = element.get_text(" ", strip=True)
                if text and len(text) > 10:
                    lines.append(text)
    return "\n".join(lines)


def clean(text: str) -> str:
    """Mirror lsd.normaliser._clean."""
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    lines = [
        ln for ln in text.splitlines()
        if not re.fullmatch(r"[\W]+", ln.strip()) or not ln.strip()
    ]
    return "\n".join(lines).strip()


def normalise(title: str, canonical_url: str, text: str) -> str:
    """Mirror lsd.normaliser.normalise. word_count is len(text.split()) as in the fetcher.

    The Retrieved line is a placeholder here (it is excluded from the hash), so
    its exact value does not matter.
    """
    lines = [
        f"# Source — {title}",
        "",
        f"- Canonical URL: {canonical_url}",
        f"{_RETRIEVED_PREFIX} (recomputed by check-drift)",
        f"- Word count: {len(text.split())}",
        "",
        "## Content",
        "",
        clean(text),
    ]
    return "\n".join(lines)


def content_hash(normalised: str) -> str:
    """Mirror lsd.normaliser.content_hash (excludes the Retrieved line)."""
    hashable = "\n".join(
        ln for ln in normalised.splitlines()
        if not ln.startswith(_RETRIEVED_PREFIX)
    )
    return hashlib.sha256(hashable.encode()).hexdigest()[:16]


def fetch_page(url: str, user_agent: str) -> tuple[str, str, int, str]:
    """Fetch URL, return (title, extracted_text, http_status, final_url)."""
    try:
        resp = httpx.get(
            url,
            headers={"User-Agent": user_agent},
            timeout=30,
            follow_redirects=True,
        )
        final_url = str(resp.url)
        soup = BeautifulSoup(resp.text, "html.parser")
        title = extract_title(soup)          # before extract_text mutates the soup
        text = extract_text(soup)
        return title, text, resp.status_code, final_url
    except Exception as exc:
        return "", "", -1, str(exc)


def classify_drift(
    stored_hash: str,
    new_hash: str,
    new_text: str,
    http_status: int,
    original_url: str,
    final_url: str,
) -> tuple[str, str]:
    """Return (state, note). new_hash is precomputed from the normalised text."""
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

    if new_hash == stored_hash:
        return "UNCHANGED", "Hash identical"

    # Magnitude heuristic (this script has no stored source text to diff against,
    # so it uses word count as a proxy; `lsd check` does a sharper direct diff).
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
    # Use the same User-Agent lsd used at build time so servers return the same
    # HTML — otherwise UA-varying pages would hash differently and look drifted.
    _user_agent = (
        f"lsd/{_lsd_ver} (Link-to-Skill Designer; +https://github.com/moondocksaint/lsd)"
    )

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

        title, text, status, final_url = fetch_page(url, _user_agent)
        # Recompute the hash exactly as lsd.normaliser did at build time.
        new_hash = content_hash(normalise(title, url, text)) if status != -1 else ""
        state, note = classify_drift(stored_hash, new_hash, text, status, url, final_url)

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
