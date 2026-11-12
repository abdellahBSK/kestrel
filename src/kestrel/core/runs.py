"""Folding a run's events into what the dashboard shows: the run, its agents and their states, and the
activity feed. Pure functions over (ts, type, agent, data) rows, so they are easy to test.

The liveness rules are those of status.py: a run is live only while its events or heartbeats keep
coming; an agent is finished only if it said so after its last activity; everything else decays.
"""

from __future__ import annotations

from kestrel.core import status

DELEGATE_TOOLS = {"Agent", "Task", "delegate"}
FEED_LIMIT = 600


def _new_agent(aid: str, ts: float) -> dict:
    return {
        "id": aid,
        "role": aid.lower(),
        "description": "",
        "parent": None,
        "model": "",
        "first": ts,
        "last": ts,
        "finish": None,  # (status, ts) of its latest agent.finished
        "tokens": 0.0,
        "raw_tokens": {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0},
        "cost_usd": 0.0,
        "actions": 0,
        "errors": 0,
    }


def fold(rows: list[tuple], *, heartbeat: float | None, now: float, th: dict, weigh=None) -> dict:
    """rows: (ts, type, agent, data) in time order. weigh(model, data) → weighted tokens (optional)."""
    run = {
        "started": None,
        "last": None,
        "title": "",
        "source": "",
        "budget": 0,
        "timeout": None,  # the run's own heartbeat_timeout, if it declared one
        "finish": None,
        "summary": "",
        "error": "",
    }
    agents: dict[str, dict] = {}
    feed: list[dict] = []
    calls: dict[str, dict] = {}

    for ts, typ, aid, d in rows:
        run["started"] = ts if run["started"] is None else min(run["started"], ts)
        run["last"] = ts if run["last"] is None else max(run["last"], ts)
        if typ == "run.started":
            run["title"] = d.get("title") or run["title"]
            run["source"] = d.get("source") or run["source"]
            run["budget"] = d.get("budget", run["budget"])
            run["timeout"] = d.get("heartbeat_timeout", run["timeout"])
            continue
        if typ == "run.finished":
            run["finish"] = (d.get("status", "ok"), ts)
            run["summary"], run["error"] = d.get("summary", ""), d.get("error", "")
            continue
        if not aid:
            continue
        a = agents.get(aid) or agents.setdefault(aid, _new_agent(aid, ts))
        a["first"] = min(a["first"], ts)
        if typ == "agent.finished":
            a["finish"] = (d.get("status", "ok"), ts)
            continue
        a["last"] = max(a["last"], ts)
        if typ == "agent.started":
            a["role"] = d.get("role") or a["role"]
            a["description"] = d.get("description") or a["description"]
            a["parent"] = d.get("parent") or a["parent"]
            a["model"] = d.get("model") or a["model"]
        elif typ == "agent.message":
            feed.append({"ts": ts, "agent_id": aid, "kind": "say", "text": d.get("text", "")})
        elif typ == "agent.notice":
            level = d.get("level", "info")
            kind = {"warning": "budget", "critical": "halt"}.get(level, "notice")
            feed.append({"ts": ts, "agent_id": aid, "kind": kind, "text": d.get("text", "")})
        elif typ == "agent.tokens":
            raw = a["raw_tokens"]
            for k in raw:
                raw[k] += d.get(k, 0)
            a["model"] = a["model"] or d.get("model", "")
            a["tokens"] += weigh(d.get("model") or a["model"], d) if weigh else d.get("input", 0) + d.get("output", 0)
            a["cost_usd"] += d.get("cost_usd", 0.0)
        elif typ == "agent.action":
            call = d.get("call")
            item = calls.get(call) if call else None
            if item is None:
                tool = d.get("tool", "")
                item = {
                    "ts": ts,
                    "agent_id": aid,
                    "kind": "delegate" if tool in DELEGATE_TOOLS else "tool",
                    "tool": tool,
                    "title": d.get("summary"),
                    "text": d.get("detail") or d.get("summary") or tool,
                    "status": d.get("status", "ok"),
                }
                if d.get("result"):
                    item["result"] = d["result"]
                feed.append(item)
                a["actions"] += 1
                if call:
                    calls[call] = item
                if item["status"] == "error":
                    a["errors"] += 1
            else:  # a later update to the same call: its result
                was = item["status"]
                item["status"] = d.get("status", item["status"])
                if d.get("result"):
                    item["result"] = d["result"]
                if d.get("summary"):
                    item["title"] = d["summary"]
                if item["status"] == "error" and was != "error":
                    agents[item["agent_id"]]["errors"] += 1

    # ── states ──
    last_signal = max(x for x in (heartbeat, run["last"], 0.0) if x is not None)
    finished = run["finish"] is not None
    timeout = run["timeout"] or th["heartbeat_timeout"]
    live = not finished and bool(rows or heartbeat) and now - last_signal <= timeout
    run_state = "running" if live else ("finished" if finished else "lost")
    run_status = run["finish"][0] if finished else None

    def own_state(a: dict) -> str:
        fin = a["finish"]
        done = fin is not None and fin[1] >= a["last"] - 1e-6  # said so after its last activity
        failed = (done and fin[0] == "failed") or (
            not done and run_status == "failed" and a["parent"] not in agents  # a root agent of a failed run
        )
        return status.agent_state(
            finished=done and fin[0] != "failed", live=live, last_activity=a["last"], now=now, th=th, failed=failed
        )

    states = {aid: own_state(a) for aid, a in agents.items()}
    # A parent is "waiting" while any of its children are still at work.
    active_parents = {a["parent"] for aid, a in agents.items() if states[aid] in ("working", "idle") and a["parent"]}
    for aid in active_parents & set(agents):
        if states[aid] in ("working", "idle", "stale"):
            states[aid] = "waiting"

    roles = {aid: a["role"] for aid, a in agents.items()}
    for item in feed:
        item["agent"] = roles.get(item["agent_id"], item["agent_id"])

    return {
        "run": {
            "started": run["started"],
            "last": run["last"],
            "title": run["title"],
            "source": run["source"],
            "budget": run["budget"],
            "state": run_state,
            "status": run_status,
            "summary": run["summary"],
            "error": run["error"],
            "live": live,
            "heartbeat": heartbeat,
            "tokens": int(sum(a["tokens"] for a in agents.values())),
        },
        "agents": [{**a, "state": states[aid]} for aid, a in agents.items()],
        "feed": feed[-FEED_LIMIT:],
    }


def health(folded: dict | None) -> str:
    """A project's health from its latest run (see status.team_health)."""
    if folded is None:
        return "never"
    run = folded["run"]
    states = [a["state"] for a in folded["agents"]]
    if run["state"] == "finished" and run["status"] == "failed":
        return "failed"
    return status.team_health(run["state"] if run["state"] != "finished" else None, True, states)
