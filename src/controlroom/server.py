"""The Control Room — a local live dashboard of the King's agent teams.

  controlroom watch     → http://127.0.0.1:7777 (opens your browser)

Reads only local files (team folders, Claude Code session logs, state/) plus your own `gh`
for PRs. Listens on 127.0.0.1 only. Buttons require a same-origin request with a custom
header, so other websites can't trigger them.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from controlroom import NAME, meter, paths
from controlroom.runner import orchestrator as kingdom

HQ = meter.HQ
TEAMS = HQ / "teams"
PORT = 7777
HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
ROLE_ORDER = ["lead", "developer", "tester", "qa", "security", "optimizer"]


# ───────────────────────────── caching ─────────────────────────────


class Cache:
    def __init__(self):
        self.data: dict = {}
        self.lock = threading.Lock()

    def get(self, key, ttl, fn):
        with self.lock:
            hit = self.data.get(key)
            if hit and time.time() - hit[0] < ttl:
                return hit[1]
        val = fn()
        with self.lock:
            self.data[key] = (time.time(), val)
        return val

    def drop(self, key):
        with self.lock:
            self.data.pop(key, None)


CACHE = Cache()


def cfg() -> dict:
    return CACHE.get("cfg", 5, meter.load_config)


# ───────────────────────────── sessions ─────────────────────────────


def sessions(team: str, limit: int = 12) -> list[dict]:
    """Agent-team sessions for a team, newest first."""
    out = []
    for d in meter.team_dirs(team):
        for f in d.glob("*.jsonl"):
            out.append({"id": f.stem, "path": f, "mtime": f.stat().st_mtime})
    out.sort(key=lambda s: s["mtime"], reverse=True)
    return out[:limit]


def short(text: str, n: int = 140) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= n else text[: n - 1] + "…"


def rel(path: str, team: str) -> str:
    p = str(path).replace("\\", "/")
    root = (TEAMS / team).as_posix()
    i = p.lower().find(root.lower())
    return p[i + len(root) + 1 :] if i != -1 else p


def summarize(tool: str, inp: dict, team: str) -> str:
    if tool in ("Bash", "PowerShell"):
        return short(inp.get("command", ""), 160)
    if tool in ("Read", "Write", "Edit", "MultiEdit", "NotebookEdit"):
        return rel(inp.get("file_path") or inp.get("notebook_path") or "", team)
    if tool in ("Grep", "Glob"):
        return short(f"{inp.get('pattern', '')}  {rel(inp.get('path', ''), team)}".strip(), 120)
    if tool in ("Agent", "Task"):
        return f"→ {inp.get('subagent_type', '?')}: {short(inp.get('description', ''), 100)}"
    if tool == "TodoWrite":
        todos = inp.get("todos") or []
        doing = [t.get("content") for t in todos if t.get("status") == "in_progress"]
        return short("plan: " + (doing[0] if doing else f"{len(todos)} items"), 120)
    return short(json.dumps(inp), 120)


def result_text(content) -> str:
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content if isinstance(c, dict))
    return str(content or "")


def parse_log(path: Path, agent: str, team: str) -> tuple[list[dict], dict]:
    """Events and token usage from one transcript file."""
    events, by_id = [], {}
    usage, seen = {"tokens": 0.0, "calls": 0}, set()
    w = cfg()["budget"]
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return [], usage
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        ts = d.get("timestamp")
        typ = d.get("type")
        msg = d.get("message") if isinstance(d.get("message"), dict) else {}
        if typ == "assistant":
            u = msg.get("usage")
            key = (msg.get("id"), d.get("requestId"))
            if u and key not in seen:
                seen.add(key)
                f = meter.model_factor(msg.get("model", ""))
                usage["tokens"] += f * (
                    (u.get("input_tokens") or 0) * w.get("weight_input", 1)
                    + (u.get("output_tokens") or 0) * w.get("weight_output", 1)
                    + (u.get("cache_creation_input_tokens") or 0) * w.get("weight_cache_write", 1)
                    + (u.get("cache_read_input_tokens") or 0) * w.get("weight_cache_read", 0)
                )
                usage["calls"] += 1
                usage["model"] = msg.get("model", usage.get("model"))
            for c in msg.get("content") or []:
                if not isinstance(c, dict):
                    continue
                if c.get("type") == "text" and c.get("text", "").strip():
                    events.append({"ts": ts, "agent": agent, "kind": "say", "text": short(c["text"], 300)})
                elif c.get("type") == "tool_use":
                    ev = {
                        "ts": ts,
                        "agent": agent,
                        "kind": "tool",
                        "tool": c.get("name"),
                        "text": summarize(c.get("name", ""), c.get("input") or {}, team),
                        "status": "running",
                    }
                    if c.get("name") in ("Agent", "Task"):
                        ev["kind"] = "delegate"
                    by_id[c.get("id")] = ev
                    events.append(ev)
        elif typ == "user":
            for c in msg.get("content") or [] if isinstance(msg.get("content"), list) else []:
                if isinstance(c, dict) and c.get("type") == "tool_result":
                    ev = by_id.get(c.get("tool_use_id"))
                    if not ev:
                        continue
                    txt = result_text(c.get("content"))
                    if "[Kingdom guard]" in txt:
                        ev["status"], ev["result"] = "blocked", short(txt.split("[Kingdom guard]", 1)[1], 200)
                    elif c.get("is_error"):
                        ev["status"], ev["result"] = "error", short(txt, 200)
                    else:
                        ev["status"], ev["result"] = "ok", short(txt[-220:], 220) if txt else ""
        elif typ == "attachment":
            a = d.get("attachment") or {}
            if a.get("type") == "hook_success":
                out = str(a.get("stdout", ""))
                if "BUDGET WARNING" in out:
                    if any(e["kind"] == "budget" for e in events):
                        continue  # the hook repeats it after every action; show the first one only
                    m = re.search(r"BUDGET WARNING: ([^.]*)", out)
                    events.append(
                        {
                            "ts": ts,
                            "agent": agent,
                            "kind": "budget",
                            "text": "Budget warning: " + (m.group(1) if m else "80% reached"),
                        }
                    )
                elif "allowance exhausted" in out or "STOP flag" in out:
                    events.append(
                        {
                            "ts": ts,
                            "agent": agent,
                            "kind": "halt",
                            "text": "Stopped by the guard: "
                            + ("token allowance exhausted" if "allowance" in out else "STOP flag"),
                        }
                    )
    return events, usage


def session_detail(team: str, sid: str | None) -> dict:
    ss = sessions(team)
    s = next((x for x in ss if x["id"] == sid), ss[0] if ss else None)
    if not s:
        return {"team": team, "session": None, "sessions": [], "events": [], "agents": []}
    cur = current_run()
    live = bool(cur and cur.get("session") == s["id"])

    def build():
        events, lead_usage = parse_log(s["path"], "lead", team)
        agents = [
            {
                "role": "lead",
                "description": "Team lead",
                "finished": not live,
                "tokens": int(lead_usage["tokens"]),
                "actions": sum(e["kind"] in ("tool", "delegate") for e in events),
                "model": lead_usage.get("model", ""),
            }
        ]
        subdir = s["path"].with_suffix("")
        for f in sorted((subdir / "subagents").glob("*.jsonl")) if (subdir / "subagents").exists() else []:
            meta = {}
            mf = f.with_suffix(".meta.json")
            if mf.exists():
                try:
                    meta = json.loads(mf.read_text(encoding="utf-8"))
                except ValueError:
                    pass
            role = meta.get("agentType", "subagent")
            ev, us = parse_log(f, role, team)
            events.extend(ev)
            times = [e["ts"] for e in ev if e.get("ts")]
            agents.append(
                {
                    "role": role,
                    "description": meta.get("description", ""),
                    "finished": bool(meta.get("finished")),
                    "tokens": int(us["tokens"]),
                    "actions": sum(e["kind"] == "tool" for e in ev),
                    "model": us.get("model", ""),
                    "start": min(times) if times else None,
                    "end": max(times) if times else None,
                }
            )
        events.sort(key=lambda e: e.get("ts") or "")
        return {"events": events[-600:], "agents": agents}

    data = CACHE.get(f"sess:{s['id']}:{s['mtime']}", 2 if live else 300, build)
    return {
        "team": team,
        "session": s["id"],
        "live": live,
        "sessions": [
            {"id": x["id"], "when": dt.datetime.fromtimestamp(x["mtime"]).strftime("%a %d %b %H:%M")} for x in ss
        ],
        **data,
    }


# ───────────────────────────── overview ─────────────────────────────


def current_run() -> dict | None:
    f = HQ / "state" / "current.json"
    lock = HQ / "state" / "run.lock"
    if f.exists() and lock.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            return None
    return None


def backlog_counts(team: str) -> dict:
    f = TEAMS / team / "BACKLOG.md"
    text = f.read_text(encoding="utf-8") if f.exists() else ""
    c = {
        k: len(re.findall(rf"^\s*-\s*\[{re.escape(m)}\]", text, re.M))
        for k, m in (("todo", " "), ("doing", "~"), ("review", "r"), ("done", "x"), ("blocked", "!"))
    }
    return c


def questions(team: str) -> str:
    reps = sorted((TEAMS / team / "reports").glob("20*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    for rep in reps[:1]:
        m = re.search(r"## Questions for the King\s*\n(.*?)(\n## |\Z)", rep.read_text(encoding="utf-8"), re.S)
        if m and m.group(1).strip() and not m.group(1).strip().lower().startswith("- none"):
            return m.group(1).strip()
    return ""


def prs_all() -> dict:
    def fetch():
        out = {}
        for team, t in cfg()["teams"].items():
            try:
                out[team] = kingdom.open_prs(t)
            except Exception:
                out[team] = []
        return out

    return CACHE.get("prs", 90, fetch)


def previews(team: str) -> list[str]:
    d = TEAMS / team / "previews"
    files = sorted(d.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True) if d.exists() else []
    return [f.name for f in files[:8]]


def overview() -> dict:
    c = cfg()
    cur = current_run()
    pool, s = CACHE.get("budget", 20, lambda: kingdom.pool_today(c))
    today = kingdom.DAYS[dt.date.today().weekday()]
    prs = prs_all()
    teams = []
    for team, t in c["teams"].items():
        ss = sessions(team, 1)
        last = ss[0] if ss else None
        running = bool(cur and cur.get("team") == team)
        now = None
        if running and last:
            det = session_detail(team, last["id"])
            acts = [e for e in det["events"] if e["kind"] in ("tool", "delegate", "say")]
            if acts:
                now = {"agent": acts[-1]["agent"], "text": acts[-1]["text"], "ts": acts[-1]["ts"]}
        used = 0
        if running:
            used = meter.team_used_since(team, dt.datetime.fromtimestamp(cur["since"]).astimezone(), c)
        teams.append(
            {
                "team": team,
                "title": t.get("title", ""),
                "key": t.get("key", ""),
                "mode": t.get("mode", "build"),
                "pr_mode": t.get("pr_mode", "none"),
                "enabled": t.get("enabled", True),
                "scheduled_today": team in c["schedule"].get(today, []),
                "running": running,
                "now": now,
                "allowance": cur.get("allowance") if running else 0,
                "used": used,
                "last_run": dt.datetime.fromtimestamp(last["mtime"]).strftime("%a %d %b %H:%M") if last else None,
                "today_tokens": s["today"].get(f"team:{team}", 0),
                "week_tokens": s["week"].get(f"team:{team}", 0),
                "backlog": backlog_counts(team),
                "prs": prs.get(team, []),
                "questions": questions(team),
                "previews": previews(team),
            }
        )
    b = c["budget"]
    return {
        "now": dt.datetime.now().strftime("%H:%M:%S"),
        "stop": (HQ / "STOP").exists(),
        "running": cur,
        "budget": {
            "agents_today": s["today"]["agents"],
            "agents_daily": b["agents_daily"],
            "agents_week": s["week"]["agents"],
            "agents_weekly": b["agents_weekly"],
            "you_today": s["today"]["personal"],
            "you_week": s["week"]["personal"],
            "pool": pool,
            "warn_at": b.get("warn_at", 0.8),
        },
        "schedule": {d: c["schedule"].get(d, []) for d in kingdom.DAYS},
        "today": today,
        "teams": teams,
    }


# ───────────────────────────── actions ─────────────────────────────


def spawn(args: list[str], window: bool) -> None:
    flags = subprocess.CREATE_NEW_CONSOLE if window else (subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
    env = {
        **os.environ,
        paths.HOME_ENV: str(HQ),
        "PYTHONPATH": os.pathsep.join(filter(None, [str(paths.PKG.parent), os.environ.get("PYTHONPATH")])),
    }
    subprocess.Popen(
        [sys.executable, "-m", "controlroom", *args],
        cwd=HQ,
        creationflags=flags,
        env=env,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=None if window else subprocess.DEVNULL,
        stderr=None if window else subprocess.DEVNULL,
    )


def act(path: str, q: dict) -> dict:
    c = cfg()
    if path == "/api/stop":
        (HQ / "STOP").write_text("Raised from the Control Room\n")
        kingdom.log("STOP flag raised from the Control Room.")
        return {"ok": True, "msg": "STOP raised: agents halt at their next action."}
    if path == "/api/resume":
        (HQ / "STOP").unlink(missing_ok=True)
        kingdom.log("STOP flag lowered from the Control Room.")
        return {"ok": True, "msg": "STOP lowered."}
    team = (q.get("team") or [""])[0]
    if team not in c["teams"]:
        return {"ok": False, "msg": "unknown team"}
    if path == "/api/run":
        if current_run():
            return {"ok": False, "msg": "A run is already in progress."}
        spawn(["run", "--team", team, "--force"], window=False)
        return {"ok": True, "msg": f"{team} started. It will appear as running in a few seconds."}
    if path == "/api/demo":
        pr = (q.get("pr") or [""])[0]
        spawn(["demo", team] + ([pr] if pr.isdigit() else []), window=True)
        return {"ok": True, "msg": f"Demo of {team}{' #' + pr if pr else ''} starting in a new window."}
    return {"ok": False, "msg": "unknown action"}


# ───────────────────────────── http ─────────────────────────────


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _ok_host(self) -> bool:
        return self.headers.get("Host", "") in HOSTS

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def do_GET(self):
        if not self._ok_host():
            return self._send(403, b"forbidden", "text/plain")
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                page = (paths.STATIC / "index.html").read_text(encoding="utf-8").replace("__APP_NAME__", NAME)
                return self._send(200, page.encode(), "text/html; charset=utf-8")
            if u.path == "/api/overview":
                return self._json(overview())
            if u.path == "/api/session":
                team = (q.get("team") or [""])[0]
                if team not in cfg()["teams"]:
                    return self._json({"error": "unknown team"}, 404)
                return self._json(session_detail(team, (q.get("id") or [None])[0]))
            m = re.match(r"^/previews/([a-z0-9-]+)/([A-Za-z0-9._-]+\.png)$", u.path)
            if m and m.group(1) in cfg()["teams"]:
                f = (TEAMS / m.group(1) / "previews" / m.group(2)).resolve()
                if f.is_file() and f.parent == (TEAMS / m.group(1) / "previews").resolve():
                    return self._send(200, f.read_bytes(), "image/png")
            return self._send(404, b"not found", "text/plain")
        except Exception as e:  # keep serving
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_POST(self):
        origin = self.headers.get("Origin", "")
        if (
            not self._ok_host()
            or self.headers.get("X-Kingdom") != "1"
            or (origin and urlparse(origin).netloc not in HOSTS)
        ):
            return self._send(403, b"forbidden", "text/plain")
        u = urlparse(self.path)
        res = act(u.path, parse_qs(u.query))
        CACHE.drop("prs")
        return self._json(res, 200 if res.get("ok") else 400)


def serve(open_browser: bool = True) -> None:
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"{NAME}: {url}   (Ctrl+C to close)")
    if open_browser:
        import webbrowser

        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    serve("--no-browser" not in sys.argv)
