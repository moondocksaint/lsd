"""Tests for `lsd eval --init` baseline creation (no network — build is stubbed)."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from lsd.cli import main


def _make_case(tmp_path: Path) -> Path:
    case = tmp_path / "case"
    case.mkdir()
    (case / "input.json").write_text(json.dumps({"url": "https://example.com"}))
    return case


def _fake_build(url, out_dir, *args, **kwargs):
    """Stand-in for pipeline.build — writes a minimal package, no network."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "SKILL.md").write_text(
        "---\nname: demo\ndescription: A sufficiently long demo description here.\n"
        "---\n\n## Purpose\n\nBody.\n"
    )
    (out_dir / "metadata.json").write_text("{}")
    return out_dir


def test_init_creates_baseline(tmp_path, monkeypatch):
    monkeypatch.setattr("lsd.cli.build", _fake_build)
    case = _make_case(tmp_path)

    result = CliRunner().invoke(main, ["eval", str(case), "--init"])
    assert result.exit_code == 0, result.output
    assert (case / "expected" / "SKILL.md").exists()


def test_init_refuses_overwrite_without_force(tmp_path, monkeypatch):
    monkeypatch.setattr("lsd.cli.build", _fake_build)
    case = _make_case(tmp_path)
    (case / "expected").mkdir()
    (case / "expected" / "stale.md").write_text("old baseline")

    result = CliRunner().invoke(main, ["eval", str(case), "--init"])
    assert result.exit_code == 1
    assert "already contains a baseline" in result.output
    # The existing baseline must be left untouched.
    assert (case / "expected" / "stale.md").exists()


def test_init_force_overwrites_and_clears_stale(tmp_path, monkeypatch):
    monkeypatch.setattr("lsd.cli.build", _fake_build)
    case = _make_case(tmp_path)
    (case / "expected").mkdir()
    (case / "expected" / "stale.md").write_text("old baseline")

    result = CliRunner().invoke(main, ["eval", str(case), "--init", "--force"])
    assert result.exit_code == 0, result.output
    assert (case / "expected" / "SKILL.md").exists()
    # Stale files from the previous baseline are cleared.
    assert not (case / "expected" / "stale.md").exists()


def test_init_conflicts_with_output(tmp_path, monkeypatch):
    monkeypatch.setattr("lsd.cli.build", _fake_build)
    case = _make_case(tmp_path)

    result = CliRunner().invoke(
        main, ["eval", str(case), "--init", "-o", str(tmp_path / "elsewhere")]
    )
    assert result.exit_code == 1
    assert "conflicts with --init" in result.output
    assert not (case / "expected").exists()
