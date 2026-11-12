"""The dashboard server.

  kestrel watch     → http://127.0.0.1:7777 (opens your browser)

Everything it shows comes from the event store (store.py): events any agent reports through
POST /v1/events, `kestrel emit` or the Python client, plus the Claude Code runner's teams,
synced in by adapters/claude_code.py. It also reads team folders and your own `gh` for PRs.

Listens on 127.0.0.1 only. Ingest needs the bearer token from <home>/ingest.token; dashboard
buttons need a same-origin request with a custom header. No telemetry.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from kestrel import NAME, __version__, meter, paths
from kestrel.adapters import claude_code
from kestrel.api import ingest
from kestrel.core import runs, status
from kestrel.core.events import EventError
from kestrel.runner import orchestrator, system
from kestrel.storage.store import open_store

HQ = meter.HQ
TEAMS = HQ / "teams"
PORT = 7777
HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}


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


# ───────────────────────────── the store ─────────────────────────────

DEMO = os.environ.get("KESTREL_DEMO") == "1"  # demo mode: actions are disabled


def iso(epoch: float | None) -> str | None:
    """Every time the API returns is UTC; the browser formats it."""
    return status.iso(epoch) if epoch is not None else None


def store():
    return open_store()


def sync() -> None:
    """Pull the runner's Claude Code teams into the store (at most every 2 s)."""
    c = cfg()
    if c["teams"] and not DEMO:
        CACHE.get("sync", 2, lambda: claude_code.sync(store(), c, HQ))


def runner_run() -> dict | None:
    """The scheduled runner's own run marker, live or lost (see status.run_state)."""
    return CACHE.get("runner", 1, lambda: status.run_state(HQ / "state", status.thresholds(cfg())["heartbeat_timeout"]))


def weigh(model: str, d: dict) -> float:
    """Tokens in the budget unit: per-type weights x the model's price relative to the reference model."""
    b = cfg()["budget"]
    return meter.model_factor(model or "") * (
        d.get("input", 0) * b.get("weight_input", 1.0)
        + d.get("output", 0) * b.get("weight_output", 1.0)
        + d.get("cache_write", 0) * b.get("weight_cache_write", 1.0)
        + d.get("cache_read", 0) * b.get("weight_cache_read", 0.0)
    )


def folded(project: str, run_id: str) -> dict:
    """A run folded into run, agents and feed; cached until it changes (states refresh every 2 s)."""
    st = store()
    version = st.run_version(project, run_id)
    th = status.thresholds(cfg())

    def build() -> dict:
        return runs.fold(
            st.run_events(project, run_id),
            heartbeat=st.heartbeat(project, run_id),
            now=time.time(),
            th=th,
            weigh=weigh,
        )

    return CACHE.get(f"fold:{project}:{run_id}:{version}:{int(time.time() // 2)}", 2, build)


def known(project: str) -> bool:
    c = cfg()
    return project in c["teams"] or project in c.get("projects", {}) or project in store().projects()


def agent_public(a: dict) -> dict:
    return {
        "id": a["id"],
        "role": a["role"],
        "description": a["description"],
        "parent": a["parent"],
        "model": a["model"],
        "tokens": int(a["tokens"]),
        "raw_tokens": a["raw_tokens"],
        "cost_usd": round(a["cost_usd"], 4),
        "actions": a["actions"],
        "errors": a["errors"],
        "start": iso(a["first"]),
        "end": iso(a["last"]),
        "last_activity": iso(a["last"]),
        "state": a["state"],
        "finished": a["state"] == "finished",
    }


def feed_public(e: dict) -> dict:
    out = {k: v for k, v in e.items() if k != "ts"}
    out["ts"] = iso(e["ts"])
    return out


def run_public(f: dict) -> dict:
    r = f["run"]
    return {
        "title": r["title"],
        "source": r["source"],
        "state": r["state"],
        "status": r["status"],
        "summary": r["summary"],
        "error": r["error"],
        "budget": r["budget"],
        "tokens": r["tokens"],
        "started_at": iso(r["started"]),
        "last_activity": iso(r["last"]),
    }


