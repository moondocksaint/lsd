"""Fetch and lightly clean a URL for downstream processing."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from lsd.models import FetchResult

HEADERS = {
    "User-Agent": "lsd/0.1.0 (Link-to-Skill Designer; +https://github.com/moondocksaint/lsd)"
}


def fetch(url: str, timeout: int = 30) -> FetchResult:
    """Fetch url and return a FetchResult.

    Raises httpx.HTTPError on network failures.
    """
    resp = httpx.get(url, headers=HEADERS, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()

    canonical_url = str(resp.url)
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    title = _extract_title(soup)
    text = _extract_text(soup)

    return FetchResult(
        url=url,
        canonical_url=canonical_url,
        title=title,
        text=text,
        html=html,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        http_status=resp.status_code,
        word_count=len(text.split()),
    )


def _extract_title(soup: BeautifulSoup) -> str:
    tag = soup.find("title")
    if tag:
        return tag.get_text(strip=True)
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return "Untitled"


def _extract_text(soup: BeautifulSoup) -> str:
    """Extract readable text, stripping nav/footer/script noise."""
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    # Prefer main content area if present
    main = soup.find("main") or soup.find(id="bodyContent") or soup.find("article")
    target = main if main else soup.find("body") or soup

    lines = []
    for element in target.descendants:  # type: ignore[union-attr]
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
