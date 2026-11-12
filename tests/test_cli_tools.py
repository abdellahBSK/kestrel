"""`controlroom emit`, `ingest` and `token`, run as a user would."""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from controlroom.store import Store


def cli(home, *args, stdin=None, store_path=None):
    env = {**os.environ, "CONTROLROOM_HOME": str(home)}
    r = subprocess.run(
        [sys.executable, "-m", "controlroom", *args],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    return r.returncode, r.stdout.strip(), r.stderr.strip()


@pytest.fixture
def home(tmp_path):
    return tmp_path  # an empty home: no config at all must work too


def events(home):
    s = Store(home / "data" / "events.db")
    try:
        return [(p, s.run_events(p, r["id"])) for p in s.projects() for r in s.runs(p)]
    finally:
        s.close()


def test_emit_a_whole_run_without_a_server(home):
    code, run, _ = cli(home, "emit", "run.started", "--project", "shop", "-d", "title=Fix login")
    assert code == 0 and run
    assert (
        cli(home, "emit", "agent.started", "--project", "shop", "--run", run, "--agent", "dev", "-d", "role=developer")[
            0
        ]
        == 0
    )
    assert (
        cli(
            home,
            "emit",
            "agent.tokens",
            "--project",
            "shop",
            "--run",
            run,
            "--agent",
            "dev",
            "-d",
            "input=120",
            "-d",
            "output=30",
        )[0]
        == 0
    )
    assert cli(home, "emit", "run.finished", "--project", "shop", "--run", run, "--data", '{"status": "ok"}')[0] == 0
    [(project, rows)] = events(home)
    assert project == "shop" and [r[1] for r in rows] == [
        "run.started",
        "agent.started",
        "agent.tokens",
        "run.finished",
    ]
    assert rows[2][3]["input"] == 120  # numbers stay numbers


def test_emit_explains_a_bad_event(home):
    code, _, err = cli(home, "emit", "agent.action", "--project", "shop", "--run", "r1")
    assert code == 2 and "agent is required" in err
    code, _, err = cli(home, "emit", "run.started", "--project", "shop", "-d", "oops")
    assert code == 2 and "KEY=VALUE" in err


def test_ingest_json_lines_from_stdin(home):
    lines = "\n".join(
        json.dumps({"type": "agent.message", "project": "api", "run": "r1", "agent": "a", "data": {"text": str(i)}})
        for i in range(3)
    )
    code, out, _ = cli(home, "ingest", "-", stdin=lines + '\n{"type": "nope"}\n')
    assert code == 1 and out.startswith("3 accepted, 0 already stored, 1 rejected")


def test_token_is_printed_and_stable(home):
    first = cli(home, "token")[1]
    assert len(first) > 30 and cli(home, "token")[1] == first
