"""Retention (spec 008): old runs go, recent ones and open pull requests stay."""

from __future__ import annotations

import subprocess
import sys

from kestrel import retention
from kestrel.core.events import normalize
from kestrel.storage.store import Store

NOW = 1_800_000_000.0
DAY = retention.DAY


def add(st, run, last_ts, n=2):
    st.add(
        [
            normalize(
                {
                    "type": "agent.message",
                    "project": "p",
                    "run": run,
                    "agent": "a",
                    "ts": last_ts - i,
                    "data": {"text": "x"},
                },
                now=NOW,
            )
            for i in range(n)
        ]
    )


def test_old_runs_are_deleted_and_recent_ones_kept(fresh_store):
    add(fresh_store, "old", NOW - 40 * DAY, n=3)
    add(fresh_store, "spans", NOW - 5 * DAY)  # started long ago but active recently: kept whole
    fresh_store.add(
        [
            normalize(
                {
                    "type": "agent.message",
                    "project": "p",
                    "run": "spans",
                    "agent": "a",
                    "ts": NOW - 60 * DAY,
                    "data": {"text": "first"},
                },
                now=NOW,
            )
        ]
    )
    fresh_store.add(
        [normalize({"type": "pr.opened", "project": "p", "ts": NOW - 90 * DAY, "data": {"number": 3}}, now=NOW)]
    )
    fresh_store.add_control("p", reason="old stop", ts=NOW - 50 * DAY)

    assert retention.prune(fresh_store, 30, dry_run=True, now=NOW) == {"runs": 1, "events": 3, "dry_run": True}
    assert {r["id"] for r in fresh_store.runs("p")} == {"spans", "old"}  # a dry run deletes nothing

    assert retention.prune(fresh_store, 30, now=NOW) == {"runs": 1, "events": 3, "dry_run": False}
    assert [r["id"] for r in fresh_store.runs("p")] == ["spans"]
    assert len(fresh_store.run_events("p", "spans")) == 3
    assert fresh_store.pull_requests("p")  # open pull requests are not history
    assert fresh_store.controls_for("p") == []


def test_zero_keeps_everything(fresh_store):
    add(fresh_store, "old", NOW - 400 * DAY)
    assert retention.prune(fresh_store, 0, now=NOW)["runs"] == 0
    assert retention.apply_setting(fresh_store, {"storage": {"retention_days": 0}}) is None
    assert fresh_store.runs("p")


def test_prune_command(home):
    st = Store(home / "data" / "events.db")
    try:
        add(st, "ancient", 1_000_000_000.0)  # 2001
    finally:
        st.close()
    run = lambda *a: subprocess.run(  # noqa: E731
        [sys.executable, "-m", "kestrel", "--home", str(home), "prune", *a], capture_output=True, text=True, timeout=60
    )
    assert "Would delete 1 run" in run("--days", "30", "--dry-run").stdout
    assert "Deleted 1 run" in run("--days", "30").stdout
    r = run()
    assert r.returncode == 1 and "retention_days" in r.stdout
