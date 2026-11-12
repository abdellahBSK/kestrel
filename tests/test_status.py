"""Liveness rules: heartbeats, PIDs, agent states and project health."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest

from kestrel.core import status

TH = {"heartbeat_timeout": 45, "idle_after": 120, "stale_after": 600}


@pytest.fixture(scope="module")
def dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def test_pid_alive(dead_pid):
    assert status.pid_alive(os.getpid())
    assert not status.pid_alive(dead_pid)
    assert not status.pid_alive(0) and not status.pid_alive(None)


def test_heartbeat_keeps_the_marker_fresh_and_removes_it(tmp_path):
    f = tmp_path / "current.json"
    with status.Heartbeat(f, {"team": "sandbox", "session": "s1"}, every=0.05) as hb:
        first = json.loads(f.read_text())
        assert first["pid"] == os.getpid() and first["team"] == "sandbox"
        hb.update(child_pid=123)
        time.sleep(0.25)
        later = json.loads(f.read_text())
        assert later["heartbeat"] > first["heartbeat"] and later["child_pid"] == 123
    assert not f.exists()


def write_current(state, **info):
    state.mkdir(exist_ok=True)
    (state / "current.json").write_text(json.dumps({"team": "sandbox", "session": "s1", **info}))


def test_run_state_trusts_only_a_fresh_heartbeat_from_a_live_runner(tmp_path, dead_pid):
    now = time.time()
    assert status.run_state(tmp_path, 45, now) is None
    write_current(tmp_path, heartbeat=now - 5, pid=os.getpid())
    assert status.run_state(tmp_path, 45, now)["state"] == "running"
    write_current(tmp_path, heartbeat=now - 600, pid=dead_pid)
    assert status.run_state(tmp_path, 45, now)["state"] == "lost"
    write_current(tmp_path, heartbeat=now - 5, pid=dead_pid)  # fresh file, but the runner is gone
    assert status.run_state(tmp_path, 45, now)["state"] == "lost"


def test_run_state_counts_an_orphaned_agent_process_as_running(tmp_path, dead_pid):
    now = time.time()
    write_current(tmp_path, heartbeat=now - 600, pid=dead_pid, child_pid=os.getpid())
    assert status.run_state(tmp_path, 45, now)["state"] == "running"


def test_run_state_for_markers_from_older_runners(tmp_path, dead_pid):
    write_current(tmp_path, since=1.0)  # no heartbeat field: fall back to the PID in run.lock
    assert status.run_state(tmp_path, 45)["state"] == "lost"
    (tmp_path / "run.lock").write_text(str(dead_pid))
    assert status.run_state(tmp_path, 45)["state"] == "lost"
    (tmp_path / "run.lock").write_text(str(os.getpid()))
    assert status.run_state(tmp_path, 45)["state"] == "running"


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        ({"finished": True, "live": True, "last_activity": 0}, "finished"),
        ({"finished": True, "live": False, "last_activity": 0}, "finished"),
        ({"finished": False, "live": True, "last_activity": 1000 - 10}, "working"),
        ({"finished": False, "live": True, "last_activity": 1000 - 200}, "idle"),
        ({"finished": False, "live": True, "last_activity": 1000 - 700}, "stale"),
        ({"finished": False, "live": True, "last_activity": 1000 - 700, "waiting": True}, "waiting"),
        ({"finished": False, "live": False, "last_activity": 990}, "lost"),  # cut off when the run ended
        ({"finished": False, "live": False, "last_activity": 990, "ended_cleanly": True}, "finished"),
        ({"finished": False, "live": False, "last_activity": 990, "failed": True}, "failed"),
    ],
)
def test_agent_state(kwargs, expected):
    assert status.agent_state(now=1000, th=TH, **kwargs) == expected


@pytest.mark.parametrize(
    "run, has_runs, states, expected",
    [
        (None, False, [], "never"),
        (None, True, ["finished", "finished"], "idle"),
        (None, True, ["finished", "lost"], "incomplete"),
        (None, True, ["failed", "lost"], "failed"),
        ("running", True, ["waiting", "working"], "running"),
        ("running", True, ["waiting", "stale"], "stale"),
        ("lost", True, ["lost"], "lost"),
    ],
)
def test_team_health_is_the_worst_true_state(run, has_runs, states, expected):
    assert status.team_health(run, has_runs, states) == expected


def test_run_results_and_failures(tmp_path):
    (tmp_path / "run-2026-01-01.json").write_text(json.dumps([{"session": "a", "status": "ok"}]))
    (tmp_path / "run-2026-01-02.json").write_text(json.dumps([{"session": "b", "status": "failed: boom"}]))
    (tmp_path / "run-2026-01-03.json").write_text("not json")
    assert status.run_results(tmp_path) == {"a": "ok", "b": "failed: boom"}
    assert status.is_failure("failed: boom") and status.is_failure("usage-limit")
    assert not status.is_failure("ok") and not status.is_failure("budget-stop") and not status.is_failure(None)


def test_iso_is_always_utc():
    assert status.iso(0) == "1970-01-01T00:00:00Z"
    assert status.iso(1794473380.39).endswith("Z")


def test_thresholds_come_from_the_config():
    assert status.thresholds({}) == {k: float(v) for k, v in status.DEFAULTS.items()}
    assert status.thresholds({"monitor": {"stale_after": 60}})["stale_after"] == 60.0