def session_detail(team: str, run_id: str | None) -> dict:
    sync()
    rs = store().runs(team, 20)
    if not rs:
        return {"team": team, "session": None, "live": False, "sessions": [], "events": [], "agents": []}
    r = next((x for x in rs if x["id"] == run_id), rs[0])
    f = folded(team, r["id"])
    agents = sorted(f["agents"], key=lambda a: (a["parent"] is not None, a["first"]))
    return {
        "team": team,
        "session": r["id"],
        "live": f["run"]["live"],
        "started_at": iso(r["started"]),
        "run": run_public(f),
        "sessions": [{"id": x["id"], "started_at": iso(x["started"]), "updated_at": iso(x["last"])} for x in rs],
        "events": [feed_public(e) for e in f["feed"]],
        "agents": [agent_public(a) for a in agents],
    }


# ───────────────────────────── overview ─────────────────────────────


def backlog_counts(team: str) -> dict:
    f = TEAMS / team / "BACKLOG.md"
    text = f.read_text(encoding="utf-8") if f.exists() else ""
    c = {
        k: len(re.findall(rf"^\s*-\s*\[{re.escape(m)}\]", text, re.M))
        for k, m in (("todo", " "), ("doing", "~"), ("review", "r"), ("done", "x"), ("blocked", "!"))
    }
    return c


def questions(team: str) -> str:
    folder = TEAMS / team / "reports"
    reps = sorted(folder.glob("20*.md"), key=lambda p: p.stat().st_mtime, reverse=True) if folder.is_dir() else []
    for rep in reps[:1]:
        m = re.search(r"## Questions for the (?:owner|King)\s*\n(.*?)(\n## |\Z)", rep.read_text(encoding="utf-8"), re.S)
        if m and m.group(1).strip() and not m.group(1).strip().lower().startswith("- none"):
            return m.group(1).strip()
    return ""


def prs_all() -> dict:
    def fetch():
        out = {}
        for team, t in cfg()["teams"].items():
            try:
                out[team] = orchestrator.open_prs(t)
            except Exception:
                out[team] = []
        return out

    return CACHE.get("prs", 90, fetch)


def reported_prs(project: str) -> list[dict]:
    """Pull requests reported through events (pr.opened / pr.closed), in the gh CLI's shape."""
    return [
        {
            "number": p["number"],
            "title": p.get("title", f"#{p['number']}"),
            "url": p.get("url", ""),
            "isDraft": p.get("draft", False),
            "headRefName": p.get("branch", ""),
            "createdAt": iso(p["ts"]),
            "reviewDecision": "",
        }
        for p in store().pull_requests(project)
    ]


def previews(team: str) -> list[str]:
    d = TEAMS / team / "previews"
    files = sorted(d.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True) if d.exists() else []
    return [f.name for f in files[:8]]


def usage(c: dict) -> dict:
    """Agent tokens from the store (any source) and your own Claude Code usage from its logs."""
    today0 = meter.start_of_today()
    days = [(today0 - dt.timedelta(days=i)).date().isoformat() for i in range(6, -1, -1)]
    since = (today0 - dt.timedelta(days=6)).timestamp()
    today = days[-1]
    per_day = {d: 0.0 for d in days}
    proj_today: dict[str, float] = {}
    proj_week: dict[str, float] = {}
    for project, ts, d in store().tokens_since(since):
        day = dt.datetime.fromtimestamp(ts).astimezone().date().isoformat()
        w = weigh(d.get("model", ""), d)
        if day in per_day and not d.get("interactive"):  # your own sessions count as "you", below
            per_day[day] += w
        proj_week[project] = proj_week.get(project, 0) + w
        if day == today:
            proj_today[project] = proj_today.get(project, 0) + w
    mine = CACHE.get("personal", 20, lambda: meter.summary(c))
    personal = {d["date"]: d["personal"] for d in mine["daily"]}
    return {
        "today": int(per_day[today]),
        "week": int(sum(per_day.values())),
        "proj_today": proj_today,
        "proj_week": proj_week,
        "you_today": mine["today"]["personal"],
        "you_week": mine["week"]["personal"],
        "daily": [{"date": d, "agents": int(per_day[d]), "personal": personal.get(d, 0)} for d in days],
    }


