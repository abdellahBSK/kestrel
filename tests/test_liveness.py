"""End to end: what the dashboard reports for live, finished, cut-off and lost runs."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import pytest

from conftest import team_project_dir, usage_record, write_transcript
from controlroom import server
from controlroom.runner import orchestrator as orch

T0 = "2026-11-12T08:49:43.000Z"


def tool_use(ts, msg_id, tool_id, command="npm test"):
    return usage_record(
        ts, msg_id, content=[{"type": "tool_use", "id": tool_id, "name": "Bash", "input": {"command": command}}]
    )


def final_answer(ts, msg_id):
    rec = usage_record(ts, msg_id, content=[{"type": "text", "text": "Done."}])
    rec["message"]["stop_reason"] = "end_turn"
    return rec


def make_session(projects, sid, lead, subs=()):
    """A lead transcript plus subagents: subs = [(name, role, finished, age_seconds)]."""
    folder = team_project_dir(projects, "sandbox")
    write_transcript(folder / f"{sid}.jsonl", lead)
    for name, role, finished, age in subs:
        sub = folder / sid / "subagents"
        write_transcript(sub / f"{name}.jsonl", [tool_use(T0, f"{name}-m", f"{name}-t")])
        meta = {"agentType": role, "description": f"{role} task", **({"finished": True} if finished else {})}
        (sub / f"{name}.meta.json").write_text(json.dumps(meta))
        t = time.time() - age
        os.utime(sub / f"{name}.jsonl", (t, t))


@pytest.fixture(autouse=True)
def clean_state(home, monkeypatch):
    monkeypatch.setattr(server.kingdom, "open_prs", lambda t: [])
    server.CACHE.data.clear()
    state = home / "state"
    state.mkdir(exist_ok=True)
    yield state
    for f in state.iterdir():
        f.unlink()
    server.CACHE.data.clear()


@pytest.fixture(scope="module")
def dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


def states(detail):
    return {a["description"]: a["state"] for a in detail["agents"]}


def team(ov, name="sandbox"):
    return next(t for t in ov["teams"] if t["team"] == name)


def test_finished_run_with_a_cut_off_agent(fake_claude_projects):
    """The 12 Nov case: the lead ended the run while a background developer was still mid-task."""
    make_session(
        fake_claude_projects,
        "s1",
        [tool_use(T0, "m1", "t1"), final_answer("2026-11-12T08:49:36.000Z", "m2")],
        [("a1", "tester", True, 0), ("a2", "developer", False, 0)],
    )
    d = server.session_detail("sandbox", None)
    assert d["live"] is False and d["started_at"] == T0
    assert d["sessions"][0]["started_at"] == T0 and d["sessions"][0]["updated_at"].endswith("Z")
    assert states(d) == {"Team lead": "finished", "tester task": "finished", "developer task": "lost"}
    t = team(server.overview())
    assert t["health"] == "incomplete" and t["running"] is False and t["started_at"] == T0


def test_run_whose_runner_died_is_lost_not_working(fake_claude_projects, clean_state, dead_pid):
    """The player-expert-system case: the runner process died and left its marker behind."""
    make_session(fake_claude_projects, "s1", [tool_use(T0, "m1", "t1")], [("a1", "developer", False, 0)])
    (clean_state / "current.json").write_text(
        json.dumps({"team": "sandbox", "session": "s1", "since": 1.0, "heartbeat": time.time() - 3600, "pid": dead_pid})
    )
    ov = server.overview()
    assert ov["running"] is None and ov["lost_run"]["team"] == "sandbox"
    t = team(ov)
    assert t["health"] == "lost" and t["running"] is False and t["run_state"] == "lost"
    assert states(server.session_detail("sandbox", "s1")) == {"Team lead": "lost", "developer task": "lost"}


def test_live_run_shows_working_waiting_and_stale(fake_claude_projects, clean_state):
    make_session(
        fake_claude_projects,
        "s1",
        [tool_use(T0, "m1", "t1")],
        [("a1", "developer", False, 5), ("a2", "tester", True, 0)],
    )
    (clean_state / "current.json").write_text(
        json.dumps(
            {"team": "sandbox", "session": "s1", "since": time.time(), "heartbeat": time.time(), "pid": os.getpid()}
        )
    )
    d = server.session_detail("sandbox", "s1")
    assert d["live"] is True
    assert states(d) == {"Team lead": "waiting", "developer task": "working", "tester task": "finished"}
    assert team(server.overview())["health"] == "running"

    stale = time.time() - 3600
    os.utime(team_project_dir(fake_claude_projects, "sandbox") / "s1" / "subagents" / "a1.jsonl", (stale, stale))
    server.CACHE.data.clear()
    assert states(server.session_detail("sandbox", "s1"))["developer task"] == "stale"
    assert team(server.overview())["health"] == "stale"


def test_failed_run_marks_the_lead_failed(fake_claude_projects, clean_state):
    make_session(fake_claude_projects, "s1", [tool_use(T0, "m1", "t1")])
    (clean_state / "run-2026-11-12.json").write_text(json.dumps([{"session": "s1", "status": "error"}]))
    assert states(server.session_detail("sandbox", None)) == {"Team lead": "failed"}
    assert team(server.overview())["health"] == "failed"


def test_overview_is_utc_only():
    ov = server.overview()
    assert "now" not in ov and isinstance(ov["utc_offset_min"], int)
    assert all("last_run" not in t for t in ov["teams"])


def test_runner_takes_over_a_dead_runners_lock(clean_state, dead_pid):
    (clean_state / "run.lock").write_text(str(os.getpid()))
    assert orch.acquire_lock() is False  # a live runner holds it
    (clean_state / "run.lock").write_text(str(dead_pid))
    assert orch.acquire_lock() is True
    assert (clean_state / "run.lock").read_text() == str(os.getpid())


def test_runner_records_a_lost_run_and_clears_the_marker(clean_state, dead_pid):
    cfg = orch.meter.load_config()
    since = time.time() - 7200
    (clean_state / "current.json").write_text(
        json.dumps({"team": "sandbox", "session": "s9", "since": since, "heartbeat": since, "pid": dead_pid})
    )
    run = orch.recover_lost_run(cfg)
    assert run and run["session"] == "s9"
    assert not (clean_state / "current.json").exists()
    rows = [r for f in clean_state.glob("run-*.json") for r in json.loads(f.read_text())]
    assert {"team": "sandbox", "session": "s9", "status": "lost"}.items() <= rows[0].items()
    assert orch.recover_lost_run(cfg) is None  # nothing left to recover


def test_results_of_the_same_day_are_merged(clean_state):
    orch.save_results("2026-11-12", [{"session": "a", "status": "lost"}])
    orch.save_results("2026-11-12", [{"session": "b", "status": "ok"}, {"session": "a", "status": "ok"}])
    rows = json.loads((clean_state / "run-2026-11-12.json").read_text())
    assert sorted((r["session"], r["status"]) for r in rows) == [("a", "ok"), ("b", "ok")]


def test_hooks_include_the_stop_check():
    assert "Stop" in orch.settings_json()["hooks"]
