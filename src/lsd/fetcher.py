"""Fetch and lightly clean a URL for downstream processing.

Audit fix (v0.5): User-Agent now reads lsd.__version__ instead of
hardcoding "0.1.0".
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from lsd import __version__
from lsd.exceptions import LSDError
from lsd.models import FetchResult, SourceType

_UA_LSD = f"lsd/{__version__} (Link-to-Skill Designer; +https://github.com/moondocksaint/lsd)"
_UA_BROWSER = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}
_VIDEO_HOSTS = {"youtube.com", "www.youtube.com", "youtu.be", "vimeo.com", "www.vimeo.com"}
_LOGIN_SIGNALS = {"login", "signin", "sign-in", "auth", "account/login", "session/new"}


def fetch(url: str, timeout: int = 30) -> FetchResult:
    """Fetch url and return a FetchResult."""
    _check_video_url(url)
    headers = _pick_headers(url)
    resp = httpx.get(url, headers=headers, timeout=timeout, follow_redirects=True)
    canonical_url = str(resp.url)
    _check_gated(url, canonical_url, resp.status_code)
    resp.raise_for_status()
    content_type = resp.headers.get("content-type", "").lower()
    source_type = _detect_source_type(url, canonical_url, content_type)

    if source_type == "pdf":
        return FetchResult(
            url=url, canonical_url=canonical_url,
            title=_title_from_url(url),
            text="PDF source — use visual backend for full content extraction.",
            html="", fetched_at=datetime.now(timezone.utc).isoformat(),
            http_status=resp.status_code, word_count=0, source_type="pdf",
        )
    if source_type == "image":
        return FetchResult(
            url=url, canonical_url=canonical_url,
            title=_title_from_url(url),
            text="Image source — visual ingestion required.",
            html="", fetched_at=datetime.now(timezone.utc).isoformat(),
            http_status=resp.status_code, word_count=0, source_type="image",
        )
    if source_type == "unsupported":
        raise LSDError(
            "Video sources are not supported. Use a transcript or article URL instead."
        )

    html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    title = _extract_title(soup)
    text = _extract_text(soup)

    return FetchResult(
        url=url, canonical_url=canonical_url, title=title, text=text, html=html,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        http_status=resp.status_code, word_count=len(text.split()),
        source_type=source_type,
    )


def _detect_source_type(url: str, canonical_url: str, content_type: str) -> SourceType:
    from urllib.parse import urlparse
    parsed = urlparse(url.lower())
    host = parsed.hostname or ""
    path = parsed.path
    if content_type.startswith("video/"): return "unsupported"
    if content_type.startswith("application/pdf") or path.endswith(".pdf"): return "pdf"
    if content_type.startswith("image/"): return "image"
    ext = "." + path.rsplit(".", 1)[-1] if "." in path else ""
    if ext in _IMAGE_EXTS: return "image"
    if host in ("docs.google.com", "slides.google.com", "sheets.google.com"): return "google_doc"
    if "linkedin.com" in host: return "social"
    return "html"


def _check_video_url(url: str) -> None:
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    if host in _VIDEO_HOSTS:
        raise LSDError("Video sources are not supported. Use a transcript or article URL instead.")


def _check_gated(original_url: str, canonical_url: str, status_code: int) -> None:
    if status_code in (401, 403):
        raise LSDError(
            f"Source returned HTTP {status_code}. "
            "The page requires authentication. "
            "Export the page manually and pass the file path instead."
        )
    from urllib.parse import urlparse
    final_path = urlparse(canonical_url).path.lower()
    final_host = urlparse(canonical_url).hostname or ""
    orig_host = urlparse(original_url).hostname or ""
    if final_host != orig_host: return
    if any(signal in final_path for signal in _LOGIN_SIGNALS):
        raise LSDError(
            "Source redirected to a login page. "
            "The content requires authentication. "
            "Export the page manually and pass the file path instead."
        )


def _pick_headers(url: str) -> dict[str, str]:
    from urllib.parse import urlparse
    host = (urlparse(url).hostname or "").lower()
    if "linkedin.com" in host:
        return {"User-Agent": _UA_BROWSER}
    return {"User-Agent": _UA_LSD}


def _title_from_url(url: str) -> str:
    from urllib.parse import urlparse
    path = urlparse(url).path
    name = path.rsplit("/", 1)[-1] if "/" in path else path
    return name or url


def _extract_title(soup: BeautifulSoup) -> str:
    tag = soup.find("title")
    if tag: return tag.get_text(strip=True)
    h1 = soup.find("h1")
    if h1: return h1.get_text(strip=True)
    return "Untitled"


def _extract_text(soup: BeautifulSoup) -> str:
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
