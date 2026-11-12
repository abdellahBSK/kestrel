"""Alerts (spec 008): what gets raised, and each one sent once."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from kestrel import alerts
from kestrel.core import runs

NOW = 1_800_000_000.0
TH = {"heartbeat_timeout": 45, "idle_after": 120, "stale_after": 600}


def fold(rows, now=NOW, heartbeat=None, **run_data):
    return runs.fold(rows, heartbeat=heartbeat, now=now, th=TH)


def kinds(found):
    return sorted(a["kind"] for a in found)


def test_a_lost_run_is_critical_for_a_day():
    f = fold([(NOW - 600, "run.started", None, {}), (NOW - 500, "agent.action", "dev", {"tool": "Bash"})])
    [a] = alerts.for_project("shop", f, "r1", now=NOW)
    assert a["kind"] == "lost" and a["level"] == "critical" and a["id"] == "lost:shop:r1"
    assert alerts.for_project("shop", f, "r1", now=NOW + 2 * 86400) == []  # old news


def test_a_failed_run():
    f = fold(
        [(NOW - 60, "run.started", None, {}), (NOW - 50, "run.finished", None, {"status": "failed", "error": "boom"})]
    )
    [a] = alerts.for_project("shop", f, "r1", now=NOW)
    assert a["kind"] == "failed" and a["detail"] == "boom"


def test_a_stale_agent_in_a_live_run_may_be_stuck():
    rows = [
        (NOW - 900, "run.started", None, {}),
        (NOW - 900, "agent.started", "dev", {"role": "developer"}),
        (NOW - 890, "agent.action", "dev", {"tool": "Bash"}),
    ]
    f = fold(rows, heartbeat=NOW - 5)
    [a] = alerts.for_project("shop", f, "r1", now=NOW)
    assert a["kind"] == "stuck" and a["agent"] == "dev" and "developer" in a["title"]


def test_a_permission_prompt_means_it_waits_for_you():
    rows = [
        (NOW - 30, "run.started", None, {}),
        (NOW - 20, "agent.notice", "main", {"level": "warning", "text": "Claude needs your permission to use Bash"}),
    ]
    [a] = alerts.for_project("shop", fold(rows), "r1", now=NOW)
    assert a["kind"] == "ask" and "permission" in a["detail"]


def test_questions_pull_requests_and_budget_stops():
    found = alerts.for_project(
        "shop",
        None,
        now=NOW,
        prs=[{"number": 7, "title": "Fix login", "isDraft": False}, {"number": 8, "isDraft": True}],
        questions="- Should we drop IE11?\n- Which DB?",
        caps=[{"id": 3, "ts": NOW, "reason": "shop reached its daily budget", "run": None}],
    )
    assert kinds(found) == ["ask", "cap", "pr"]  # the draft PR isn't waiting for review yet
    assert next(a for a in found if a["kind"] == "ask")["detail"] == "Should we drop IE11?"


def test_the_daily_budget_warns_then_is_critical():
    assert alerts.for_budget(700, 1000, 0.8, "2026-11-12", NOW) == []
    [warn] = alerts.for_budget(850, 1000, 0.8, "2026-11-12", NOW)
    [over] = alerts.for_budget(1000, 1000, 0.8, "2026-11-12", NOW)
    assert (warn["level"], over["level"]) == ("warning", "critical") and warn["id"] != over["id"]
    assert alerts.for_budget(10**9, 0, 0.8, "2026-11-12", NOW) == []  # no budget, no alert


def test_critical_first():
    found = [
        {"level": "info", "ts": 3},
        {"level": "critical", "ts": 1},
        {"level": "warning", "ts": 2},
    ]
    assert [a["level"] for a in alerts.ordered(found)] == ["critical", "warning", "info"]


# ───────────────────────────── sending ─────────────────────────────


def test_the_webhook_body_suits_slack_and_discord():
    a = alerts._alert("failed", "critical", "shop", "shop: run failed", "boom", key="r1", ts=NOW)
    body = alerts.webhook_body(a, "Kestrel", "http://127.0.0.1:7777/#/p/shop")
    assert body["text"] == body["content"] and body["text"].startswith("🔴 shop: run failed: boom")
    assert body["alert"]["id"] == "failed:shop:r1"


class Hook(BaseHTTPRequestHandler):
    received: list = []

    def do_POST(self):
        Hook.received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(204)
        self.end_headers()

    def log_message(self, *a):
        pass


def test_each_new_alert_is_sent_once_and_old_ones_are_not_replayed(tmp_path):
    srv = HTTPServer(("127.0.0.1", 0), Hook)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    Hook.received.clear()
    current = [alerts._alert("lost", "critical", "shop", "shop: run lost", key="old", ts=NOW)]
    desktop = []
    n = alerts.Notifier(
        current=lambda: current,
        cfg=lambda: {
            "alerts": {"webhook": f"http://127.0.0.1:{srv.server_address[1]}/hook", "kinds": ["lost", "failed"]}
        },
        state=tmp_path / "sent.json",
        name="Kestrel",
        dashboard="http://127.0.0.1:7777",
        notify=lambda *a: desktop.append(a),
    )
    try:
        assert n.tick(first=True) == []  # what was already there when the dashboard started
        current.append(alerts._alert("failed", "critical", "shop", "shop: run failed", key="new", ts=NOW))
        current.append(alerts._alert("pr", "info", "shop", "shop: PR #1", key="1", ts=NOW))  # kind not wanted
        sent = n.tick()
        assert [a["id"] for a in sent] == ["failed:shop:new"]
        assert n.tick() == []  # once
        assert [d[0] for d in desktop] == ["shop: run failed"]
        assert desktop[0][2] == "http://127.0.0.1:7777/#/p/shop"
        assert [b["alert"]["id"] for b in Hook.received] == ["failed:shop:new"]
        again = alerts.Notifier(lambda: current, lambda: {}, tmp_path / "sent.json", "K", "", lambda *a: None)
        assert again.tick() == []  # remembered across restarts
    finally:
        srv.shutdown()


def test_desktop_notifications_can_be_turned_off(tmp_path):
    current: list = []
    desktop = []
    n = alerts.Notifier(
        lambda: current,
        lambda: {"alerts": {"desktop": False}},
        tmp_path / "s.json",
        "K",
        "",
        lambda *a: desktop.append(a),
    )
    n.tick(first=True)
    current.append(alerts._alert("failed", "critical", "shop", "x", key="1", ts=NOW))
    assert len(n.tick()) == 1 and desktop == []


def test_the_overview_lists_alerts(fresh_store, monkeypatch):
    import time

    from kestrel.api import server
    from kestrel.core.events import normalize

    monkeypatch.setattr(server.orchestrator, "open_prs", lambda t: [])
    server.CACHE.data.clear()
    t = time.time()
    fresh_store.add(
        [
            normalize({"type": "run.started", "project": "api", "run": "r1", "ts": t - 60}),
            normalize(
                {"type": "run.finished", "project": "api", "run": "r1", "ts": t - 30, "data": {"status": "failed"}}
            ),
        ]
    )
    monkeypatch.setattr(server, "store", lambda: fresh_store)
    found = server.overview()["alerts"]
    assert any(a["id"] == "failed:api:r1" and a["ts"].endswith("Z") for a in found)
