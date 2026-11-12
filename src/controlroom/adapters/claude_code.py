"""Claude Code adapter for the scheduled runner: the runner's teams, as events.

Reads, for every team in the config:
  ~/.claude/projects/<home/teams/<team>>/<session>.jsonl         the lead's transcript
  .../<session>/subagents/agent-*.jsonl and agent-*.meta.json     each subagent it started
  <home>/state/current.json and state/run-<date>.json             run liveness and outcome

Every event gets a deterministic id derived from where it came from, so syncing again only adds
what is new. The dashboard calls sync() every couple of seconds while it is open.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path

from controlroom import meter, status
from controlroom.events import EventError, normalize

SOURCE = "claude-code"
GUARD_MARK = "[Kingdom guard]"
RESULT_STATUS = {  # the runner's final status → run.finished status
    "ok": "ok",
    "budget-stop": "stopped",
    "lost": "interrupted",
    "error": "failed",
    "usage-limit": "failed",
    "not-logged-in": "failed",
}

_SEEN: dict[str, tuple] = {}  # file signature per session, to skip unchanged sessions


def _short(text: str, n: int) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _rel(path: str, team_dir: str) -> str:
    p = str(path).replace("\\", "/")
    i = p.lower().find(team_dir.lower())
    return p[i + len(team_dir) + 1 :] if i != -1 else p


def describe(tool: str, inp: dict, team_dir: str) -> str:
    """What a tool call did, in a form the dashboard turns into a readable line."""
    if tool in ("Bash", "PowerShell"):
        return str(inp.get("command", ""))
    if tool in ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit"):
        return _rel(inp.get("file_path") or inp.get("notebook_path") or "", team_dir)
    if tool in ("Grep", "Glob"):
        return _short(f"{inp.get('pattern', '')}  {_rel(inp.get('path', ''), team_dir)}".strip(), 200)
    if tool in ("Agent", "Task"):
        return f"→ {inp.get('subagent_type', '?')}: {_short(inp.get('description', ''), 100)}"
    if tool == "TodoWrite":
        todos = inp.get("todos") or []
        doing = [t.get("content") for t in todos if t.get("status") == "in_progress"]
        return _short("plan: " + (doing[0] if doing else f"{len(todos)} items"), 120)
    return _short(json.dumps(inp), 200)


def _result_text(content) -> str:
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return str(content or "")


def _epoch(ts) -> float | None:
    try:
        return dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def transcript_events(path: Path, project: str, run: str, agent: str, team_dir: str) -> tuple[list[dict], dict]:
    """Events from one transcript, plus {first, last, model, clean_end}."""
    info = {"first": None, "last": None, "model": "", "clean_end": False}
    out: list[dict] = []
    seen_usage: set = set()
    tools: dict[str, str] = {}
    last_turn: tuple = (None, None)
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return out, info
    for n, line in enumerate(lines):
        try:
            d = json.loads(line)
        except ValueError:
            continue
        ts = _epoch(d.get("timestamp")) if d.get("timestamp") else None
        if ts is None:
            continue
        info["first"] = ts if info["first"] is None else min(info["first"], ts)
        info["last"] = ts if info["last"] is None else max(info["last"], ts)
        typ = d.get("type")
        msg = d.get("message") if isinstance(d.get("message"), dict) else {}
        if typ in ("assistant", "user"):
            last_turn = (typ, msg.get("stop_reason"))
        base = {"project": project, "run": run, "agent": agent, "ts": ts}
        if typ == "assistant":
            info["model"] = msg.get("model") or info["model"]
            u = msg.get("usage")
            key = (msg.get("id"), d.get("requestId"))
            if u and key not in seen_usage:  # Claude Code repeats a message once per content block
                seen_usage.add(key)
                out.append(
                    {
                        **base,
                        "id": f"cc:{run}:{agent}:tok:{key[0]}:{key[1]}",
                        "type": "agent.tokens",
                        "data": {
                            "input": u.get("input_tokens") or 0,
                            "output": u.get("output_tokens") or 0,
                            "cache_write": u.get("cache_creation_input_tokens") or 0,
                            "cache_read": u.get("cache_read_input_tokens") or 0,
                            "model": msg.get("model", ""),
                        },
                    }
                )
            for i, c in enumerate(msg.get("content") or []):
                if not isinstance(c, dict):
                    continue
                eid = f"cc:{run}:{agent}:{n}:{i}"
                if c.get("type") == "text" and c.get("text", "").strip():
                    out.append({**base, "id": eid, "type": "agent.message", "data": {"text": _short(c["text"], 600)}})
                elif c.get("type") == "tool_use":
                    tool = c.get("name") or "tool"
                    tools[c.get("id", "")] = tool
                    out.append(
                        {
                            **base,
                            "id": eid,
                            "type": "agent.action",
                            "data": {
                                "tool": tool,
                                "call": c.get("id"),
                                "detail": describe(tool, c.get("input") or {}, team_dir),
                                "status": "running",
                            },
                        }
                    )
        elif typ == "user" and isinstance(msg.get("content"), list):
            for i, c in enumerate(msg["content"]):
                if not (isinstance(c, dict) and c.get("type") == "tool_result" and c.get("tool_use_id")):
                    continue
                txt = _result_text(c.get("content"))
                if GUARD_MARK in txt:
                    st, res = "blocked", _short(txt.split(GUARD_MARK, 1)[1], 300)
                elif c.get("is_error"):
                    st, res = "error", _short(txt, 300)
                else:
                    st, res = "ok", _short(txt[-300:], 300)
                data = {"call": c["tool_use_id"], "status": st, "result": res}
                if c["tool_use_id"] in tools:
                    data["tool"] = tools[c["tool_use_id"]]
                out.append({**base, "id": f"cc:{run}:{agent}:{n}:r{i}", "type": "agent.action", "data": data})
        elif typ == "attachment":
            a = d.get("attachment") or {}
            hook_out = str(a.get("stdout", "")) if a.get("type") == "hook_success" else ""
            if "BUDGET WARNING" in hook_out:  # repeated after every action: one fixed id keeps the first
                text = hook_out.split("BUDGET WARNING:", 1)[1].split(".")[0].strip()
                out.append(
                    {
                        **base,
                        "id": f"cc:{run}:{agent}:budget-warning",
                        "type": "agent.notice",
                        "data": {"level": "warning", "text": f"Budget warning: {text or '80% reached'}"},
                    }
                )
            elif "allowance exhausted" in hook_out or "STOP flag" in hook_out:
                why = "token allowance exhausted" if "allowance" in hook_out else "STOP flag"
                out.append(
                    {
                        **base,
                        "id": f"cc:{run}:{agent}:{n}:halt",
                        "type": "agent.notice",
                        "data": {"level": "critical", "text": f"Stopped by the guard: {why}"},
                    }
                )
    info["clean_end"] = last_turn == ("assistant", "end_turn")
    return out, info


def session_events(
    team: str,
    lead: Path,
    final_status: str | None,
    current: dict | None,
    now: float,
    th: dict,
) -> list[dict]:
    """All events for one runner session (= one run)."""
    sid, team_dir = lead.stem, (meter.HQ / "teams" / team).as_posix()
    live = bool(current and current.get("state") == "running")
    out, info = transcript_events(lead, team, sid, "lead", team_dir)
    if info["first"] is None:
        return []
    base = {"project": team, "run": sid}
    started = {"source": SOURCE}
    if current and current.get("allowance"):
        started["budget"] = int(current["allowance"])
    out.insert(0, {**base, "id": f"cc:{sid}:run.started", "type": "run.started", "ts": info["first"], "data": started})
    out.insert(
        1,
        {
            **base,
            "id": f"cc:{sid}:lead:started",
            "type": "agent.started",
            "agent": "lead",
            "ts": info["first"],
            "data": {"role": "lead", "description": "Team lead", "model": info["model"]},
        },
    )
    last = info["last"]
    if info["clean_end"] and not live:
        out.append(
            {**base, "id": f"cc:{sid}:lead:finished:{int(last)}", "type": "agent.finished", "agent": "lead", "ts": last}
        )
    folder = lead.with_suffix("") / "subagents"
    for f in sorted(folder.glob("*.jsonl")) if folder.is_dir() else []:
        aid = f.stem
        meta = status.read_json(f.with_suffix(".meta.json")) or {}
        evs, sub = transcript_events(f, team, sid, aid, team_dir)
        if sub["first"] is None:
            continue
        last = max(last, sub["last"])
        out.append(
            {
                **base,
                "id": f"cc:{sid}:{aid}:started",
                "type": "agent.started",
                "agent": aid,
                "ts": sub["first"],
                "data": {
                    "role": meta.get("agentType") or "subagent",
                    "description": meta.get("description", ""),
                    "parent": "lead",
                    "model": sub["model"],
                },
            }
        )
        out += evs
        if meta.get("finished"):
            out.append(
                {**base, "id": f"cc:{sid}:{aid}:finished", "type": "agent.finished", "agent": aid, "ts": sub["last"]}
            )
    outcome = RESULT_STATUS.get(final_status or "")
    if outcome is None and info["clean_end"] and not live and now - last > th["heartbeat_timeout"]:
        outcome = "ok"  # an older run with no recorded result whose lead signed off cleanly
    if outcome:
        out.append(
            {
                **base,
                "id": f"cc:{sid}:run.finished:{outcome}",
                "type": "run.finished",
                "ts": last,
                "data": {"status": outcome},
            }
        )
    return out


def _stat(p: Path) -> tuple:
    try:
        s = p.stat()
        return s.st_mtime, s.st_size
    except OSError:
        return 0.0, 0


def sync(store, cfg: dict, home: Path, now: float | None = None) -> int:
    """Bring the store up to date with the runner's teams. Returns how many events were added."""
    now = time.time() if now is None else now
    th = status.thresholds(cfg)
    state_dir = home / "state"
    current = status.run_state(state_dir, th["heartbeat_timeout"], now)
    results = status.run_results(state_dir)
    added = 0
    for team in cfg.get("teams", {}):
        for folder in meter.team_dirs(team):
            for lead in sorted(folder.glob("*.jsonl")):
                sid = lead.stem
                cur = current if current and current.get("session") == sid else None
                subs = sorted((lead.with_suffix("") / "subagents").glob("*"))
                signature = (
                    _stat(lead),
                    tuple(_stat(s) for s in subs),
                    results.get(sid),
                    cur and cur["state"],
                    now - _stat(lead)[0] > th["heartbeat_timeout"],
                )
                key = f"{store.path}|{lead}"
                if _SEEN.get(key) == signature:
                    continue
                good = []
                for e in session_events(team, lead, results.get(sid), cur, now, th):
                    try:
                        good.append(normalize(e, now))
                    except EventError:
                        continue  # one odd record never blocks the rest
                added += store.add(good)[0]
                _SEEN[key] = signature
    if current and current["state"] == "running" and current.get("team") and current.get("session"):
        # run_state just confirmed the run is alive (fresh heartbeat or its process): say so.
        store.add([normalize({"type": "run.heartbeat", "project": current["team"], "run": current["session"]}, now)])
    return added
