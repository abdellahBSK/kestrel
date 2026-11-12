"""The runner: schedules and runs teams of Claude Code agents.

kestrel status                      usage today / this week, budget left
kestrel baseline                    your personal daily usage stats
kestrel setup [team ...]             create/refresh team workspaces
kestrel run [--team T] [--force] [--dry-run]
                                         today's run (once per day unless --force)
kestrel brief [YYYY-MM-DD]           rebuild the daily brief
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

from kestrel import NAME, meter, paths
from kestrel.core import status
from kestrel.runner import system

HQ = meter.HQ
TEAMS = HQ / "teams"
STATE = HQ / "state"
LOGS = HQ / "logs"
REPORTS = HQ / "reports"
ROLES = ["developer", "tester", "qa", "security", "optimizer"]
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
PY = sys.executable.replace("\\", "/")
GUARD = (paths.RUNNER / "guard.py").as_posix()


def log(msg: str) -> None:
    line = f"[{dt.datetime.now().astimezone().isoformat(timespec='seconds')}] {msg}"
    print(line, flush=True)
    LOGS.mkdir(exist_ok=True)
    with open(LOGS / "orchestrator.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def git(repo: Path, *args: str, check: bool = True, env: dict | None = None) -> str:
    e = {**os.environ, "GIT_CEILING_DIRECTORIES": str(TEAMS), **(env or {})}
    r = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", env=e
    )
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


def fmt(n: int) -> str:
    return f"{n / 1e6:.2f}M" if n >= 1e6 else f"{n / 1e3:.0f}k"


# ───────────────────────────── workspace setup ─────────────────────────────


def gh_slug(t: dict) -> str:
    m = re.search(r"github\.com[/:]([^/]+/[^/]+?)(\.git)?$", t.get("repo", ""))
    return m.group(1) if m else ""


def default_branch(repo: Path) -> str:
    ref = git(repo, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD", check=False)
    return ref.split("/", 1)[1] if ref.startswith("origin/") else "main"


def owner(cfg: dict) -> str:
    """The GitHub account that owns the runner (its own repos get the `agent` label)."""
    return str(cfg.get("owner", {}).get("github", "")).strip()


def pr_flags(t: dict, cfg: dict) -> str:
    mode = t.get("pr_mode", "none")
    if mode == "none":
        return "(PR MODE = none: never push or open PRs)"
    own = bool(owner(cfg)) and gh_slug(t).split("/")[0].lower() == owner(cfg).lower()
    flags = ["--draft"] if mode == "draft" else []
    if own:
        flags += ["--label agent"]
    return " ".join(flags) or "(no extra flags)"


def hide_attribution(cfg: dict) -> bool:
    """`[pipeline] hide_ai_attribution`: keep "Co-Authored-By: Claude" and similar lines out of
    commits, PRs and files. Off by default: agent work is attributed unless you opt out."""
    return bool(cfg.get("pipeline", {}).get("hide_ai_attribution", False))


def rules_text(cfg: dict) -> str:
    rules = (paths.RUNNER / "rules" / "RULES.md").read_text(encoding="utf-8")
    block = re.compile(r"<!-- hide-attribution -->\n(.*?)<!-- /hide-attribution -->\n", re.S)
    return block.sub(lambda m: m.group(1) if hide_attribution(cfg) else "", rules)


def charter(team: str, t: dict, cfg: dict) -> str:
    rules = rules_text(cfg)
    specs = "\n".join(f"- specs/{Path(s).name}" for s in t.get("specs", [])) or "- (none: use README/docs in repo/)"
    repo = TEAMS / team / "repo"
    base = default_branch(repo) if (repo / ".git").exists() else "main"
    tools = paths.RUNNER.as_posix()
    return f"""# Team charter: {team}

PROJECT: {t["title"]}
MODE: {t.get("mode", "build")}
KEY: {t.get("key", "XXX")}   (backlog IDs and branches: {t.get("key", "XXX")}-001, feat/{t.get("key", "XXX")}-001-short-name)
GITHUB: {gh_slug(t) or "(none)"}   DEFAULT BRANCH: {base}
PR MODE: {t.get("pr_mode", "none")}   gh pr create flags: {pr_flags(t, cfg)}
FOCUS (from the owner): {t.get("focus", "")}

