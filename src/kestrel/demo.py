"""Demo mode: the dashboard with realistic fake projects, so anyone can try it without agents.

  kestrel demo            → http://127.0.0.1:7777

Six fictional projects show every state the dashboard knows: a live run, a stuck agent, a run
that left work unfinished, a failed run, a lost run and a quiet one, over a week of history.
Everything goes through the real code paths (event validation, the store, the Reporter client), in
a throwaway home folder that is deleted when you stop the demo. Your own data is never touched.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

OPUS, SONNET, HAIKU = "claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"

STACKS = {
    "web": {
        "files": [
            "app/checkout/page.tsx",
            "app/cart/CartDrawer.tsx",
            "lib/stripe.ts",
            "app/api/orders/route.ts",
            "components/ProductCard.tsx",
            "lib/money.ts",
        ],
        "test": "npm test -- --runInBand",
        "pass": "Test Suites: 31 passed, 31 total\nTests:       128 passed, 128 total",
        "fail": "Tests:       3 failed, 125 passed, 128 total",
        "build": "npm run build",
        "lint": "npm run lint",
        "e2e": "npx playwright test checkout",
    },
    "go": {
        "files": [
            "internal/invoice/service.go",
            "internal/payout/scheduler.go",
            "cmd/api/main.go",
            "internal/invoice/service_test.go",
            "internal/ledger/entries.go",
        ],
        "test": "go test ./...",
        "pass": "ok   billing/internal/invoice   0.412s\nok   billing/internal/payout    0.287s",
        "fail": "--- FAIL: TestPayoutRounding (0.00s)\nFAIL billing/internal/payout",
        "build": "go build ./...",
        "lint": "golangci-lint run",
        "e2e": "go test -race -run Integration ./...",
    },
    "rn": {
        "files": [
            "src/screens/Feed.tsx",
            "src/hooks/useOfflineQueue.ts",
            "src/api/client.ts",
            "src/screens/Settings.tsx",
            "src/store/session.ts",
        ],
        "test": "npx jest",
        "pass": "Tests:       64 passed, 64 total",
        "fail": "Tests:       2 failed, 62 passed, 64 total",
        "build": "npx tsc --noEmit",
        "lint": "npx eslint src",
        "e2e": "npx detox test -c ios.sim.release",
    },
    "py": {
        "files": [
            "pipeline/extract/orders.py",
            "pipeline/transform/dedupe.py",
            "pipeline/load/warehouse.py",
            "tests/test_dedupe.py",
            "pipeline/config.py",
        ],
        "test": "pytest -q",
        "pass": "57 passed in 3.21s",
        "fail": "2 failed, 55 passed in 3.40s",
        "build": "python -m compileall -q pipeline",
        "lint": "ruff check .",
        "e2e": "pytest -q tests/integration",
    },
    "astro": {
        "files": ["src/pages/guides/index.astro", "src/content/config.ts", "astro.config.mjs", "src/layouts/Doc.astro"],
        "test": "npx astro check",
        "pass": "Result (42 files): 0 errors, 0 warnings",
        "fail": "Result (42 files): 2 errors",
        "build": "npx astro build",
        "lint": "npx linkinator dist --recurse",
        "e2e": "npx linkinator dist --recurse",
    },
    "node": {
        "files": [
            "src/sessions/store.ts",
            "src/sso/saml.ts",
            "src/totp/verify.ts",
            "src/routes/login.ts",
            "test/totp.test.ts",
        ],
        "test": "npm test",
        "pass": "Tests: 212 passed, 212 total",
        "fail": "Tests: 4 failed, 208 passed, 212 total",
        "build": "npm run build",
        "lint": "npm run lint",
        "e2e": "npm run test:e2e",
    },
}

PROJECTS = {
    "storefront": {
        "title": "Storefront: Next.js shop with Stripe checkout",
        "key": "SHP",
        "stack": "web",
        "tasks": [
            "Apple Pay in checkout",
            "Fix keyboard trap in the cart drawer",
            "Order confirmation email",
            "Show stock levels on product cards",
            "Retry failed Stripe webhooks",
        ],
    },
    "billing-api": {
        "title": "Billing API: Go service for invoices and payouts",
        "key": "BIL",
        "stack": "go",
        "tasks": ["Idempotent payout scheduling", "Invoice PDF rendering", "Ledger export to CSV"],
    },
    "mobile-app": {
        "title": "Mobile app: React Native client for iOS and Android",
        "key": "MOB",
        "stack": "rn",
        "tasks": ["Offline queue for posts", "Biometric unlock", "Settings screen redesign"],
    },
    "data-pipeline": {
        "title": "Data pipeline: Python ETL into the warehouse",
        "key": "ETL",
        "stack": "py",
        "tasks": ["Deduplicate late-arriving orders", "Incremental loads for refunds", "Backfill March events"],
    },
    "auth-service": {
        "title": "Auth service: sessions, SSO and two-factor login",
        "key": "AUT",
        "stack": "node",
        "tasks": ["TOTP recovery codes", "SAML metadata refresh", "Session revocation API"],
    },
    "docs-site": {
        "title": "Docs site: Astro, audit only",
        "key": "DOC",
        "stack": "astro",
        "tasks": ["Audit broken links", "Accessibility pass on guides"],
    },
}

CONFIG_HEAD = """# Demo configuration (fictional projects).
[budget]
agents_daily = 800_000
agents_weekly = 4_000_000
warn_at = 0.80

