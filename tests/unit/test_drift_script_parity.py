"""Parity guard: the standalone scripts/check-drift.py must compute the same
normalized_hash as lsd.fetcher + lsd.normaliser.

The standalone script has no `lsd` dependency (it runs via `uv run` in CI), so
it re-implements extraction/normalisation. If lsd's logic changes and the script
isn't updated, drift detection silently breaks (every check reports drift). This
test loads the script by path and asserts hash parity on fixed HTML — no network.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import lsd
from bs4 import BeautifulSoup
from lsd.fetcher import _extract_text, _extract_title
from lsd.models import FetchResult
from lsd.normaliser import content_hash as lsd_content_hash
from lsd.normaliser import normalise as lsd_normalise

_SCRIPT_PATH = Path(lsd.__file__).parent / "scripts" / "check-drift.py"

_SAMPLES = [
    # Structured page with main/headings/paragraphs
    """<html><head><title>Rules Guide</title></head><body>
       <nav>skip me</nav>
       <main>
         <h2>First Rule</h2>
         <p>You should always validate the input before processing it downstream.</p>
         <h3>Detail</h3>
         <ul><li>Never trust user-supplied identifiers without checking them first.</li></ul>
       </main>
       <footer>skip me too</footer></body></html>""",
    # Wikipedia-style bodyContent id, no <main>
    """<html><head><title>Topic</title></head><body>
       <div id="bodyContent"><p>This paragraph is comfortably longer than ten characters.</p>
       <h4>Sub</h4><p>Another paragraph with sufficient length to be kept in extraction.</p></div>
       </body></html>""",
    # No title tag → falls back to h1
    """<html><body><article><h1>Fallback Title</h1>
       <p>Content paragraph that exceeds the ten character minimum length.</p></article></body></html>""",
]


def _load_script_module():
    spec = importlib.util.spec_from_file_location("check_drift_script", _SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def _lsd_hash(html: str, url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    title = _extract_title(soup)          # title first (extract_text mutates soup)
    text = _extract_text(soup)
    fetch = FetchResult(
        url=url, canonical_url=url, title=title, text=text, html=html,
        fetched_at="2026-07-02T00:00:00+00:00", http_status=200,
        word_count=len(text.split()),
    )
    return lsd_content_hash(lsd_normalise(fetch))


def _script_hash(module, html: str, url: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    title = module.extract_title(soup)
    text = module.extract_text(soup)
    return module.content_hash(module.normalise(title, url, text))


def test_script_exists():
    assert _SCRIPT_PATH.exists(), f"missing {_SCRIPT_PATH}"


def test_hash_parity_across_samples():
    module = _load_script_module()
    url = "https://example.com/page"
    for html in _SAMPLES:
        assert _script_hash(module, html, url) == _lsd_hash(html, url), (
            "standalone check-drift.py hash diverged from lsd.normaliser — "
            "update the script's extraction/normalisation to match."
        )


def test_script_reports_unchanged_on_matching_hash():
    """End-to-end within the script: matching stored hash ⇒ UNCHANGED."""
    module = _load_script_module()
    html = _SAMPLES[0]
    url = "https://example.com/page"
    stored = _lsd_hash(html, url)

    soup = BeautifulSoup(html, "html.parser")
    title = module.extract_title(soup)
    text = module.extract_text(soup)
    new_hash = module.content_hash(module.normalise(title, url, text))

    state, note = module.classify_drift(stored, new_hash, text, 200, url, url)
    assert state == "UNCHANGED", note