## Your workspace (you may only touch this folder)
- `repo/`       the git repository (one task branch per backlog item)
- `specs/`      specifications, read-only
{specs}
- `BACKLOG.md`  prioritised task list with IDs (you maintain it)
- `STATE.md`    handoff notes between runs (you maintain it)
- `demo.json`   how to run the app for previews (you keep it accurate):
                {{"cwd": "subfolder of the repo, or .", "install": "...", "run": "...", "url": "http://localhost:PORT", "screens": ["/", "/path"], "size": "390x844"}}
- `previews/`   screenshots you take
- `reports/`    one report per run + PR bodies (`reports/pr-<KEY>-<NNN>.md`)

Run git as `git -C repo ...` and gh as `gh pr ... --repo {gh_slug(t) or "<owner/name>"}` from this folder.

## Runner tools (the only outside programs you may run)
- Screenshot a local page:  `python {tools}/shoot.py <http://localhost:...> previews/<name>.png --size 390x844`
- Publish screenshots for a PR: `python {tools}/preview.py --repo repo --branch <task-branch> previews/<files>`

{rules}
"""


def settings_json(cfg: dict | None = None) -> dict:
    hook = [{"type": "command", "command": f'"{PY}" "{GUARD}" --home "{HQ.as_posix()}"', "timeout": 30}]
    hidden = {"includeCoAuthoredBy": False, "attribution": {"commit": "", "pr": ""}}
    return {
        **(hidden if cfg and hide_attribution(cfg) else {}),
        "permissions": {
            "defaultMode": "dontAsk",
            "allow": [
                "Read",
                "Glob",
                "Grep",
                "Edit",
                "Write",
                "MultiEdit",
                "NotebookEdit",
                "Bash",
                "PowerShell",
                "Agent",
                "Task",
                "TodoWrite",
            ],
            "deny": ["WebFetch", "WebSearch"],
        },
        "hooks": {
            "PreToolUse": [{"matcher": "*", "hooks": hook}],
            "PostToolUse": [{"matcher": "*", "hooks": hook}],
            "Stop": [{"hooks": hook}],
        },
    }


def install_git_hooks(repo: Path, cfg: dict | None = None) -> None:
    hooks_dir = Path(git(repo, "rev-parse", "--git-path", "hooks"))
    if not hooks_dir.is_absolute():
        hooks_dir = repo / hooks_dir
    hooks_dir.mkdir(parents=True, exist_ok=True)
    for name in ("commit-msg", "pre-commit"):
        dst = hooks_dir / name
        if name == "commit-msg" and not (cfg and hide_attribution(cfg)):
            dst.unlink(missing_ok=True)
            continue
        shutil.copyfile(paths.RUNNER / "git-hooks" / name, dst)
        os.chmod(dst, 0o755)


def ensure_repo(team: str, t: dict, cfg: dict) -> Path:
    tdir = TEAMS / team
    repo = tdir / "repo"
    owner = {"KESTREL_OWNER": "1"}
    if not (repo / ".git").exists():
        url = t.get("repo", "")
        if url:
            m = re.search(r"github\.com[/:]([^/]+/[^/.]+)", url)
            log(f"{team}: cloning {url}")
            r = subprocess.run(
                ["gh", "repo", "clone", m.group(1) if m else url, str(repo)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if r.returncode != 0 and not (repo / ".git").exists():
                raise RuntimeError(f"clone failed: {r.stderr.strip()}")
        else:
            log(f"{team}: new local repository")
            repo.mkdir(parents=True, exist_ok=True)
            subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    # make sure we are really in the team repo, never a parent repo (e.g. the home folder)
    top = Path(git(repo, "rev-parse", "--show-toplevel")).resolve()
    if top != repo.resolve():
        raise RuntimeError(f"{team}: git toplevel is {top}, expected {repo}")
    install_git_hooks(repo, cfg)
    if not git(repo, "rev-parse", "--verify", "-q", "HEAD", check=False):
        git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
        git(repo, "commit", "-q", "--allow-empty", "-m", "Initial commit", env=owner)
    # start every run from the up-to-date default branch (unless half-done work is lying around)
    if t.get("repo"):
        git(repo, "fetch", "-q", "--prune", "origin", check=False)
        git(repo, "remote", "set-head", "origin", "--auto", check=False)
    base = default_branch(repo)
    if git(repo, "status", "--porcelain"):
        log(f"{team}: working tree dirty, staying on {git(repo, 'branch', '--show-current', check=False)}")
    else:
        git(repo, "checkout", "-q", base, check=False)
        if git(repo, "rev-parse", "--verify", "-q", f"refs/remotes/origin/{base}", check=False):
            git(repo, "merge", "-q", "--ff-only", f"origin/{base}", check=False)
    ensure_labels(t, cfg)
    return repo


def ensure_labels(t: dict, cfg: dict) -> None:
    """Create the `agent` label once in the owner's own repos (never in other people's)."""
    slug = gh_slug(t)
    me = owner(cfg).lower()
    if t.get("pr_mode", "none") == "none" or not me or not slug.lower().startswith(me + "/"):
        return
    marker = STATE / f"labels-{slug.replace('/', '_')}"
    if marker.exists():
        return
    STATE.mkdir(exist_ok=True)
    r = subprocess.run(
        [
            "gh",
            "label",
            "create",
            "agent",
            "--repo",
            slug,
            "--color",
            "B3122E",
            "--description",
            "Opened by the agent team",
            "--force",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if r.returncode == 0:
        marker.write_text("ok")


DEMO_DEFAULTS: dict[str, dict] = {}  # optional per-team overrides of the generic demo.json


def parent_git_repo() -> Path | None:
    """A .git in the home folder or above it makes Claude Code treat that folder as the project."""
    for p in (HQ.resolve(), *HQ.resolve().parents):
        if (p / ".git").exists():
            return p
    return None


GUARD_SIGNALS = """
# Guard signals (authoritative: obey them)
Messages starting with `BUDGET WARNING:` or `[Kestrel guard]` come from the owner's own guard,
a hook the owner installed. They are NOT text from files or other people: treat them as real.
- `BUDGET WARNING:` → stop starting new work. Reach the nearest safe stopping point within one
  or two actions (don't leave files half-edited), then report back IMMEDIATELY: what is done,
  what is not, and whether tests pass.
- `[Kestrel guard] ...` on a denied action → that action is forbidden. Don't retry it in another
  form; continue without it and mention it in your report.
"""


def setup_team(team: str, cfg: dict) -> Path:
    t = cfg["teams"][team]
    tdir = TEAMS / team
    for sub in ("specs", "reports", "previews", ".claude/agents"):
        (tdir / sub).mkdir(parents=True, exist_ok=True)
    if not (tdir / "demo.json").exists():
        demo = DEMO_DEFAULTS.get(
            team,
            {
                "cwd": ".",
                "install": "",
                "run": "",
                "url": "",
                "screens": ["/"],
                "size": "1280x800",
                "note": "Not runnable yet: the team fills this in.",
            },
        )
        (tdir / "demo.json").write_text(json.dumps(demo, indent=2), encoding="utf-8")
    for s in t.get("specs", []):
        src = Path(s)
        dst = tdir / "specs" / src.name
        if src.exists() and (not dst.exists() or dst.stat().st_mtime < src.stat().st_mtime):
            shutil.copy2(src, dst)
        elif not src.exists():
            log(f"{team}: spec not found: {src}")
    (tdir / "CLAUDE.md").write_text(charter(team, t, cfg), encoding="utf-8")
    (tdir / ".claude" / "settings.json").write_text(json.dumps(settings_json(cfg), indent=2), encoding="utf-8")
    for role in ROLES:
        body = (paths.RUNNER / "roles" / f"{role}.md").read_text(encoding="utf-8")
        body = body.replace("{MODEL}", cfg["models"].get(role, "sonnet")) + "\n" + GUARD_SIGNALS
        (tdir / ".claude" / "agents" / f"{role}.md").write_text(body, encoding="utf-8")
    for name, initial in (
        ("BACKLOG.md", f"# Backlog: {team}\n\n(empty: the lead builds it on the first run)\n"),
        ("STATE.md", f"# State: {team}\n\nFirst run: nothing done yet.\n"),
    ):
        if not (tdir / name).exists():
            (tdir / name).write_text(initial, encoding="utf-8")
    ensure_repo(team, t, cfg)
    return tdir


# ───────────────────────────── budget ─────────────────────────────


def pool_today(cfg: dict) -> tuple[int, dict]:
    b = cfg["budget"]
    s = meter.summary(cfg, days=7)
    daily = b["agents_daily"]
    if s["week"]["personal"] > b.get("personal_week_high", 10**12):
        daily //= 2
    left = min(daily - s["today"]["agents"], b["agents_weekly"] - s["week"]["agents"])
    return max(0, left), s


# ───────────────────────────── run ─────────────────────────────


def agents_json(tdir: Path) -> str:
    """Subagent definitions for --agents, built from the team's generated role files."""
    agents = {}
    for f in sorted((tdir / ".claude" / "agents").glob("*.md")):
        text = f.read_text(encoding="utf-8")
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.S)
        if not m:
            continue
        meta = dict(re.findall(r"^(\w+):\s*(.*)$", m.group(1), re.M))
        agents[meta["name"]] = {
            "description": meta.get("description", ""),
            "prompt": m.group(2).strip(),
            "tools": [x.strip() for x in meta.get("tools", "").split(",") if x.strip()],
            "model": meta.get("model", "sonnet"),
        }
    return json.dumps(agents)


