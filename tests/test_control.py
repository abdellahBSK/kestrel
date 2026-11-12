"""Stops and budget caps (spec 008), through every channel that delivers them."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
import uuid

import pytest

from conftest import write_transcript
from kestrel import control
from kestrel.adapters import claude_code_hooks as cch
from kestrel.api import ingest, server
from kestrel.client import Reporter, StopRequested
from kestrel.core import runs
from kestrel.core.events import normalize
from kestrel.storage.store import Store
from test_guard import pre, run_guard

T0 = 1_800_000_000.0
TH = {"heartbeat_timeout": 45, "idle_after": 120, "stale_after": 600}


def started(st, project, run, at, **data):
    st.add([normalize({"type": "run.started", "project": project, "run": run, "ts": at, "data": data}, now=at + 1)])


def tokens(st, project, run, at, **data):
    st.add(
        [
            normalize(
                {"type": "agent.tokens", "project": project, "run": run, "agent": "a", "ts": at, "data": data},
                now=at + 1,
            )
        ]
    )


# ───────────────────────────── who a stop applies to ─────────────────────────────


def test_a_project_stop_covers_its_running_runs_but_not_later_ones(fresh_store):
    started(fresh_store, "shop", "r1", T0)
    fresh_store.add_control("shop", reason="enough", ts=T0 + 10)
    started(fresh_store, "shop", "r2", T0 + 20)
    assert control.requested(fresh_store, "shop", "r1").reason == "enough"
    assert control.requested(fresh_store, "shop", "r2") is None  # started after the request
    assert control.requested(fresh_store, "other", "r1") is None


def test_run_agent_and_everything_scopes(fresh_store):
    started(fresh_store, "shop", "r1", T0)
    started(fresh_store, "shop", "r2", T0)
    fresh_store.add_control("shop", "r1", "dev", reason="loop", ts=T0 + 5)
    assert control.requested(fresh_store, "shop", "r1", "dev").scope == "agent"
    assert control.requested(fresh_store, "shop", "r1", "lead") is None
    assert control.requested(fresh_store, "shop", "r1") is None  # the run itself goes on
    fresh_store.add_control(control.ALL, reason="all", ts=T0 + 6)
    assert control.requested(fresh_store, "shop", "r2").reason == "all"


def test_a_daily_token_cap_stops_and_is_recorded_once(fresh_store):
    cfg = {"projects": {"shop": {"daily_tokens": 1000}}, "budget": {}}
    now = control.day_start(T0) + 3600
    started(fresh_store, "shop", "r1", now - 100)
    tokens(fresh_store, "shop", "r1", now - 50, input=600)
    assert control.check(fresh_store, "shop", "r1", "a", cfg, now) is None
    tokens(fresh_store, "shop", "r1", now - 40, input=500)
    stop = control.check(fresh_store, "shop", "r1", "a", cfg, now)
    assert stop.source == "budget" and "1,000 tokens" in stop.reason
    control.check(fresh_store, "shop", "r1", "a", cfg, now + 5)
    assert len(fresh_store.controls_for("shop")) == 1  # the next checks find the recorded stop


def test_a_daily_dollar_cap(fresh_store):
    cfg = {"projects": {"shop": {"daily_usd": 1.0}}, "budget": {}}
    now = control.day_start(T0) + 3600
    started(fresh_store, "shop", "r1", now - 100)
    tokens(fresh_store, "shop", "r1", now - 50, output=100_000, model="claude-sonnet-5-5")  # $1.00
    assert "$1.00" in control.check(fresh_store, "shop", "r1", "a", cfg, now).reason


def test_yesterdays_spend_does_not_count(fresh_store):
    cfg = {"projects": {"shop": {"daily_tokens": 1000}}, "budget": {}}
    now = control.day_start(T0) + 3600
    started(fresh_store, "shop", "r1", now - 100)
    tokens(fresh_store, "shop", "r1", control.day_start(T0) - 60, input=5000)
    assert control.check(fresh_store, "shop", "r1", "a", cfg, now) is None


def test_a_runs_own_budget_stops_only_that_run(fresh_store):
    started(fresh_store, "shop", "r1", T0, budget=1000)
    started(fresh_store, "shop", "r2", T0)
    tokens(fresh_store, "shop", "r1", T0 + 1, input=1200)
    assert "this run" in control.check(fresh_store, "shop", "r1", None, {"budget": {}}, T0 + 2).reason
    assert control.check(fresh_store, "shop", "r2", None, {"budget": {}}, T0 + 3) is None


# ───────────────────────────── Claude Code hook ─────────────────────────────


def hook(store, sid, name, at, **fields):
    event = {"hook_event_name": name, "session_id": sid, "cwd": ".", "prompt_id": "p1", **fields}
    return cch.process(event, now=at, store=store, project="shop")


def test_a_stopped_claude_code_run_is_refused_and_ended(fresh_store, tmp_path):
    sid = str(uuid.uuid4())
    hook(fresh_store, sid, "UserPromptSubmit", T0, prompt="long job")
    _, answer = hook(fresh_store, sid, "PreToolUse", T0 + 1, tool_name="Bash", tool_use_id="t1", tool_input={})
    assert answer is None
    fresh_store.add_control("shop", "p1", reason="Stopped from the dashboard", ts=T0 + 2)
    _, answer = hook(fresh_store, sid, "PreToolUse", T0 + 3, tool_name="Bash", tool_use_id="t2", tool_input={})
    assert answer["continue"] is False and "Stopped from the dashboard" in answer["stopReason"]
    assert answer["hookSpecificOutput"]["permissionDecision"] == "deny"
    hook(fresh_store, sid, "Stop", T0 + 4, transcript_path=str(write_transcript(tmp_path / "t.jsonl", [])))
    f = runs.fold(fresh_store.run_events("shop", "p1"), heartbeat=None, now=T0 + 5, th=TH)
    assert f["run"]["status"] == "stopped" and f["run"]["summary"] == "Stopped from the dashboard"
    assert any(i["kind"] == "halt" for i in f["feed"])


def test_stopping_a_subagent_refuses_only_its_tools(fresh_store):
    sid = str(uuid.uuid4())
    hook(fresh_store, sid, "UserPromptSubmit", T0, prompt="review")
    hook(fresh_store, sid, "SubagentStart", T0 + 1, agent_id="a1", agent_type="tester")
    fresh_store.add_control("shop", "p1", "a1", reason="looping", ts=T0 + 2)
    _, sub = hook(fresh_store, sid, "PreToolUse", T0 + 3, agent_id="a1", tool_name="Bash", tool_use_id="t1")
    _, main = hook(fresh_store, sid, "PreToolUse", T0 + 4, tool_name="Read", tool_use_id="t2")
    assert sub["hookSpecificOutput"]["permissionDecision"] == "deny" and "continue" not in sub
    assert main is None


def test_the_hook_prints_the_stop_for_claude_code(home):
    import subprocess
    import sys

    sid = str(uuid.uuid4())
    st = Store(home / "data" / "events.db")
    try:
        started(st, "hooked", "p9", T0)
        st.add_control("hooked", reason="enough", ts=T0 + 1)
    finally:
        st.close()
    event = {"hook_event_name": "PreToolUse", "session_id": sid, "cwd": ".", "prompt_id": "p9", "tool_name": "Bash"}
    r = subprocess.run(
        [sys.executable, "-m", "kestrel", "--home", str(home), "hook", "claude-code"],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        timeout=60,
        env={**__import__("os").environ, "KESTREL_PROJECT": "hooked"},
    )
    assert r.returncode == 0 and json.loads(r.stdout)["continue"] is False


# ───────────────────────────── Python client ─────────────────────────────


def test_the_client_sees_a_stop_and_finishes_the_run_as_stopped(fresh_store):
    rep = Reporter("bot", store=fresh_store)
    with rep.run("crawl") as run:
        assert not run.stop_requested
        fresh_store.add_control("bot", reason="enough crawling")
        run._checked = 0  # don't wait for the next poll
        assert run.stop_requested
        run.check()  # raises StopRequested, which the block turns into a clean "stopped"
        pytest.fail("check() should have raised")
    f = runs.fold(fresh_store.run_events("bot", run.id), heartbeat=None, now=9e9, th=TH)
    assert f["run"]["status"] == "stopped" and f["run"]["summary"] == "enough crawling"


def test_stop_requested_is_an_exception_with_the_reason():
    assert StopRequested("why").reason == "why"


# ───────────────────────────── HTTP and the dashboard ─────────────────────────────


@pytest.fixture
def base_url(monkeypatch):
    monkeypatch.setattr(server.orchestrator, "open_prs", lambda t: [])
    server.CACHE.data.clear()
    srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    port = srv.server_address[1]
    monkeypatch.setattr(server, "HOSTS", {f"127.0.0.1:{port}", f"localhost:{port}"})
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}"
    srv.shutdown()


def call(url, method="GET", headers=None):
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, None


def test_http_reporters_ask_whether_to_stop(base_url, fresh_store):
    started(fresh_store, "web", "r1", T0)
    url = f"{base_url}/v1/control?project=web&run=r1"
    assert call(url)[0] == 401
    auth = {"Authorization": f"Bearer {ingest.token()}"}
    assert call(url, headers=auth)[1] == {"stop": False, "reason": None, "scope": None}
    fresh_store.add_control("web", reason="halt", ts=T0 + 1)
    assert call(url, headers=auth)[1] == {"stop": True, "reason": "halt", "scope": "run"}


def test_the_dashboard_requests_stops_for_any_project(base_url, fresh_store, monkeypatch):
    monkeypatch.setattr(server, "DEMO", False)
    started(fresh_store, "web", "r1", __import__("time").time() - 10)  # the server stamps stops with the real time
    status, body = call(f"{base_url}/api/control/stop?project=web&run=r1", "POST", {"X-Kestrel": "1"})
    assert status == 200 and "run r1" in body["msg"]
    assert control.requested(fresh_store, "web", "r1") is not None
    assert call(f"{base_url}/api/control/stop?project=nope", "POST", {"X-Kestrel": "1"})[0] == 400
    assert call(f"{base_url}/api/control/stop?project=web", "POST")[0] == 403  # no custom header


# ───────────────────────────── the runner's guard ─────────────────────────────


def test_the_guard_halts_a_stopped_runner_session(home):
    st = Store(home / "data" / "events.db")
    try:
        started(st, "sandbox", "sess-1", T0)
        st.add_control("sandbox", reason="enough", ts=T0 + 1)
    finally:
        st.close()
    out = run_guard(home, {**pre("Bash", command="ls"), "session_id": "sess-1"})
    assert out["continue"] is False and "enough" in out["stopReason"]
