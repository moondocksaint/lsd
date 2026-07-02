"""Tests for lsd.validation — the optional skills-ref spec check wrapper."""

from __future__ import annotations

from pathlib import Path

from lsd.validation import PackageValidation, validate_package

# skills-ref is a dev/test dependency, so it is importable in the test env.

_VALID_SKILL = """\
---
name: {name}
description: >-
  Use this skill when reviewing content for rule adherence. Applies a checklist
  derived from the source and reports findings with evidence.
allowed-tools: Read
metadata:
  lsd_version: "0.5.0"
---

## Purpose

Body.
"""


def _write_skill(dir_path: Path, name: str, body: str | None = None) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / "SKILL.md").write_text(body or _VALID_SKILL.format(name=name))
    return dir_path


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_valid_package_when_dir_matches_slug(tmp_path):
    pkg = _write_skill(tmp_path / "reviewer-demo", "reviewer-demo")
    result = validate_package(pkg)
    assert isinstance(result, PackageValidation)
    assert result.checked
    assert result.ok
    assert result.errors == []
    assert result.dir_name_hint == ""
    assert result.validator == "skills-ref"


# ---------------------------------------------------------------------------
# Directory-name mismatch is benign (build output goes to a chosen dir)
# ---------------------------------------------------------------------------

def test_dir_name_mismatch_is_hint_not_error(tmp_path):
    # Directory 'out' does not match the slug 'reviewer-demo'.
    pkg = _write_skill(tmp_path / "out", "reviewer-demo")
    result = validate_package(pkg)
    assert result.checked
    assert result.ok, f"dir-name mismatch should not fail validation: {result.errors}"
    assert result.errors == []
    assert result.dir_name_hint
    assert "must match skill name" in result.dir_name_hint


# ---------------------------------------------------------------------------
# Real spec violations surface as errors
# ---------------------------------------------------------------------------

def test_disallowed_frontmatter_key_is_error(tmp_path):
    body = (
        "---\n"
        "name: reviewer-demo\n"
        "description: A valid description that is long enough to pass.\n"
        "bogus_key: nope\n"
        "---\n\n## Purpose\n\nBody.\n"
    )
    pkg = _write_skill(tmp_path / "reviewer-demo", "reviewer-demo", body=body)
    result = validate_package(pkg)
    assert result.checked
    assert not result.ok
    assert any("bogus_key" in e or "Unexpected field" in e for e in result.errors)


def test_missing_skill_md_is_error(tmp_path):
    empty = tmp_path / "empty-pkg"
    empty.mkdir()
    result = validate_package(empty)
    assert result.checked
    assert not result.ok
    assert any("SKILL.md" in e for e in result.errors)


# ---------------------------------------------------------------------------
# Graceful skip when skills-ref is unavailable
# ---------------------------------------------------------------------------

def test_graceful_skip_when_validator_missing(tmp_path, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "skills_ref":
            raise ImportError("simulated: skills-ref not installed")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    pkg = _write_skill(tmp_path / "reviewer-demo", "reviewer-demo")
    result = validate_package(pkg)
    assert result.checked is False
    assert result.ok is False  # not checked ⇒ not asserted valid
    assert result.errors == []
