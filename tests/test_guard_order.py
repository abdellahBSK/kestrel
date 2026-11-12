"""The guard keeps the team in order: QA after tests, and no ending the run while agents still work."""

from __future__ import annotations

import json
import os
import time

import pytest

from test_guard import decision, pre, run_guard


@pytest.fixture
def transcript(tmp_path):
    """A lead transcript with a subagents folder next to it, as Claude Code lays them out."""
    tp = tmp_path / "session.jsonl"
    tp.write_text("")
    (tmp_path / "session" / "subagents").mkdir(parents=True)
    return tp


def subagent(tp, name, role, finished=False, age=0.0):
    folder = tp.with_suffix("") / "subagents"
    meta = {"agentType": role, "description": f"{role} task", **({"finished": True} if finished else {})}
    (folder / f"{name}.meta.json").write_text(json.dumps(meta))
    log = folder / f"{name}.jsonl"
    log.write_text("{}\n")
    t = time.time() - age
    os.utime(log, (t, t))


def spawn(tp, role):
    return {**pre("Agent", subagent_type=role, description="x", prompt="y"), "transcript_path": str(tp)}


def test_qa_waits_for_a_running_tester(home, transcript):
    subagent(transcript, "a1", "tester")
    out = run_guard(home, spawn(transcript, "qa"))
    assert decision(out) == "deny"
    assert "wait for the tester" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_qa_may_start_once_the_tester_reported_back(home, transcript):
    subagent(transcript, "a1", "tester", finished=True)
    subagent(transcript, "a2", "security")  # unrelated roles don't block QA
    assert decision(run_guard(home, spawn(transcript, "qa"))) == "allow"


def test_a_stale_tester_does_not_block_forever(home, transcript):
    subagent(transcript, "a1", "tester", age=3600)
    assert decision(run_guard(home, spawn(transcript, "qa"))) == "allow"


def test_tester_waits_for_the_developer_but_developers_never_wait(home, transcript):
    subagent(transcript, "a1", "developer")
    assert decision(run_guard(home, spawn(transcript, "tester"))) == "deny"
    assert decision(run_guard(home, spawn(transcript, "qa"))) == "deny"
    assert decision(run_guard(home, spawn(transcript, "developer"))) == "allow"
    assert decision(run_guard(home, spawn(transcript, "security"))) == "allow"


def stop_event(tp, active=False):
    return {"hook_event_name": "Stop", "transcript_path": str(tp), "stop_hook_active": active}


def test_lead_cannot_end_the_run_while_agents_work(home, transcript):
    subagent(transcript, "a1", "developer")
    out = run_guard(home, stop_event(transcript))
    assert out["decision"] == "block" and "developer" in out["reason"]


def test_stop_is_allowed_on_the_retry_and_when_nothing_runs(home, transcript):
    subagent(transcript, "a1", "developer")
    assert run_guard(home, stop_event(transcript, active=True)) is None  # nudge once, never loop
    subagent(transcript, "a1", "developer", finished=True)
    assert run_guard(home, stop_event(transcript)) is None


def test_stop_flag_and_non_team_sessions_are_never_held(home, transcript):
    subagent(transcript, "a1", "developer")
    assert run_guard(home, stop_event(transcript), KESTREL_TEAM="") is None
    (home / "STOP").write_text("x")
    try:
        assert run_guard(home, stop_event(transcript)) is None
    finally:
        (home / "STOP").unlink()
