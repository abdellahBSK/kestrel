"""Alerts (spec 008): what needs the owner's attention, and telling them once.

Alerts are derived, not stored: every time the dashboard looks, `for_project` and `for_budget`
turn the current state into a list. Each alert has a stable id, so the dashboard can tell new
ones apart and the notifier sends each one once (to the desktop and to `[alerts] webhook`),
while `kestrel watch` runs.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from pathlib import Path

KINDS = ("stuck", "lost", "failed", "budget", "cap", "ask", "pr")
DEFAULTS = {"desktop": True, "webhook": "", "kinds": list(KINDS)}
RECENT = 24 * 3600  # failed and lost runs alert for a day, then they are history
ASKING = re.compile(r"(?i)permission|waiting for your|needs your")
LEVEL_ORDER = {"critical": 0, "warning": 1, "info": 2}


def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **(cfg.get("alerts") or {})}


def _alert(kind, level, project, title, detail="", *, key, ts, run=None, agent=None) -> dict:
    return {
        "id": f"{kind}:{project}:{key}",
        "kind": kind,
        "level": level,
        "project": project,
        "run": run,
        "agent": agent,
        "title": title,
        "detail": detail,
        "ts": ts,
    }


def for_project(
    project: str, folded: dict | None, run_id: str | None = None, *, now: float, prs=(), questions="", caps=()
) -> list[dict]:
    """Alerts about one project, from its latest run (folded by core.runs), its open pull requests,
    the questions its agents left, and its budget stops recorded today."""
    out: list[dict] = []
    if folded:
        run, rid = folded["run"], run_id or ""
        recent = run["last"] is not None and now - run["last"] < RECENT
        if run["state"] == "lost" and recent:
            out.append(
                _alert(
                    "lost",
                    "critical",
                    project,
                    f"{project}: run lost",
                    "It stopped reporting without finishing.",
                    key=rid,
                    ts=run["last"],
                    run=rid,
                )
            )
        if run["state"] == "finished" and run["status"] == "failed" and recent:
            out.append(
                _alert(
                    "failed",
                    "critical",
                    project,
                    f"{project}: run failed",
                    run["error"] or run["summary"],
                    key=rid,
                    ts=run["last"],
                    run=rid,
                )
            )
        if run["live"]:
            for a in folded["agents"]:
                if a["state"] == "stale":
                    out.append(
                        _alert(
                            "stuck",
                            "warning",
                            project,
                            f"{project}: {a['role']} may be stuck",
                            "No activity for over 10 minutes in a running run.",
                            key=f"{rid}:{a['id']}",
                            ts=a["last"],
                            run=rid,
                            agent=a["id"],
                        )
                    )
            asking = [e for e in folded["feed"] if e["kind"] == "budget" and ASKING.search(e.get("text", ""))]
            if asking and now - asking[-1]["ts"] < 15 * 60:
                e = asking[-1]
                out.append(
                    _alert(
                        "ask",
                        "warning",
                        project,
                        f"{project} is waiting for you",
                        e["text"],
                        key=f"{rid}:{int(e['ts'])}",
                        ts=e["ts"],
                        run=rid,
                    )
                )
    for c in caps:
        out.append(
            _alert(
                "cap",
                "warning",
                project,
                f"{project}: stopped by its budget",
                c["reason"],
                key=str(c["id"]),
                ts=c["ts"],
                run=c.get("run"),
            )
        )
    if questions:
        first = questions.strip().splitlines()[0].lstrip("-* ").strip()
        out.append(
            _alert(
                "ask",
                "info",
                project,
                f"{project}: questions for you",
                first,
                key=f"q:{abs(hash(questions)) % 10**8}",
                ts=now,
            )
        )
    for pr in prs:
        if pr.get("isDraft"):
            continue
        out.append(
            _alert(
                "pr",
                "info",
                project,
                f"{project}: pull request #{pr['number']} waiting for review",
                pr.get("title", ""),
                key=str(pr["number"]),
                ts=now,
            )
        )
    return out


def for_budget(used_today: float, daily: float, warn_at: float, day: str, now: float) -> list[dict]:
    """The agents' daily budget passing its warning share."""
    if not daily or used_today < daily * warn_at:
        return []
    level = "critical" if used_today >= daily else "warning"
    return [
        _alert(
            "budget",
            level,
            "*",
            f"Agents used {used_today / daily:.0%} of today's budget",
            f"{int(used_today):,} of {int(daily):,} tokens.",
            key=f"{day}:{level}",
            ts=now,
        )
    ]


def ordered(alerts: list[dict]) -> list[dict]:
    return sorted(alerts, key=lambda a: (LEVEL_ORDER[a["level"]], -(a["ts"] or 0)))


# ───────────────────────────── sending ─────────────────────────────


def webhook_body(alert: dict, name: str, url: str = "") -> dict:
    """JSON that Slack (`text`) and Discord (`content`) incoming webhooks both accept, plus the alert."""
    icon = {"critical": "🔴", "warning": "🟠", "info": "🔵"}[alert["level"]]
    text = f"{icon} {alert['title']}" + (f": {alert['detail']}" if alert["detail"] else "") + (f" {url}" if url else "")
    return {"text": text, "content": text, "username": name, "alert": alert}


def post_webhook(url: str, body: dict) -> bool:
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return 200 <= r.status < 300
    except Exception:
        return False


class Notifier:
    """Sends each new alert once while the dashboard runs. Alerts present when it starts are
    taken as already known, so starting the dashboard doesn't replay old news."""

    def __init__(self, current, cfg, state: Path, name: str, dashboard: str, notify, every: float = 20.0):
        self.current, self.cfg, self.state, self.name = current, cfg, state, name
        self.dashboard, self.notify, self.every = dashboard, notify, every
        self.stop = threading.Event()
        self.sent: list[str] = self._load()

    def _load(self) -> list[str]:
        try:
            return list(json.loads(self.state.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return []

    def _save(self) -> None:
        self.state.parent.mkdir(parents=True, exist_ok=True)
        self.state.write_text(json.dumps(self.sent[-2000:]), encoding="utf-8")

    def tick(self, first: bool = False) -> list[dict]:
        """Send what is new; returns what was sent."""
        s = settings(self.cfg())
        new = [a for a in self.current() if a["id"] not in self.sent]
        self.sent += [a["id"] for a in new]
        if new:
            self._save()
        if first:
            return []
        out = []
        for a in new:
            if a["kind"] not in s["kinds"]:
                continue
            url = f"{self.dashboard}/#/p/{a['project']}" if a["project"] != "*" else self.dashboard
            if s["desktop"]:
                self.notify(a["title"], a["detail"], url)
            if s["webhook"]:
                post_webhook(s["webhook"], webhook_body(a, self.name, url))
            out.append(a)
        return out

    def run(self) -> None:
        try:
            self.tick(first=True)
        except Exception:
            pass
        while not self.stop.wait(self.every):
            try:
                self.tick()
            except Exception:
                pass  # never take the dashboard down for a notification
            time.sleep(0)
