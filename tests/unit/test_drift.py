"""Tests for the drift-magnitude classifier and its similarity swap point.

Covers cli._content_similarity (the documented embedding swap seam) and
cli._classify_magnitude (direct-diff and proxy modes).
"""

from __future__ import annotations

from lsd.cli import _classify_magnitude, _content_lines, _content_similarity


# ---------------------------------------------------------------------------
# _content_similarity — default lexical ratio + injectable seam
# ---------------------------------------------------------------------------

def test_content_similarity_identical_is_one():
    lines = ["## Content", "", "alpha", "beta", "gamma"]
    assert _content_similarity(lines, lines) == 1.0


def test_content_similarity_disjoint_is_low():
    old = [f"old line {i}" for i in range(40)]
    new = [f"new content {i}" for i in range(40)]
    assert _content_similarity(old, new) < 0.5


def test_content_similarity_accepts_injected_fn():
    """The embedding swap: a caller can inject any similarity function."""
    seen: dict[str, object] = {}

    def fake_cosine(old: list[str], new: list[str]) -> float:
        seen["old"], seen["new"] = old, new
        return 0.42

    result = _content_similarity(["a"], ["b"], similarity_fn=fake_cosine)
    assert result == 0.42
    assert seen["old"] == ["a"] and seen["new"] == ["b"]


# ---------------------------------------------------------------------------
# _classify_magnitude — direct diff (old source.md available)
# ---------------------------------------------------------------------------

def _content(lines: list[str]) -> str:
    return "## Content\n\n" + "\n".join(lines)


def test_direct_diff_substantial_on_full_rewrite():
    old = _content([f"original point number {i}" for i in range(50)])
    new = _content([f"completely rewritten idea {i}" for i in range(50)])
    state, note = _classify_magnitude(new, old_normalised=old)
    assert state == "SUBSTANTIAL"
    assert "similarity" in note


def test_direct_diff_minor_on_small_edit():
    base = [f"stable line {i}" for i in range(50)]
    old = _content(base)
    new = _content(base + ["one appended sentence at the end"])
    state, _ = _classify_magnitude(new, old_normalised=old)
    assert state == "MINOR"


def test_direct_diff_substantial_on_heading_loss():
    old = "## Content\n\n### A\ntext\n### B\ntext\n### C\ntext\n### D\ntext\n"
    new = "## Content\n\n### A\ntext\n"  # dropped 3 of 4 headings
    state, _ = _classify_magnitude(new, old_normalised=old)
    assert state == "SUBSTANTIAL"


# ---------------------------------------------------------------------------
# _classify_magnitude — proxy heuristic (no stored source.md)
# ---------------------------------------------------------------------------

def test_proxy_minor_for_substantial_length():
    state, _ = _classify_magnitude(_content(["word " * 300]))
    assert state == "MINOR"


def test_proxy_substantial_for_tiny_result():
    state, _ = _classify_magnitude("short")
    assert state == "SUBSTANTIAL"


# ---------------------------------------------------------------------------
# _content_lines — header stripping
# ---------------------------------------------------------------------------

def test_content_lines_strips_metadata_header():
    normalised = (
        "# Source — Title\n\n- Canonical URL: https://x\n- Retrieved: 2026\n"
        "- Word count: 5\n\n## Content\n\nreal body line\n"
    )
    lines = _content_lines(normalised)
    assert lines[0] == "## Content"
    assert "real body line" in lines
    assert not any("Canonical URL" in ln for ln in lines)