def last_action(f: dict) -> dict | None:
    for e in reversed(f["feed"]):
        if e["kind"] in ("tool", "delegate", "say"):
            return {"agent": e["agent"], "text": e.get("title") or e["text"], "ts": iso(e["ts"])}
    return None


def overview() -> dict:
    c = cfg()
    sync()
    st = store()
    runner = runner_run()
    u = usage(c)
    b = c["budget"]
    if c["teams"]:
        pool = CACHE.get("pool", 20, lambda: orchestrator.pool_today(c))[0]
    else:
        caps = [x for x in (b["agents_daily"] - u["today"], b["agents_weekly"] - u["week"]) if b["agents_daily"]]
        pool = max(0, min(caps)) if caps else 0
    today = orchestrator.DAYS[dt.date.today().weekday()]
    prs = prs_all()
    declared = list(c["teams"]) + [p for p in c.get("projects", {}) if p not in c["teams"]]
    names = declared + [p for p in st.projects() if p not in declared]
    teams, live_runs, lost_run = [], [], None
    for name in names:
        t = c["teams"].get(name) or c.get("projects", {}).get(name) or {}
        latest = (st.runs(name, 1) or [None])[0]
        f = folded(name, latest["id"]) if latest else None
        r = f["run"] if f else None
        running = bool(r and r["live"])
        budget = (r["budget"] if r else 0) or (
            runner.get("allowance", 0) if runner and latest and runner.get("session") == latest["id"] else 0
        )
        run_info = None
        if r:
            run_info = {
                "team": name,
                "session": latest["id"],
                "since": r["started"],
                "started_at": iso(r["started"]),
                "allowance": budget,
                "state": r["state"],
                "last_heartbeat": r["heartbeat"] or r["last"],
            }
            if running:
                live_runs.append(run_info)
            elif r["state"] == "lost" and lost_run is None:
                lost_run = run_info
        teams.append(
            {
                "team": name,
                "title": t.get("title") or (r["title"] if r else ""),
                "key": t.get("key", ""),
                "mode": t.get("mode", "build"),
                "pr_mode": t.get("pr_mode", "none"),
                "enabled": t.get("enabled", True),
                "runnable": name in c["teams"] and not DEMO,
                "source": r["source"] if r else "",
                "scheduled_today": name in c["schedule"].get(today, []),
                "running": running,
                "run_state": r["state"] if r and r["state"] != "finished" else None,
                "health": runs.health(f),
                "heartbeat_at": iso(r["heartbeat"] or r["last"]) if r and r["state"] != "finished" else None,
                "now": last_action(f) if running else None,
                "allowance": budget if running else 0,
                "used": r["tokens"] if running else 0,
                "started_at": iso(r["started"]) if r else None,
                "last_run_at": iso(r["last"]) if r else None,
                "today_tokens": int(u["proj_today"].get(name, 0)),
                "week_tokens": int(u["proj_week"].get(name, 0)),
                "backlog": backlog_counts(name),
                "prs": prs.get(name, []) or reported_prs(name),
                "questions": questions(name),
                "previews": previews(name) if name in c["teams"] else [],
            }
        )
    return {
        "generated_at": iso(time.time()),
        "utc_offset_min": round(dt.datetime.now().astimezone().utcoffset().total_seconds() / 60),
        "name": NAME,
        "version": __version__,
        "demo": DEMO,
        "stop": (HQ / "STOP").exists(),
        "running": live_runs[0] if live_runs else None,
        "live_runs": live_runs,
        "lost_run": lost_run,
        "budget": {
            "agents_today": u["today"],
            "agents_daily": b["agents_daily"],
            "agents_week": u["week"],
            "agents_weekly": b["agents_weekly"],
            "you_today": u["you_today"],
            "you_week": u["you_week"],
            "pool": pool,
            "warn_at": b.get("warn_at", 0.8),
            "daily": u["daily"],
        },
        "schedule": {d: c["schedule"].get(d, []) for d in orchestrator.DAYS},
        "today": today,
        "teams": teams,
    }


