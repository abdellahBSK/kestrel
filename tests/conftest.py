"""Test setup: every test runs against a throwaway home folder, never your real one.

The home folder must be chosen before any `kestrel` module is imported (paths are resolved
at import time), so it is set here at conftest import.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_HOME = Path(tempfile.mkdtemp(prefix="kestrel-test-home-"))
shutil.copyfile(ROOT / "config.example.toml", _HOME / "config.toml")
os.environ["KESTREL_HOME"] = str(_HOME)

from kestrel import meter  # noqa: E402
from kestrel.adapters import claude_code  # noqa: E402
from kestrel.storage import store as store_module  # noqa: E402


@pytest.fixture
def home() -> Path:
    return _HOME


@pytest.fixture(autouse=True)
def fake_claude_projects(tmp_path, monkeypatch) -> Path:
    """An empty stand-in for ~/.claude/projects, so tests never read real session logs."""
    projects = tmp_path / "claude-projects"
    projects.mkdir()
    monkeypatch.setattr(meter, "PROJECTS", projects)
    return projects


@pytest.fixture(autouse=True)
def fresh_store(tmp_path, monkeypatch):
    """Every test gets its own empty event store."""
    monkeypatch.setattr(store_module, "DEFAULT_PATH", tmp_path / "events.db")
    claude_code._SEEN.clear()
    yield store_module.open_store()
    claude_code._SEEN.clear()


def write_transcript(path: Path, records: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    return path


def usage_record(ts: str, msg_id: str, model: str = "claude-opus-5-5", inp=0, out=0, cw=0, cr=0, content=None) -> dict:
    return {
        "type": "assistant",
        "timestamp": ts,
        "requestId": f"req-{msg_id}",
        "message": {
            "id": msg_id,
            "model": model,
            "usage": {
                "input_tokens": inp,
                "output_tokens": out,
                "cache_creation_input_tokens": cw,
                "cache_read_input_tokens": cr,
            },
            "content": content or [],
        },
    }


def team_project_dir(projects: Path, team: str) -> Path:
    """The folder Claude Code would create for a session started in <home>/teams/<team>."""
    return projects / meter.sanitize(str(meter.HQ / "teams" / team))
