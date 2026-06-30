"""Tests for lsd.fetcher — uses pytest-httpx to mock all network calls."""

from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from lsd.exceptions import LSDError
from lsd.fetcher import fetch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HTML_MINIMAL = """
<html>
  <head><title>Test Page</title></head>
  <body>
    <main>
      <p>This is a meaningful paragraph about rules and heuristics that you should follow.</p>
      <p>Another paragraph with more than ten characters for extraction.</p>
    </main>
  </body>
</html>
"""

HTML_LOGIN = """
<html>
  <head><title>Login</title></head>
  <body><p>Please sign in to continue.</p></body>
</html>
"""

PDF_BYTES = b"%PDF-1.4 fake pdf content"


# ---------------------------------------------------------------------------
# HTML source type
# ---------------------------------------------------------------------------

def test_html_fetch_returns_correct_source_type(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://example.com/page",
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
        text=HTML_MINIMAL,
    )
    result = fetch("https://example.com/page")
    assert result.source_type == "html"
    assert result.title == "Test Page"
    assert result.http_status == 200
    assert result.word_count > 0
    assert "https://example.com" in result.canonical_url


def test_html_fetch_extracts_text(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://example.com/page",
        status_code=200,
        headers={"content-type": "text/html"},
        text=HTML_MINIMAL,
    )
    result = fetch("https://example.com/page")
    assert len(result.text) > 0
    assert "paragraph" in result.text.lower()


# ---------------------------------------------------------------------------
# PDF source type
# ---------------------------------------------------------------------------

def test_pdf_by_content_type(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://example.com/doc.pdf",
        status_code=200,
        headers={"content-type": "application/pdf"},
        content=PDF_BYTES,
    )
    result = fetch("https://example.com/doc.pdf")
    assert result.source_type == "pdf"
    assert result.word_count == 0
    assert "PDF source" in result.text


def test_pdf_by_url_extension(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://example.com/report.pdf",
        status_code=200,
        headers={"content-type": "application/octet-stream"},
        content=PDF_BYTES,
    )
    result = fetch("https://example.com/report.pdf")
    assert result.source_type == "pdf"


# ---------------------------------------------------------------------------
# Image source type
# ---------------------------------------------------------------------------

def test_image_by_content_type(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://example.com/photo.jpg",
        status_code=200,
        headers={"content-type": "image/jpeg"},
        content=b"\xff\xd8\xff fake jpeg",
    )
    result = fetch("https://example.com/photo.jpg")
    assert result.source_type == "image"
    assert "visual ingestion" in result.text.lower()


def test_image_by_url_extension(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://example.com/diagram.png",
        status_code=200,
        headers={"content-type": "application/octet-stream"},
        content=b"\x89PNG fake png",
    )
    result = fetch("https://example.com/diagram.png")
    assert result.source_type == "image"


# ---------------------------------------------------------------------------
# Social (LinkedIn) — browser UA used, fetch succeeds
# ---------------------------------------------------------------------------

def test_linkedin_returns_social_source_type(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://www.linkedin.com/in/someprofile/",
        status_code=200,
        headers={"content-type": "text/html"},
        text=HTML_MINIMAL,
    )
    result = fetch("https://www.linkedin.com/in/someprofile/")
    assert result.source_type == "social"


# ---------------------------------------------------------------------------
# Gated pages — LSDError raised
# ---------------------------------------------------------------------------

def test_gated_page_403_raises_lsd_error(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://example.com/private",
        status_code=403,
    )
    with pytest.raises(LSDError, match="authentication"):
        fetch("https://example.com/private")


def test_gated_page_401_raises_lsd_error(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://example.com/secret",
        status_code=401,
    )
    with pytest.raises(LSDError, match="authentication"):
        fetch("https://example.com/secret")


def test_login_redirect_raises_lsd_error(httpx_mock: HTTPXMock):
    # Simulate a redirect to a login page on the same host
    httpx_mock.add_response(
        url="https://example.com/protected",
        status_code=200,
        headers={"content-type": "text/html"},
        text=HTML_LOGIN,
    )
    # We simulate the redirect outcome by patching the canonical URL:
    # pytest-httpx doesn't support redirect chains natively, so we test
    # the login-path detection logic directly via a URL that already
    # contains the login signal.
    with pytest.raises(LSDError, match="login|authentication"):
        fetch("https://example.com/login?next=/protected")


# ---------------------------------------------------------------------------
# Unsupported (video) — LSDError raised
# ---------------------------------------------------------------------------

def test_youtube_url_raises_lsd_error():
    # No mock needed — video check happens before any HTTP call
    with pytest.raises(LSDError, match="[Vv]ideo"):
        fetch("https://www.youtube.com/watch?v=dQw4w9WgXcQ")


def test_vimeo_url_raises_lsd_error():
    with pytest.raises(LSDError, match="[Vv]ideo"):
        fetch("https://vimeo.com/123456789")


# ---------------------------------------------------------------------------
# Google Docs — parsed as html/google_doc
# ---------------------------------------------------------------------------

def test_google_doc_returns_google_doc_source_type(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://docs.google.com/document/d/abc123/edit",
        status_code=200,
        headers={"content-type": "text/html"},
        text=HTML_MINIMAL,
    )
    result = fetch("https://docs.google.com/document/d/abc123/edit")
    assert result.source_type == "google_doc"