[schedule]
mon = ["storefront", "billing-api"]
tue = ["mobile-app", "data-pipeline"]
wed = ["storefront", "auth-service"]
thu = ["billing-api", "mobile-app"]
fri = ["storefront", "data-pipeline"]
sat = ["auth-service"]
sun = ["docs-site"]

[model_weights]
"opus-5" = 1.0
"sonnet-5" = 0.5
"haiku-5" = 0.025
default = 1.0
"""


def slug(text: str) -> str:
    return "-".join(w for w in "".join(c if c.isalnum() else " " for c in text.lower()).split()[:4])


class Timeline:
    """Events of one run at offsets (seconds) from its start."""

    def __init__(self, rng: random.Random):
        self.rng, self.t, self.items = rng, 0.0, []

    def wait(self, lo: float, hi: float) -> None:
        self.t += self.rng.uniform(lo, hi)

    def add(self, type: str, agent: str | None = None, **data) -> None:
        self.items.append((self.t, {"type": type, "agent": agent, "data": data}))

    def tokens(self, agent: str, model: str, scale: float = 1.0) -> None:
        r = self.rng
        self.add(
            "agent.tokens",
            agent,
            model=model,
            input=int(r.uniform(6_000, 26_000) * scale),
            output=int(r.uniform(1_000, 5_600) * scale),
            cache_write=int(r.uniform(3_000, 16_000) * scale),
            cache_read=int(r.uniform(60_000, 240_000) * scale),
        )


def build_run(name: str, number: int, outcome: str, rng: random.Random, pr: int | None) -> list[tuple[float, dict]]:
    """One run's events. outcome: ok | failed | cutoff | lost | stuck."""
    p, s = PROJECTS[name], STACKS[PROJECTS[name]["stack"]]
    task = p["tasks"][number % len(p["tasks"])]
    key = f"{p['key']}-{number:03d}"
    branch = f"feat/{key}-{slug(task)}"
    tl = Timeline(rng)
    tl.add("run.started", title=f"{key} {task}", budget=400_000, source="demo")
    tl.add("agent.started", "lead", role="lead", description="Team lead", model=OPUS)
    for f in ("STATE.md", "BACKLOG.md"):
        tl.wait(2, 6)
        tl.add("agent.action", "lead", tool="Read", detail=f)
    tl.wait(2, 5)
    tl.add("agent.action", "lead", tool="Bash", detail="git -C repo fetch origin", result="")
    tl.tokens("lead", OPUS, 0.6)
    tl.wait(5, 14)
    tl.add("agent.message", "lead", text=f"Next up is {key}: {task}. Branching from main and briefing the developer.")
    tl.wait(2, 5)
    tl.add("agent.action", "lead", tool="Bash", detail=f"git -C repo switch -c {branch} origin/main")

    def delegate(aid: str, role: str, desc: str, model: str) -> None:
        tl.wait(3, 8)
        tl.add("agent.action", "lead", tool="Agent", detail=f"→ {role}: {desc}")
        tl.wait(1, 3)
        tl.add("agent.started", aid, role=role, description=desc, parent="lead", model=model)

    def run_cmd(aid: str, cmd: str, result: str, status: str = "ok", gap=(8, 40)) -> None:
        call = f"{aid}-{len(tl.items)}"
        tl.wait(2, 6)
        tl.add("agent.action", aid, tool="Bash", detail=cmd, call=call, status="running")
        tl.wait(*gap)
        tl.add("agent.action", aid, call=call, status=status, result=result)

    files = rng.sample(s["files"], k=min(4, len(s["files"])))
    delegate("developer-1", "developer", f"{key} {task}", SONNET)
    for f in files[:3]:
        tl.wait(4, 12)
        tl.add("agent.action", "developer-1", tool="Read", detail=f"repo/{f}")
    tl.wait(3, 8)
    tl.add("agent.action", "developer-1", tool="Grep", detail=f"{slug(task).split('-')[0]}  repo")
    tl.tokens("developer-1", SONNET)
    tl.wait(10, 25)
    tl.add("agent.message", "developer-1", text=f"Plan: change {files[0]} and {files[1]}, then cover it with tests.")
    for i, f in enumerate(files):
        tl.wait(15, 45)
        tl.add("agent.action", "developer-1", tool="Edit", detail=f"repo/{f}")
        if i % 2:
            tl.tokens("developer-1", SONNET)
        if outcome == "lost" and i == 2:
            return tl.items  # the runner died here: nothing more ever arrives
    run_cmd("developer-1", s["build"], "done")
    if outcome == "stuck":
        tl.wait(4, 8)
        tl.add("agent.action", "developer-1", tool="Bash", detail=s["e2e"], call="stuck-e2e", status="running")
        return tl.items
    run_cmd("developer-1", s["test"], s["pass"])
    tl.tokens("developer-1", SONNET, 0.8)
    tl.wait(3, 8)
    tl.add("agent.finished", "developer-1", status="ok")

    delegate("tester-1", "tester", f"Full test suite for {key}", HAIKU)
    if outcome == "failed":
        run_cmd("tester-1", s["test"], s["fail"], "error", (20, 60))
        tl.tokens("tester-1", HAIKU)
        tl.wait(4, 8)
        tl.add("agent.message", "tester-1", text="3 tests fail in the totals: amounts are rounded before the discount.")
        tl.add("agent.finished", "tester-1", status="ok")
        delegate("developer-2", "developer", f"Fix the failing tests for {key}", SONNET)
        tl.wait(20, 50)
        tl.add("agent.action", "developer-2", tool="Edit", detail=f"repo/{files[0]}")
        run_cmd("developer-2", s["test"], s["fail"], "error")
        tl.tokens("developer-2", SONNET)
        tl.add("agent.finished", "developer-2", status="failed", error="Tests still failing")
        tl.wait(5, 10)
        tl.add("agent.notice", "lead", level="critical", text="Stopping: tests still fail after two attempts")
        tl.add("agent.finished", "lead", status="failed")
        tl.add("run.finished", status="failed", error=f"{key}: tests still failing after two attempts")
        return tl.items
    run_cmd("tester-1", s["test"], s["pass"], "ok", (20, 70))
    tl.tokens("tester-1", HAIKU)
    tl.wait(2, 5)
    tl.add("agent.finished", "tester-1", status="ok")

    delegate("qa-1", "qa", f"Check {key} against the spec", HAIKU)
    for f in files[:2]:
        tl.wait(4, 10)
        tl.add("agent.action", "qa-1", tool="Read", detail=f"repo/{f}")
    tl.tokens("qa-1", HAIKU)
    tl.wait(8, 20)
    tl.add("agent.message", "qa-1", text="PASS: meets the acceptance criteria. Minor: the empty state needs copy.")
    tl.add("agent.finished", "qa-1", status="ok")

    if outcome == "cutoff":
        delegate("developer-2", "developer", "Fix the flaky end-to-end test", SONNET)
        tl.wait(10, 20)
        tl.add("agent.action", "developer-2", tool="Read", detail=f"repo/{files[-1]}")
        tl.wait(10, 20)
        tl.add("agent.action", "developer-2", tool="Bash", detail=s["e2e"], call="cut", status="running")
    if rng.random() < 0.5:
        delegate("security-1", "security", f"Security review of {key}", SONNET)
        tl.wait(6, 14)
        tl.add("agent.action", "security-1", tool="Grep", detail="api[_-]?key|secret|password  repo")
        tl.tokens("security-1", SONNET, 0.5)
        tl.wait(6, 14)
        tl.add("agent.message", "security-1", text="No findings.")
        tl.add("agent.finished", "security-1", status="ok")
    if rng.random() < 0.3:
        tl.add("agent.notice", "lead", level="warning", text="Budget warning: 81% of this run's 400k tokens used")

    tl.wait(5, 12)
    tl.add("agent.action", "lead", tool="Bash", detail=f'git -C repo commit -am "{task}"')
    tl.wait(3, 8)
    tl.add("agent.action", "lead", tool="Bash", detail=f"git -C repo push -u origin {branch}")
    if pr:
        tl.wait(3, 8)
        url = f"https://github.com/acme/{name}/pull/{pr}"
        tl.add("agent.action", "lead", tool="Bash", detail=f'gh pr create --title "{key} {task}"', result=url)
        tl.add("pr.opened", number=pr, title=f"{key} {task}", url=url, branch=branch, draft=False)
    tl.tokens("lead", OPUS)
    tl.wait(4, 10)
    tl.add("agent.action", "lead", tool="Write", detail="reports/latest.md")
    tl.add("agent.finished", "lead", status="ok")
    tl.add("run.finished", status="ok", summary=f"{key} done" + (f", PR #{pr} opened" if pr else ""))
    return tl.items