# ───────────────────────────── actions ─────────────────────────────


def spawn(args: list[str], window: bool) -> None:
    env = {
        **os.environ,
        paths.HOME_ENV: str(HQ),
        "PYTHONPATH": os.pathsep.join(filter(None, [str(paths.PKG.parent), os.environ.get("PYTHONPATH")])),
    }
    subprocess.Popen(
        [sys.executable, "-m", "kestrel", *args],
        cwd=HQ,
        **system.background_kwargs(window),
        env=env,
        close_fds=True,
        stdin=subprocess.DEVNULL,
        stdout=None if window else subprocess.DEVNULL,
        stderr=None if window else subprocess.DEVNULL,
    )


def act(path: str, q: dict) -> dict:
    c = cfg()
    if DEMO:
        return {"ok": False, "msg": "Demo mode: buttons are disabled, nothing real is running."}
    if path == "/api/stop":
        (HQ / "STOP").write_text("Raised from the Kestrel\n")
        orchestrator.log("STOP flag raised from the Kestrel.")
        return {"ok": True, "msg": "STOP raised: agents halt at their next action."}
    if path == "/api/resume":
        (HQ / "STOP").unlink(missing_ok=True)
        orchestrator.log("STOP flag lowered from the Kestrel.")
        return {"ok": True, "msg": "STOP lowered."}
    team = (q.get("team") or [""])[0]
    if team not in c["teams"]:
        return {"ok": False, "msg": "unknown team"}
    if path == "/api/run":
        run = runner_run()
        if run and run["state"] == "running":
            return {"ok": False, "msg": "A run is already in progress."}
        spawn(["run", "--team", team, "--force"], window=False)
        return {"ok": True, "msg": f"{team} started. It will appear as running in a few seconds."}
    if path == "/api/demo":
        pr = (q.get("pr") or [""])[0]
        spawn(["launch", team] + ([pr] if pr.isdigit() else []), window=True)
        return {"ok": True, "msg": f"Demo of {team}{' #' + pr if pr else ''} starting in a new window."}
    return {"ok": False, "msg": "unknown action"}


# ───────────────────────────── http ─────────────────────────────


