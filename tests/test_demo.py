"""The demo data: valid events, and every state the dashboard knows on show."""

from __future__ import annotations

import random
import time

from kestrel import demo
from kestrel.core import runs

TH = {"heartbeat_timeout": 45, "idle_after": 120, "stale_after": 600}


def test_demo_seed_shows_every_health_state(tmp_path, fresh_store):
    now = time.time()
    state = demo.seed(tmp_path, demo.sender(fresh_store), now, random.Random(7))
    # what the live loop would send next: heartbeats for the stuck and the live run
    demo.sender(fresh_store)(
        [
            {"type": "run.heartbeat", "project": state["stuck"][0], "run": state["stuck"][1]},
            {"type": "run.heartbeat", "project": "storefront", "run": state["live"]["id"]},
        ]
    )
    health = {}
    for name in demo.PROJECTS:
        latest = fresh_store.runs(name, 1)[0]["id"]
        f = runs.fold(
            fresh_store.run_events(name, latest), heartbeat=fresh_store.heartbeat(name, latest), now=now, th=TH
        )
        health[name] = runs.health(f)
    assert health == {
        "storefront": "running",
        "billing-api": "stale",
        "mobile-app": "incomplete",
        "data-pipeline": "failed",
        "auth-service": "lost",
        "docs-site": "idle",
    }
    assert (tmp_path / "teams" / "storefront" / "BACKLOG.md").exists()
    assert any(fresh_store.pull_requests(n) for n in demo.PROJECTS)


def test_every_outcome_builds_a_valid_run():
    rng = random.Random(1)
    for outcome in ("ok", "failed", "cutoff", "lost", "stuck"):
        items = demo.build_run("storefront", 3, outcome, rng, 42 if outcome == "ok" else None)
        offsets = [t for t, _ in items]
        assert offsets == sorted(offsets) and items[0][1]["type"] == "run.started"
