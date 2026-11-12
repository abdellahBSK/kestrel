"""Publish PR screenshots to the repo's `agent-previews` branch and print markdown for the PR.

  python preview.py --repo repo --branch feat/TEL-014-lock-screen-ui previews/TEL-014-*.png

Images go to `agent-previews:<task-branch>/<file>` using git plumbing (the working tree and
the task branch are untouched), so they never end up in main. The printed links render in
the PR for anyone with access to the repo (private repos included).
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import quote

REF = "agent-previews"


def git(repo: str, *args: str, env: dict | None = None, check: bool = True, data: bytes | None = None) -> str:
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, input=data, env={**os.environ, **(env or {})})
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed: {r.stderr.decode(errors='replace').strip()}")
    return r.stdout.decode(errors="replace").strip()


def main() -> None:
    if os.environ.get("AGENTHQ_PR_MODE", "ready") == "none":
        sys.exit("PR MODE = none: previews are not published. Keep them in previews/ and mention them in the report.")
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default="repo")
    ap.add_argument("--branch", required=True)
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()

    files = [Path(f) for pattern in a.files for f in (glob.glob(pattern) or [pattern])]
    files = [f for f in files if f.is_file() and f.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp")]
    if not files:
        sys.exit("No image files found: take screenshots with shoot.py first.")
    url = git(a.repo, "remote", "get-url", "origin")
    m = re.search(r"github\.com[/:]([^/]+)/(.+?)(\.git)?$", url)
    if not m:
        sys.exit("origin is not a GitHub repository.")
    owner, name = m.group(1), m.group(2)
    safe_branch = re.sub(r"[^A-Za-z0-9/_.-]", "-", a.branch)

    for attempt in range(2):
        git(a.repo, "fetch", "-q", "origin", f"+refs/heads/{REF}:refs/remotes/origin/{REF}", check=False)
        parent = git(a.repo, "rev-parse", "--verify", "-q", f"refs/remotes/origin/{REF}", check=False)
        with tempfile.TemporaryDirectory() as tmp:
            env = {"GIT_INDEX_FILE": str(Path(tmp) / "index")}
            if parent:
                git(a.repo, "read-tree", parent, env=env)
            for f in files:
                blob = git(a.repo, "hash-object", "-w", "--stdin", data=f.read_bytes())
                git(a.repo, "update-index", "--add", "--cacheinfo", f"100644,{blob},{safe_branch}/{f.name}", env=env)
            tree = git(a.repo, "write-tree", env=env)
        args = ["commit-tree", tree, "-m", f"Add previews for {a.branch}"]
        if parent:
            args[2:2] = ["-p", parent]
        commit = git(a.repo, *args)
        r = subprocess.run(
            ["git", "-C", a.repo, "push", "-q", "origin", f"{commit}:refs/heads/{REF}"], capture_output=True
        )
        if r.returncode == 0:
            break
        if attempt == 1:
            sys.exit(f"push to {REF} failed: {r.stderr.decode(errors='replace').strip()}")

    for f in files:
        path = quote(f"{safe_branch}/{f.name}")
        alt = f.stem.replace("-", " ")
        print(f"![{alt}](https://github.com/{owner}/{name}/blob/{REF}/{path}?raw=true)")


if __name__ == "__main__":
    main()
