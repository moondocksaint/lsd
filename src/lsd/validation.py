"""Optional agentskills-spec validation of a written package.

Wraps the ``skills-ref`` validator (the reference implementation of the Agent
Skills spec) so the pipeline can surface spec problems at build time without
taking a hard dependency on it. ``skills-ref`` is a dev/optional dependency, so
``validate_package`` degrades gracefully to "not checked" when it is absent.

The directory-name/`name`-slug match that ``skills-ref`` enforces is a
*packaging-time* concern here: ``lsd build`` writes into a user-chosen output
directory, and ``lsd package`` aligns the archive root with the slug. So a
directory-name mismatch is reported as an informational hint, not a spec error —
everything else ``skills-ref`` flags is a real problem with the generated
``SKILL.md`` frontmatter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PackageValidation:
    """Result of validating a written package against the agentskills spec."""

    checked: bool                       # False when skills-ref is not installed
    errors: list[str] = field(default_factory=list)   # real spec errors
    dir_name_hint: str = ""             # set when the dir isn't named after the slug
    validator: str = ""                 # e.g. "skills-ref"

    @property
    def ok(self) -> bool:
        """True only when validation actually ran and found no real errors."""
        return self.checked and not self.errors


def _is_dir_name_mismatch(message: str) -> bool:
    """Recognise skills-ref's benign directory-name/slug mismatch message."""
    return message.startswith("Directory name ") and "must match skill name" in message


def validate_package(package_dir: Path) -> PackageValidation:
    """Validate the SKILL.md in ``package_dir`` against the agentskills spec.

    Returns a ``PackageValidation``. If ``skills-ref`` is not importable, the
    result has ``checked=False`` (the caller should note validation was skipped
    rather than treat the package as valid).
    """
    try:
        import skills_ref  # noqa: PLC0415 — optional dependency, imported lazily
    except Exception:
        return PackageValidation(checked=False)

    # Validation is advisory and runs after the package is already written, so a
    # validator bug must never turn a successful build into a crash — treat any
    # unexpected failure as "not checked".
    try:
        raw_errors = skills_ref.validate(Path(package_dir))
    except Exception:
        return PackageValidation(checked=False)

    errors: list[str] = []
    dir_name_hint = ""
    for message in raw_errors:
        if _is_dir_name_mismatch(message):
            dir_name_hint = message
        else:
            errors.append(message)

    return PackageValidation(
        checked=True,
        errors=errors,
        dir_name_hint=dir_name_hint,
        validator="skills-ref",
    )