def lead_prompt(team: str, t: dict, today: str, allowance: int) -> tuple[str, str]:
    system = (paths.RUNNER / "roles" / "lead.md").read_text(encoding="utf-8")
    system = system.replace("{DATE}", today).replace("{TEAM}", team)
    user = (
        f"Start today's run.\nDate: {today}\nTeam: {team}\nMode: {t.get('mode', 'build')}\n"
        f"Token allowance for this run: {allowance:,} (warning at 80%, hard stop at 100%).\n"
        f"Write your report to reports/{today}.md before ending."
    )
    return system, user


def run_team(team: str, cfg: dict, allowance: int, today: str, dry: bool) -> dict:
    t = cfg["teams"][team]
    tdir = setup_team(team, cfg)
    repo = tdir / "repo"
    system, user = lead_prompt(team, t, today, allowance)
    sid = str(uuid.uuid4())
    claude = shutil.which("claude") or "claude"
    ids = cfg.get("model_ids", {})
    cmd = [
        claude,
        "-p",
        user,
        "--model",
        ids.get(cfg["models"].get("lead", "opus"), cfg["models"].get("lead", "opus")),
        "--fallback-model",
        ids.get(cfg["models"].get("lead_fallback", "sonnet"), cfg["models"].get("lead_fallback", "sonnet")),
        "--effort",
        cfg["models"].get("lead_effort", "high"),
        "--append-system-prompt",
        system,
        "--permission-mode",
        "dontAsk",
        # team settings passed explicitly: flag settings don't depend on workspace trust
        "--settings",
        str(tdir / ".claude" / "settings.json"),
        "--setting-sources",
        "local",
        "--agents",
        agents_json(tdir),
        "--strict-mcp-config",
        "--disallowedTools",
        "WebFetch,WebSearch",
        "--session-id",
        sid,
        "--name",
        f"kestrel-{team}-{today}",
        "--output-format",
        "json",
    ]
    since = time.time()
    env = {
        **os.environ,
        "KESTREL_TEAM": team,
        "KESTREL_ALLOWANCE": str(allowance),
        "KESTREL_SINCE": str(since),
        paths.HOME_ENV: str(HQ),
        "KESTREL_MODE": t.get("mode", "build"),
        "KESTREL_HIDE_ATTRIBUTION": "1" if hide_attribution(cfg) else "0",
        "KESTREL_PR_MODE": t.get("pr_mode", "none") if t.get("mode", "build") == "build" else "none",
        "GIT_CEILING_DIRECTORIES": str(TEAMS),
    }
    for alias in ("opus", "sonnet", "haiku"):  # subagents use short names → pin versions
        if ids.get(alias):
            env[f"ANTHROPIC_DEFAULT_{alias.upper()}_MODEL"] = ids[alias]
    result = {"team": team, "allowance": allowance, "session": sid, "status": "dry-run", "used": 0}
    if dry:
        log(f"{team}: DRY RUN, would run with allowance {allowance:,} in {tdir}")
        return result
    log(f"{team}: starting (allowance {allowance:,}, session {sid})")
    STATE.mkdir(exist_ok=True)
    info = {"team": team, "session": sid, "since": since, "started_at": status.iso(since), "allowance": allowance}
    # The dashboard trusts this heartbeat, not the agents: if this process dies, the run shows as lost.
    with status.Heartbeat(STATE / "current.json", info) as hb:
        proc = subprocess.Popen(
            cmd,
            cwd=tdir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        hb.update(child_pid=proc.pid)
        try:
            out, _ = proc.communicate(timeout=4 * 3600)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate()
            rc = -1
    (LOGS / f"{today}-{team}.json").write_text(out or "", encoding="utf-8")
    info = {}
    try:
        info = json.loads(out) if out.strip() else {}
    except ValueError:
        pass
    text = json.dumps(info).lower() if info else (out or "").lower()
    if rc != 0 or info.get("is_error"):
        if "not logged in" in text or "please run /login" in text:
            result["status"] = "not-logged-in"
        elif re.search(r"usage limit|rate limit|limit reached|out of extra usage", text):
            result["status"] = "usage-limit"
        else:
            result["status"] = "error"
    else:
        result["status"] = "ok"
    if info.get("terminal_reason") == "hook_stopped" or ("kestrel guard" in text and "allowance exhausted" in text):
        result["status"] = "budget-stop"
        dirty = git(repo, "status", "--porcelain", check=False)
        if dirty:  # leave a handoff note so the next run reviews the half-done work
            with open(tdir / "STATE.md", "a", encoding="utf-8") as f:
                f.write(
                    f"\n\n## ⚠️ Unfinished work from the {today} run (stopped by budget)\n"
                    "These changes in repo/ were NOT committed. First thing next run: have tester + "
                    "qa review them, then commit or discard.\n```\n" + dirty + "\n```\n"
                )
    result["used"] = meter.team_used_since(team, dt.datetime.fromtimestamp(since).astimezone(), cfg)
    result["commits"] = git(repo, "log", "--branches", "--oneline", f"--since=@{int(since)}", check=False)
    result["prs"] = prs_since(t, since)
    report = tdir / "reports" / f"{today}.md"
    if not report.exists():
        report.write_text(
            f"# {team} — {today}\n\nThe run ended without a report "
            f"(status: {result['status']}).\n\nCommits:\n```\n{result['commits'] or 'none'}\n```\n",
            encoding="utf-8",
        )
    log(f"{team}: {result['status']}, used {result['used']:,} / {allowance:,}")
    return result


TASK_BRANCH_RE = re.compile(r"^(feat|fix|refactor|perf|test|docs|chore|security)/[A-Z]{3}-\d{3}-")


def open_prs(t: dict) -> list[dict]:
    """Open PRs on agent task branches in this team's repo."""
    slug = gh_slug(t)
    if not slug or t.get("pr_mode", "none") == "none":
        return []
    r = subprocess.run(
        [
            "gh",
            "pr",
            "list",
            "--repo",
            slug,
            "--state",
            "open",
            "--limit",
            "50",
            "--json",
            "number,title,url,isDraft,headRefName,createdAt,reviewDecision",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        prs = json.loads(r.stdout or "[]")
    except ValueError:
        return []
    return [p for p in prs if TASK_BRANCH_RE.match(p.get("headRefName", ""))]


def prs_since(t: dict, since: float) -> list[dict]:
    cutoff = dt.datetime.fromtimestamp(since, dt.UTC)
    return [p for p in open_prs(t) if dt.datetime.fromisoformat(p["createdAt"].replace("Z", "+00:00")) >= cutoff]


def notify(title: str, body: str, url: str, url2: str = "") -> None:
    system.notify(title, body, url, url2, runner_dir=paths.RUNNER)


def wait_for_network(max_wait: int = 180) -> bool:
    """Right after logon/wake Wi-Fi may not be up yet: poll the API host for up to 3 min."""
    import socket

    deadline = time.time() + max_wait
    while True:
        try:
            socket.create_connection(("api.anthropic.com", 443), timeout=5).close()
            return True
        except OSError:
            if time.time() > deadline:
                return False
            time.sleep(10)


def acquire_lock() -> bool:
    STATE.mkdir(exist_ok=True)
    lock = STATE / "run.lock"
    if lock.exists() and time.time() - lock.stat().st_mtime < 6 * 3600:
        try:
            pid = int(lock.read_text().strip() or 0)
        except (OSError, ValueError):
            pid = 0
        if status.pid_alive(pid):
            return False
        log(f"The previous runner (PID {pid}) is gone: taking over its lock.")
    lock.write_text(str(os.getpid()))
    return True


def save_results(day: str, rows: list[dict]) -> None:
    """Merge run results into state/run-<day>.json (a later run the same day must not erase earlier ones)."""
    f = STATE / f"run-{day}.json"
    old = status.read_json_list(f)
    sessions = {r.get("session") for r in rows if r.get("session")}
    merged = [r for r in old if r.get("session") not in sessions] + rows
    f.write_text(json.dumps(merged, indent=2), encoding="utf-8")


def recover_lost_run(cfg: dict) -> dict | None:
    """A runner that died mid-run leaves current.json behind. Record that run as lost, leave the team a
    handoff note about any uncommitted work, and clear the marker so the dashboard stops showing it."""
    run = status.run_state(STATE, status.thresholds(cfg)["heartbeat_timeout"])
    if not run or run["state"] != "lost":
        return None
    team, sid = run.get("team", ""), run.get("session", "")
    started = dt.datetime.fromtimestamp(run.get("since") or run["last_heartbeat"]).astimezone()
    log(f"{team}: the run started {started:%Y-%m-%d %H:%M} (session {sid}) was lost: its runner stopped early.")
    save_results(
        started.date().isoformat(),
        [{"team": team, "session": sid, "allowance": run.get("allowance", 0), "status": "lost", "used": 0}],
    )
    repo = TEAMS / team / "repo"
    dirty = git(repo, "status", "--porcelain", check=False) if (repo / ".git").exists() else ""
    if dirty:
        with open(TEAMS / team / "STATE.md", "a", encoding="utf-8") as f:
            f.write(
                f"\n\n## ⚠️ Unfinished work from the {started:%Y-%m-%d} run (the run was interrupted)\n"
                "These changes in repo/ were NOT committed. First thing next run: have tester + "
                "qa review them, then commit or discard.\n```\n" + dirty + "\n```\n"
            )
    (STATE / "current.json").unlink(missing_ok=True)
    return run


def cmd_run(args, cfg: dict) -> None:
    today = dt.date.today().isoformat()
    if (HQ / "STOP").exists():
        log("STOP flag present: no run.")
        return
    bad = parent_git_repo()
    if bad is not None:
        log(
            f"REFUSING TO RUN: {bad} is a git repository, so Claude Code would treat it as the "
            f"agents' project. Move the home folder outside it, or rename {bad / '.git'}."
        )
        return
    if not args.dry_run:
        recover_lost_run(cfg)
    if not args.force and dt.datetime.now().hour < cfg["schedule"].get("start_hour", 0):
        log("Too early (start_hour): no run yet.")
        return
    last = STATE / "last_run"
    if not args.force and not args.dry_run and last.exists() and last.read_text().strip() == today:
        log("Already ran today.")
        return
    if not args.dry_run and not acquire_lock():
        log("Another run is in progress.")
        return
    try:
        teams = [args.team] if args.team else cfg["schedule"].get(DAYS[dt.date.today().weekday()], [])
        teams = [t for t in teams if t in cfg["teams"] and (args.team or cfg["teams"][t].get("enabled", True))]
        if args.lead_model:
            cfg["models"]["lead"] = args.lead_model
        if not teams:
            log("No team scheduled today.")
            return
        if not args.dry_run and not wait_for_network():
            log("No network after 3 minutes: will retry at next trigger.")
            return
        if not args.dry_run:
            last.write_text(today)
        pool, s = pool_today(cfg)
        if args.extra:
            pool += args.extra
            log(f"One-off extra budget: +{args.extra:,} tokens")
        log(
            f"Pool today: {pool:,} tokens for {teams} (agents week {s['week']['agents']:,}, "
            f"personal week {s['week']['personal']:,})"
        )
        results = []
        for i, team in enumerate(teams):
            remaining_w = sum(cfg["teams"][x].get("weight", 1.0) for x in teams[i:])
            share = int(pool * cfg["teams"][team].get("weight", 1.0) / remaining_w)
            if args.allowance:
                share = min(share, args.allowance)
            if share < cfg["budget"].get("min_team_run", 120_000):
                log(f"{team}: skipped, only {share:,} tokens left")
                results.append({"team": team, "allowance": share, "status": "skipped", "used": 0})
                continue
            try:
                res = run_team(team, cfg, share, today, args.dry_run)
            except Exception as e:  # keep the other teams running
                log(f"{team}: FAILED: {e}")
                res = {"team": team, "allowance": share, "status": f"failed: {e}", "used": 0}
            results.append(res)
            pool -= res.get("used", 0) if not args.dry_run else share
            if res.get("status") == "usage-limit":
                log("Claude usage limit reached: stopping today's run.")
                break
            if res.get("status") == "not-logged-in":
                log("Claude CLI is not logged in (run `claude auth login`). Will retry at next trigger.")
                last.unlink(missing_ok=True)
                break
        if not args.dry_run:
            save_results(today, results)
            brief = write_brief(today, cfg)
            pulls = (
                f"https://github.com/pulls?q=is%3Aopen+is%3Apr+author%3A{owner(cfg)}+archived%3Afalse"
                if owner(cfg)
                else "https://github.com/pulls"
            )
            new_prs = [p for r in results for p in r.get("prs", [])]
            ready = [p for p in new_prs if not p.get("isDraft")]
            if new_prs:
                title = f"{NAME}: {len(ready)} PR(s) ready for review" + (
                    f", {len(new_prs) - len(ready)} draft" if len(ready) < len(new_prs) else ""
                )
                body = "\n".join(f"#{p['number']} {p['title']}" for p in new_prs[:4])
                url = new_prs[0]["url"] if len(new_prs) == 1 else pulls
            else:
                title, body = f"{NAME}: today's run is done", ", ".join(f"{r['team']}: {r['status']}" for r in results)
                url = pulls
            notify(title, body, url, brief.resolve().as_uri())
    finally:
        if not args.dry_run:
            (STATE / "run.lock").unlink(missing_ok=True)


# ───────────────────────────── brief ─────────────────────────────


def write_brief(day: str, cfg: dict) -> Path:
    REPORTS.mkdir(exist_ok=True)
    runs = []
    f = STATE / f"run-{day}.json"
    if f.exists():
        runs = json.loads(f.read_text(encoding="utf-8"))
    s = meter.summary(cfg, days=7)
    b = cfg["budget"]
    lines = [
        f"# Daily brief: {day}",
        "",
        "## Budget",
        f"- You today: **{fmt(s['today']['personal'])}** · you this week: {fmt(s['week']['personal'])}",
        f"- Agents today: **{fmt(s['today']['agents'])}** / {fmt(b['agents_daily'])} · "
        f"agents this week: {fmt(s['week']['agents'])} / {fmt(b['agents_weekly'])}",
        "",
        "| Team | Status | Used / allowance | New commits | New PRs |",
        "|---|---|---|---|---|",
    ]
    for r in runs:
        n = len([c for c in (r.get("commits") or "").splitlines() if c.strip()])
        lines.append(
            f"| {r['team']} | {r['status']} | {fmt(r.get('used', 0))} / {fmt(r.get('allowance', 0))} "
            f"| {n} | {len(r.get('prs', []))} |"
        )
    waiting = []
    for team, t in cfg["teams"].items():
        for p in open_prs(t):
            state = "draft" if p.get("isDraft") else (p.get("reviewDecision") or "ready").lower()
            waiting.append(
                f"- **{team}** [#{p['number']} {p['title']}]({p['url']}) · {state} · "
                f"try it: `kestrel launch {team} {p['number']}`"
            )
    if waiting:
        lines += ["", "## 🔀 Pull requests waiting for you", *waiting]
    questions = []
    for r in runs:
        rep = TEAMS / r["team"] / "reports" / f"{day}.md"
        if not rep.exists():
            continue
        body = rep.read_text(encoding="utf-8")
        m = re.search(r"## Questions for the owner\s*\n(.*?)(\n## |\Z)", body, re.S)
        if m and m.group(1).strip() and "none" not in m.group(1).strip().lower()[:10]:
            questions.append(f"**{r['team']}**\n{m.group(1).strip()}")
        lines += ["", "---", "", body.strip()]
    if questions:
        lines[1:1] = ["", "## ❓ Questions for you", *questions, ""]
    path = REPORTS / f"{day}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    shutil.copyfile(path, REPORTS / "LATEST.md")
    log(f"Brief written: {path}")
    return path


# ───────────────────────────── demo ─────────────────────────────

DEMOS = HQ / "demos"


def cmd_demo(args, cfg: dict) -> None:
    """Run a PR (or branch) of a project locally, in its own copy, and open it in the browser."""
    import urllib.request
    import webbrowser

    team = args.team
    if team not in cfg["teams"]:
        sys.exit(f"Unknown team '{team}'. Teams: {', '.join(cfg['teams'])}")
    t = cfg["teams"][team]
    tdir = TEAMS / team
    repo = tdir / "repo"
    demo = json.loads((tdir / "demo.json").read_text(encoding="utf-8")) if (tdir / "demo.json").exists() else {}
    if not demo.get("run") or not demo.get("url"):
        sys.exit(f"{team} has no runnable demo yet (teams/{team}/demo.json). {demo.get('note', '')}")
    target = args.target or default_branch(repo)
    if target.isdigit():
        r = subprocess.run(
            ["gh", "pr", "view", target, "--repo", gh_slug(t), "--json", "headRefName"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if r.returncode != 0:
            sys.exit(f"PR #{target} not found in {gh_slug(t)}")
        branch = json.loads(r.stdout)["headRefName"]
    else:
        branch = target
    git(repo, "fetch", "-q", "origin", branch, check=False)
    ref = f"origin/{branch}" if git(repo, "rev-parse", "--verify", "-q", f"origin/{branch}", check=False) else branch
    wt = DEMOS / team / re.sub(r"[^A-Za-z0-9._-]", "_", branch)
    if (wt / ".git").exists():
        subprocess.run(["git", "-C", str(wt), "checkout", "-q", "--detach", "--force", ref], check=True)
    else:
        wt.parent.mkdir(parents=True, exist_ok=True)
        git(repo, "worktree", "prune", check=False)
        git(repo, "worktree", "add", "-q", "--force", "--detach", str(wt), ref)
    # "cwd" is relative to the repo root; tolerate "repo" / "repo/web" (relative to the team folder).
    sub = Path(demo.get("cwd") or ".")
    if sub.parts and sub.parts[0] == "repo":
        sub = Path(*sub.parts[1:]) if len(sub.parts) > 1 else Path(".")
    cwd = wt / sub
    if not cwd.is_dir():
        sys.exit(f"demo.json cwd '{demo.get('cwd')}' doesn't exist in {wt}")
    print(f"▶ {team} @ {branch} ({git(Path(wt), 'log', '-1', '--format=%h %s')})\n  copy: {wt}")
    if demo.get("install") and not args.no_install:
        print(f"  installing: {demo['install']}")
        subprocess.run(demo["install"], cwd=cwd, shell=True)
    where = system.open_terminal(demo["run"], cwd, f"{team} demo - {branch}", LOGS / f"launch-{team}.log")
    if where == "window":
        print(f"  starting:   {demo['run']}  (in a new window; close it to stop)")
    else:
        print(f"  starting:   {demo['run']}  (in the background; output in {where})")
    url = demo["url"]
    for _ in range(90):
        try:
            urllib.request.urlopen(url, timeout=2)
            break
        except Exception:
            time.sleep(2)
    else:
        print(f"  {url} didn't answer after 3 minutes; check the demo window for errors.")
        return
    screens = demo.get("screens") or ["/"]
    webbrowser.open(url.rstrip("/") + screens[0] if screens[0] != "/" else url)
    print(f"  opened {url}")


# ───────────────────────────── status ─────────────────────────────


def cmd_status(cfg: dict) -> None:
    pool, s = pool_today(cfg)
    b = cfg["budget"]
    print(f"{'':<26}{'today':>12}{'last 7 days':>14}")
    print(f"{'You (personal)':<26}{s['today']['personal']:>12,}{s['week']['personal']:>14,}")
    for k in sorted(k for k in s["week"] if k.startswith("team:")):
        print(f"{'  ' + k[5:]:<26}{s['today'].get(k, 0):>12,}{s['week'][k]:>14,}")
    print(f"{'Agents total':<26}{s['today']['agents']:>12,}{s['week']['agents']:>14,}")
    print(f"\nAgent caps: {b['agents_daily']:,}/day, {b['agents_weekly']:,}/week")
    print(f"Agent pool still available today: {pool:,}")
    print(f"Today's teams: {cfg['schedule'].get(DAYS[dt.date.today().weekday()], [])}")
    print(f"STOP flag: {'RAISED' if (HQ / 'STOP').exists() else 'down'}")
