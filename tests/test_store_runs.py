"""The event store and folding a run's events into run, agents and feed."""

from __future__ import annotations

import pytest

from controlroom import runs
from controlroom.events import normalize
from controlroom.store import Store

TH = {"heartbeat_timeout": 45, "idle_after": 120, "stale_after": 600}
T = 1_794_473_380.0


def mk(typ, ts, agent=None, run="r1", project="shop", **data):
    return normalize(
        {"type": typ, "ts": ts, "project": project, "run": run, "agent": agent, "data": data}, now=T + 10_000
    )


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "events.db")
    yield s
    s.close()


def test_store_dedupes_by_id_and_keeps_only_the_latest_heartbeat(store):
    e = mk("agent.message", T, "lead", text="hi")
    assert store.add([e, e]) == (1, 1)
    assert store.add([{**e}]) == (0, 1)
    store.add([mk("run.heartbeat", T + 5), mk("run.heartbeat", T + 2)])
    assert store.heartbeat("shop", "r1") == T + 5
    assert store.run_events("shop", "r1") == [(T, "agent.message", "lead", {"text": "hi"})]


def test_store_lists_projects_runs_tokens_and_prs(store):
    store.add(
        [
            mk("run.started", T, run="old"),
            mk("run.started", T + 100, run="new"),
            mk("agent.tokens", T + 101, "dev", run="new", input=10, output=5, model="m"),
            mk("run.started", T + 50, project="api", run="a1"),
            normalize({"type": "pr.opened", "ts": T, "project": "shop", "data": {"number": 1, "title": "A"}}, now=T),
            normalize({"type": "pr.opened", "ts": T, "project": "shop", "data": {"number": 2, "title": "B"}}, now=T),
            normalize(
                {"type": "pr.closed", "ts": T + 1, "project": "shop", "data": {"number": 1, "merged": True}}, now=T
            ),
        ]
    )
    assert store.projects() == ["shop", "api"]
    assert [r["id"] for r in store.runs("shop")] == ["new", "old"]
    assert [(p, d["input"]) for p, _, d in store.tokens_since(T)] == [("shop", 10)]
    assert [p["number"] for p in store.pull_requests("shop")] == [2]
    v1 = store.run_version("shop", "new")
    store.add([mk("agent.message", T + 200, "dev", run="new", text="x")])
    assert store.run_version("shop", "new") != v1


def rows(*events):
    return [(e["ts"], e["type"], e["agent"], e["data"]) for e in events]


def test_fold_a_finished_run_with_a_cut_off_agent():
    f = runs.fold(
        rows(
            mk("run.started", T, title="Fix login"),
            mk("agent.started", T, "lead", role="lead", description="Team lead", model="opus"),
            mk("agent.started", T + 1, "dev", role="developer", parent="lead"),
            mk("agent.action", T + 2, "dev", tool="Bash", call="c1", detail="npm test", status="running"),
            mk("agent.action", T + 3, "dev", call="c1", status="error", result="1 failed"),
            mk("agent.tokens", T + 3, "dev", input=100, output=50),
            mk("agent.finished", T + 9, "lead"),
            mk("run.finished", T + 10),
        ),
        heartbeat=None,
        now=T + 5000,
        th=TH,
    )
    assert f["run"]["state"] == "finished" and f["run"]["status"] == "ok" and f["run"]["title"] == "Fix login"
    agents = {a["id"]: a for a in f["agents"]}
    assert agents["lead"]["state"] == "finished"
    assert agents["dev"]["state"] == "lost" and agents["dev"]["errors"] == 1 and agents["dev"]["actions"] == 1
    assert agents["dev"]["tokens"] == 150
    [action] = [x for x in f["feed"] if x["kind"] == "tool"]
    assert action["status"] == "error" and action["result"] == "1 failed" and action["agent"] == "developer"
    assert runs.health(f) == "incomplete"


def test_fold_a_live_run_where_the_lead_waits():
    f = runs.fold(
        rows(
            mk("agent.started", T, "lead", role="lead"),
            mk("agent.started", T + 1, "dev", role="developer", parent="lead"),
            mk("agent.action", T + 590, "dev", tool="Edit", detail="src/a.ts"),
        ),
        heartbeat=T + 595,
        now=T + 600,
        th=TH,
    )
    states = {a["id"]: a["state"] for a in f["agents"]}
    assert f["run"]["state"] == "running" and states == {"lead": "waiting", "dev": "working"}
    assert runs.health(f) == "running"


def test_fold_a_stuck_agent_and_a_lost_run():
    events = rows(mk("agent.started", T, "lead", role="lead"), mk("agent.action", T + 1, "lead", tool="Bash"))
    stuck = runs.fold(events, heartbeat=T + 1000, now=T + 1010, th=TH)
    assert stuck["agents"][0]["state"] == "stale" and runs.health(stuck) == "stale"
    lost = runs.fold(events, heartbeat=None, now=T + 1010, th=TH)
    assert lost["run"]["state"] == "lost" and lost["agents"][0]["state"] == "lost" and runs.health(lost) == "lost"


def test_fold_a_failed_run_and_an_agent_that_resumed_after_finishing():
    f = runs.fold(
        rows(
            mk("agent.started", T, "lead", role="lead"),
            mk("agent.finished", T + 1, "lead"),
            mk("agent.action", T + 2, "lead", tool="Bash"),  # it kept going after saying it was done
            mk("run.finished", T + 3, status="failed", error="boom"),
        ),
        heartbeat=None,
        now=T + 10,
        th=TH,
    )
    assert f["agents"][0]["state"] == "failed" and f["run"]["error"] == "boom" and runs.health(f) == "failed"
    assert runs.health(None) == "never"
