"""Prepare a release: bump the version, date the changelog, commit and tag. Nothing is pushed.

    python scripts/release.py 0.1.0

Then push the commit and the tag (see RELEASING.md); the tag starts the release workflow.
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INIT = ROOT / "src" / "kestrel" / "__init__.py"
CHANGELOG = ROOT / "CHANGELOG.md"
REPO = "https://github.com/abdellahBSK/kestrel"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def fail(msg: str) -> None:
    sys.exit(f"release: {msg}")


def main() -> None:
    if len(sys.argv) != 2 or not re.fullmatch(r"\d+\.\d+\.\d+", sys.argv[1]):
        fail("usage: python scripts/release.py X.Y.Z")
    version = sys.argv[1]
    tag = f"v{version}"
    if git("status", "--porcelain"):
        fail("the working tree has changes: commit or stash them first")
    if git("rev-parse", "--abbrev-ref", "HEAD") != "main":
        fail("release from main")
    if tag in git("tag", "--list", tag).splitlines():
        fail(f"{tag} already exists")

    text = CHANGELOG.read_text(encoding="utf-8")
    if "## [Unreleased]" not in text:
        fail("CHANGELOG.md has no [Unreleased] section")
    section = text.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
    if not section.strip():
        fail("the [Unreleased] section of CHANGELOG.md is empty")
    today = dt.date.today().isoformat()
    text = text.replace("## [Unreleased]", f"## [Unreleased]\n\n## [{version}] - {today}", 1)
    previous = re.findall(r"^\[(\d+\.\d+\.\d+)\]:", text, re.M)
    links = re.compile(r"^\[Unreleased\]:.*$", re.M)
    since = f"v{previous[0]}" if previous else None
    new_links = f"[Unreleased]: {REPO}/compare/{tag}...HEAD\n" + (
        f"[{version}]: {REPO}/compare/{since}...{tag}" if since else f"[{version}]: {REPO}/releases/tag/{tag}"
    )
    text = links.sub(new_links, text, count=1)
    CHANGELOG.write_text(text, encoding="utf-8", newline="\n")

    init = INIT.read_text(encoding="utf-8")
    INIT.write_text(
        re.sub(r'__version__ = "[^"]+"', f'__version__ = "{version}"', init), encoding="utf-8", newline="\n"
    )

    git("add", str(CHANGELOG), str(INIT))
    git("commit", "-q", "-m", f"Release {version}")
    git("tag", "-a", tag, "-m", f"Kestrel {version}")
    print(f"Release {version} is committed and tagged {tag}. Nothing is pushed yet.")
    print("Push it to publish (PyPI, GitHub release, Docker image):")
    print(f"  git push origin main {tag}")


if __name__ == "__main__":
    main()