def materialize(name: str, run_id: str, start: float, items, until: float | None = None) -> list[dict]:
    out = []
    for offset, e in items:
        ts = start + offset
        if until is not None and ts > until:
            break
        raw = {**e, "project": name, "run": None if e["type"].startswith("pr.") else run_id, "ts": ts}
        out.append(raw)
    return out


def at_local(days_ago: int, hour: float) -> float:
    base = dt.datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    return (base - dt.timedelta(days=days_ago) + dt.timedelta(hours=hour)).timestamp()


def seed(home: Path, send, now: float, rng: random.Random) -> dict:
    """A week of history plus today's runs. Returns what the live loop keeps going."""
    pr_numbers = {n: 10 + i * 7 for i, n in enumerate(PROJECTS)}
    task_no = {n: 1 for n in PROJECTS}

    def run(name: str, start: float, outcome: str, pr: bool = True, until: float | None = None):
        run_id = f"{name}-{dt.datetime.fromtimestamp(start).strftime('%Y%m%d-%H%M')}"
        number = task_no[name]
        task_no[name] += 1
        pr_no = None
        if pr and outcome not in ("failed", "lost", "stuck"):
            pr_numbers[name] += 1
            pr_no = pr_numbers[name]
        items = build_run(name, number, outcome, rng, pr_no)
        send(materialize(name, run_id, start, items, until))
        return run_id, items, pr_no

    # history: days 6..1, a handful of runs a day, mostly fine; older PRs get merged
    for days_ago in range(6, 0, -1):
        for name in rng.sample(list(PROJECTS), k=rng.randint(3, 5)):
            if name == "docs-site" and days_ago < 2:
                continue
            outcome = "failed" if rng.random() < 0.12 else "ok"
            _, items, pr_no = run(name, at_local(days_ago, rng.uniform(8, 18)), outcome, name != "docs-site")
            if pr_no and days_ago > 1:
                merged = at_local(days_ago - 1, rng.uniform(9, 12))
                send([{"type": "pr.closed", "project": name, "ts": merged, "data": {"number": pr_no, "merged": True}}])

    # today: the latest run of each project shows one state
    run("docs-site", at_local(1, 16), "ok", pr=False)
    run("auth-service", now - 5 * 3600, "lost")
    run("data-pipeline", now - 3 * 3600, "failed")
    run("mobile-app", now - 2 * 3600, "cutoff")
    run("storefront", now - 6 * 3600, "ok")
    stuck_items = build_run("billing-api", task_no["billing-api"], "stuck", rng, None)
    stuck_start = now - stuck_items[-1][0] - 14 * 60  # its last sign of life was 14 minutes ago
    stuck_id = f"billing-api-{dt.datetime.fromtimestamp(stuck_start).strftime('%Y%m%d-%H%M')}"
    send(materialize("billing-api", stuck_id, stuck_start, stuck_items))
    live_start = now - 150
    live_id, live_items, _ = run("storefront", live_start, "ok", until=now)

    write_team_files(home)
    return {
        "live": {"name": "storefront", "id": live_id, "start": live_start, "items": live_items},
        "stuck": ("billing-api", stuck_id),
        "next_task": task_no["storefront"],
        "next_pr": pr_numbers["storefront"] + 1,
    }


