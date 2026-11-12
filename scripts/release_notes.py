"""Print the CHANGELOG.md section of one version (the GitHub release notes).

python scripts/release_notes.py 0.1.0 > notes.md
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"
LINK = re.compile(r"^\[[^\]]+\]: https?://")


def notes(version: str, text: str) -> str:
    out, inside = [], False
    for line in text.splitlines():
        if line.startswith("## ["):
            if inside:
                break
            inside = line.startswith(f"## [{version}]")
            continue
        if inside and not LINK.match(line):  # the compare links at the end of the file
            out.append(line)
    return "\n".join(out).strip()


if __name__ == "__main__":
    body = notes(sys.argv[1], CHANGELOG.read_text(encoding="utf-8"))
    print(body or "See CHANGELOG.md")