ASSET_TYPES = {
    "js": "text/javascript; charset=utf-8",
    "css": "text/css; charset=utf-8",
    "woff2": "font/woff2",
    "woff": "font/woff",
    "svg": "image/svg+xml",
    "png": "image/png",
    "ico": "image/x-icon",
}
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)
NOT_BUILT = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>__APP_NAME__</title></head>
<body style="font:15px system-ui,sans-serif;max-width:560px;margin:15vh auto;padding:0 16px;line-height:1.5">
<h1 style="font-size:20px">The __APP_NAME__ web app is not built</h1>
<p>Build it once from the repository root, then reload this page:</p>
<pre style="background:#f3f3f0;padding:12px;border-radius:8px">cd frontend
npm ci
npm run build</pre></body></html>"""


def index_page() -> str:
    f = paths.STATIC / "index.html"
    page = f.read_text(encoding="utf-8") if f.is_file() else NOT_BUILT
    return page.replace("__APP_NAME__", NAME)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _ok_host(self) -> bool:
        return self.headers.get("Host", "") in HOSTS

    def _send(self, code: int, body: bytes, ctype: str, cache: str = "no-store") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Frame-Options", "DENY")
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
                return self._send(200, index_page().encode(), "text/html; charset=utf-8")
            m = re.match(r"^/(assets/)?([A-Za-z0-9._-]+\.(js|css|woff2|woff|svg|png|ico))$", u.path)
            if m:
                folder = (paths.STATIC / (m.group(1) or "")).resolve()
                f = (folder / m.group(2)).resolve()
                if f.is_file() and f.parent == folder:
                    # Vite puts a content hash in every file name under assets/, so those never change.
                    cache = "public, max-age=31536000, immutable" if m.group(1) else "no-cache"
                    return self._send(200, f.read_bytes(), ASSET_TYPES[m.group(3)], cache)
            if u.path == "/api/overview":
                return self._json(overview())
            if u.path == "/v1/health":
                return self._json({"ok": True, "version": __version__, "events": "v1"})
            if u.path == "/api/session":
                team = (q.get("team") or [""])[0]
                if not team or not known(team):
                    return self._json({"error": "unknown project"}, 404)
                return self._json(session_detail(team, (q.get("id") or [None])[0]))
            m = re.match(r"^/previews/([a-z0-9-]+)/([A-Za-z0-9._-]+\.png)$", u.path)
            if m and m.group(1) in cfg()["teams"]:
                f = (TEAMS / m.group(1) / "previews" / m.group(2)).resolve()
                if f.is_file() and f.parent == (TEAMS / m.group(1) / "previews").resolve():
                    return self._send(200, f.read_bytes(), "image/png")
            return self._send(404, b"not found", "text/plain")
        except Exception as e:  # keep serving
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def _ingest(self):
        """POST /v1/events: events from agents and adapters (see docs/events.md)."""
        if not ingest.authorized(self.headers.get("Authorization")):
            return self._json({"error": "missing or wrong bearer token (see `kestrel token`)"}, 401)
        length = int(self.headers.get("Content-Length") or 0)
        if length > ingest.MAX_BODY:
            return self._json({"error": f"body larger than {ingest.MAX_BODY // 1_000_000} MB"}, 413)
        try:
            raw = ingest.parse_body(self.rfile.read(length), self.headers.get("Content-Type", "application/json"))
            result = ingest.ingest(store(), raw)
        except (EventError, UnicodeDecodeError) as e:
            return self._json({"error": str(e)}, 400)
        code = 400 if result["rejected"] and not (result["accepted"] or result["duplicates"]) else 200
        return self._json(result, code)

    def do_POST(self):
        if not self._ok_host():
            return self._send(403, b"forbidden", "text/plain")
        if urlparse(self.path).path == "/v1/events":
            return self._ingest()
        origin = self.headers.get("Origin", "")
        if (
            not self._ok_host()
            or self.headers.get("X-Kestrel") != "1"
            or (origin and urlparse(origin).netloc not in HOSTS)
        ):
            return self._send(403, b"forbidden", "text/plain")
        u = urlparse(self.path)
        res = act(u.path, parse_qs(u.query))
        CACHE.drop("prs")
        return self._json(res, 200 if res.get("ok") else 400)


class Server(ThreadingHTTPServer):
    """Owns its port exclusively. On Windows, SO_REUSEADDR lets a second server bind the same port
    and the browser then reaches whichever one answers, so an old dashboard could shadow a new one."""

    allow_reuse_address = sys.platform != "win32"

    def server_bind(self) -> None:
        if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def serve(open_browser: bool = True, port: int = PORT, host: str | None = None) -> None:
    """Serve the dashboard. `host` (or $KESTREL_HOST) defaults to 127.0.0.1; containers bind
    0.0.0.0 and publish the port on the host's loopback only. The Host check still applies."""
    global HOSTS
    HOSTS = {f"127.0.0.1:{port}", f"localhost:{port}"}
    host = host or os.environ.get("KESTREL_HOST") or "127.0.0.1"
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(f"Listening on {host}: anyone who can reach this port can see your agents' activity.")
    try:
        srv = Server((host, port), Handler)
    except OSError:
        sys.exit(
            f"Port {port} is already in use, probably by another {NAME} dashboard. "
            f"Close it first, or pick another port with --port."
        )
    url = f"http://127.0.0.1:{port}"
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