def write_team_files(home: Path) -> None:
    """Backlogs and the teams' questions, as the runner's teams keep them."""
    marks = ["x", "x", "x", "r", "~", " ", " ", " ", "!"]
    for i, (name, p) in enumerate(PROJECTS.items()):
        team = home / "teams" / name
        (team / "reports").mkdir(parents=True, exist_ok=True)
        lines = [f"# Backlog: {name}", ""]
        for n in range(1, 10 + i):
            mark = marks[(n + i) % len(marks)]
            lines.append(f"- [{mark}] {p['key']}-{n:03d} P{n % 3} {p['tasks'][n % len(p['tasks'])]}")
        (team / "BACKLOG.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    questions = {
        "storefront": "- Apple Pay needs a verified domain in Stripe. Use the staging domain until launch? "
        "(Recommended: yes.)\n- Keep guest checkout once accounts ship?",
        "mobile-app": "- The flaky checkout e2e test was cut off mid-fix. Quarantine it for now, or block "
        "releases on it?",
    }
    for name, q in questions.items():
        report = home / "teams" / name / "reports" / f"{dt.date.today().isoformat()}.md"
        report.write_text(f"# {name}\n\n## Questions for the owner\n{q}\n\n## Next run\n- Continue\n", encoding="utf-8")


def live_loop(send, state: dict, rng: random.Random, stop: threading.Event) -> None:
    """Keeps the storefront run going in real time, and the stuck run's heartbeats coming."""
    live = state["live"]
    pending = [(live["start"] + off, e) for off, e in live["items"] if live["start"] + off > time.time()]
    next_beat, next_run = 0.0, None
    while not stop.is_set():
        now = time.time()
        due = [(t, e) for t, e in pending if t <= now]
        pending = [(t, e) for t, e in pending if t > now]
        if due:
            send(
                [
                    {**e, "project": live["name"], "run": None if e["type"].startswith("pr.") else live["id"], "ts": t}
                    for t, e in due
                ]
            )
        if now >= next_beat:
            beats = [{"type": "run.heartbeat", "project": state["stuck"][0], "run": state["stuck"][1]}]
            if pending:
                beats.append({"type": "run.heartbeat", "project": live["name"], "run": live["id"]})
            send(beats)
            next_beat = now + 5
        if not pending:  # the run finished: start the next one shortly
            if next_run is None:
                next_run = now + 25
            elif now >= next_run:
                next_run = None
                items = build_run(live["name"], state["next_task"], "ok", rng, state["next_pr"])
                state["next_task"] += 1
                state["next_pr"] += 1
                live.update(id=f"storefront-{dt.datetime.fromtimestamp(now).strftime('%Y%m%d-%H%M%S')}", start=now)
                # a little faster than real life, so something happens every couple of seconds
                pending = [(now + off * 0.35, e) for off, e in items]
        stop.wait(0.5)


