"""The release helpers (RELEASING.md)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("release_notes", ROOT / "scripts" / "release_notes.py")
release_notes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release_notes)

CHANGELOG = """# Changelog

## [Unreleased]

### Added
- Coming soon.

## [0.2.0] - 2027-01-10

### Added
- Team mode.

## [0.1.0] - 2026-11-12

### Added
- The first release.

[Unreleased]: https://github.com/a/b/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/a/b/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/a/b/releases/tag/v0.1.0
"""


def test_notes_are_one_versions_section():
    assert release_notes.notes("0.2.0", CHANGELOG) == "### Added\n- Team mode."


def test_the_last_section_leaves_out_the_links():
    assert release_notes.notes("0.1.0", CHANGELOG) == "### Added\n- The first release."


def test_an_unknown_version_has_no_notes():
    assert release_notes.notes("9.9.9", CHANGELOG) == ""


def test_the_real_changelog_has_an_unreleased_section():
    assert "## [Unreleased]" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