def sender(store):
    """Send events grouped by project through the Python client, like any reporter would."""
    from kestrel.client import Reporter

    def send(events: list[dict]) -> None:
        by_project: dict[str, list[dict]] = {}
        for e in events:
            by_project.setdefault(e["project"], []).append({k: v for k, v in e.items() if k != "project"})
        for project, evs in by_project.items():
            Reporter(project, store=store).send(evs)

    return send


def serve(port: int, open_browser: bool) -> None:
    """Runs inside the demo's own process, whose home folder is already the throwaway one."""
    from kestrel import meter, paths
    from kestrel.api import server
    from kestrel.storage.store import open_store

    home = paths.HOME
    projects = "".join(f'\n[projects.{n}]\ntitle = "{p["title"]}"\nkey = "{p["key"]}"\n' for n, p in PROJECTS.items())
    paths.CONFIG.write_text(CONFIG_HEAD + projects, encoding="utf-8")
    meter.PROJECTS = home / "no-claude-logs"  # never read the real ~/.claude logs in the demo
    store = open_store()
    rng = random.Random(7)

    send = sender(store)
    state = seed(home, send, time.time(), rng)
    stop = threading.Event()
    threading.Thread(target=live_loop, args=(send, state, rng, stop), daemon=True).start()
    print("Demo mode: fictional projects and agents, deleted when you stop. Nothing real runs.")
    try:
        server.serve(open_browser=open_browser, port=port)
    finally:
        stop.set()


def launch(port: int = 7777, open_browser: bool = True) -> int:
    """`kestrel demo`: run the demo in its own process with a throwaway home folder."""
    from kestrel import paths

    home = Path(tempfile.mkdtemp(prefix="kestrel-demo-"))
    env = {
        **os.environ,
        paths.HOME_ENV: str(home),
        "KESTREL_DEMO": "1",
        "PYTHONPATH": os.pathsep.join(filter(None, [str(paths.PKG.parent), os.environ.get("PYTHONPATH")])),
    }
    cmd = [sys.executable, "-m", "kestrel.demo", "--port", str(port)] + ([] if open_browser else ["--no-browser"])
    try:
        return subprocess.call(cmd, env=env)
    except KeyboardInterrupt:
        return 0
    finally:
        shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=7777)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    if os.environ.get("KESTREL_DEMO") != "1":
        sys.exit("Start the demo with `kestrel demo`.")
    try:
        serve(a.port, not a.no_browser)
    except KeyboardInterrupt:
        pass
