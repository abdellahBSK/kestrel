"""Guard hook — runs before/after every tool call of every agent (lead and subagents).

PreToolUse : enforces the STOP switch, the token allowance and the rules (no push, stay in the
             workspace, advisory = read-only, optionally no AI attribution). Fails closed.
PostToolUse: warns the agent to wrap up when it reaches the warning threshold.

Environment (set by orchestrator.py for each run):
  KESTREL_TEAM, KESTREL_ALLOWANCE (tokens), KESTREL_SINCE (epoch seconds), KESTREL_MODE
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path

if "--home" in sys.argv:  # the hook command passes the home folder explicitly
    os.environ["KESTREL_HOME"] = sys.argv[sys.argv.index("--home") + 1]
if not __package__:  # run by path as a hook script: make the package importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from kestrel import meter, paths  # noqa: E402
from kestrel.core import status  # noqa: E402

HQ = meter.HQ
TEAM = os.environ.get("KESTREL_TEAM", "")
TEAM_DIR = (HQ / "teams" / TEAM).resolve() if TEAM else None
ALLOWANCE = int(os.environ.get("KESTREL_ALLOWANCE", "0") or 0)
SINCE = float(os.environ.get("KESTREL_SINCE", "0") or 0)
MODE = os.environ.get("KESTREL_MODE", "build")
HIDE_ATTRIBUTION = os.environ.get("KESTREL_HIDE_ATTRIBUTION") == "1"  # [pipeline] hide_ai_attribution

WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read", "Glob", "Grep"}

PR_MODE = os.environ.get("KESTREL_PR_MODE", "none")
TASK_BRANCH = r"(feat|fix|refactor|perf|test|docs|chore|security)/[A-Z]{3}-\d{3}-[a-z0-9][a-z0-9-]*"
PUSH_OK = re.compile(
    r"^git(\s+-C\s+(\"[^\"]+\"|'[^']+'|\S+))?\s+push\s+(-u\s+|--set-upstream\s+)?origin\s+"
    + TASK_BRANCH
    + r"(\s+2>&1)?$"
)
GH_OK = re.compile(r"^gh(\.exe)?\s+pr\s+(create|view|list|edit|comment|checks|diff|status)\b")
TOOLS = {(paths.RUNNER / "shoot.py").resolve(), (paths.RUNNER / "preview.py").resolve()}

BANNED_BASH = [
    (r"\b(vercel|netlify|firebase|flyctl|heroku|railway|wrangler|eas|expo\s+publish)\b", "Rule 2: no deploy CLIs."),
    (r"\b(ssh|scp|sftp|rsync)\b", "Rule 2: no remote shells or copies."),
    (r"\b(npm|yarn|pnpm)\s+publish\b|\btwine\s+upload\b|\bmvn\b[^|;&]*\bdeploy\b", "Rule 2: no publishing."),
    (r"\bdocker\s+(push|login)\b", "Rule 2: no registry pushes."),
    (r"\bgit\s+config\b[^|;&]*(--global|--system|user\.(name|email))", "Rule 1: never change git identity/config."),
    (
        r"--no-verify|\bgit\b[^|;&]*(--force\b|\s-f\b)|\bgit\s+reset\s+--hard\b|\bgit\s+filter-|\bgit\s+rebase\b",
        "Rule 4: no history rewriting or skipping hooks.",
    ),
    (r"(?i)(\.ssh|\.aws|\.azure|\.gnupg|\.claude|\.credentials|id_rsa|id_ed25519)", "Rule 3: sensitive location."),
    (r"(?i)(^|[\s'\"=/\\])\.env(?!\.example|\.sample|\.template)\b", "Rule 3: never read or write .env files."),
    (r"(?i)\$HOME|%USERPROFILE%|\$env:USERPROFILE|(^|\s)~[/\\]", "Rule 3: stay in your workspace."),
    (
        r"(?i)\b(curl|wget|invoke-webrequest|iwr|invoke-restmethod|irm)\b(?![^|;&]*\b(localhost|127\.0\.0\.1)\b)[^|;&]*https?://",
        "Rule 2: no outbound HTTP except localhost (use the package manager to install deps).",
    ),
]

if HIDE_ATTRIBUTION:
    BANNED_BASH.append(
        (r"(?i)co-authored-by|generated with \[?claude|noreply@anthropic", "Rule 1: no Claude attribution.")
    )

# Absolute paths in a shell command: Windows (C:\..., C:/...), Git Bash (/c/...), and the POSIX
# top-level folders where homes, system files and mounted disks live. Not every word that starts
# with "/": `curl http://localhost:3000/api` or `grep '/api/users'` are not file paths.
ABS_PATH = re.compile(
    r"(?<![\w.:/])(?:[a-zA-Z]:[\\/]|/[a-zA-Z]/"
    r"|/(?:home|Users|root|etc|var|opt|usr|mnt|media|srv|private|Volumes|proc|sys|dev|tmp|Library|System)(?:/|\b))"
    r"[^\s'\"|;&]*"
)
HARMLESS_PATH = re.compile(r"^/(dev/(null|stdout|stderr|stdin|tty)|tmp)\b")


def out(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj))
    sys.exit(0)


def deny(reason: str) -> None:
    out(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"[Kestrel guard] {reason}",
            }
        }
    )


def halt(reason: str) -> None:
    out({"continue": False, "stopReason": f"[Kestrel guard] {reason}"})


def norm(p: str) -> Path | None:
    if not p:
        return None
    s = p.strip().strip("'\"")
    m = re.match(r"^/([a-zA-Z])/(.*)$", s) if sys.platform == "win32" else None  # Git Bash: /c/Users/...
    if m:
        s = f"{m.group(1)}:/{m.group(2)}"
    try:
        path = Path(s)
        if not path.is_absolute():
            path = Path(os.getcwd()) / path
        return path.resolve()
    except (OSError, ValueError):
        return None


def inside(path: Path | None, root: Path | None) -> bool:
    if path is None or root is None:
        return False
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


SESSION_DIRS: list[Path] = []  # the run's own Claude temp folder (scratchpad, background-task output)


def session_dirs(event: dict) -> list[Path]:
    sid = str(event.get("session_id") or "")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", sid):
        return []
    import tempfile

    base = Path(tempfile.gettempdir()) / "claude"
    try:
        return [d.resolve() for d in base.glob(f"*/{sid}") if d.is_dir()]
    except OSError:
        return []


def allowed(path: Path | None) -> bool:
    """Inside the team folder, or inside this run's own temp folder."""
    return inside(path, TEAM_DIR) or any(inside(path, d) for d in SESSION_DIRS)


def used() -> int:
    if not TEAM:
        return 0
    cfg = meter.load_config()
    since = dt.datetime.fromtimestamp(SINCE).astimezone() if SINCE else meter.start_of_today()
    return meter.team_used_since(TEAM, since, cfg)


def segments(cmd: str) -> list[str]:
    """Split a shell command line into simple commands (&&, ||, ;, |, newlines)."""
    return [s.strip() for s in re.split(r"&&|\|\||[;|\n]", cmd) if s.strip()]


def check_push_and_gh(cmd: str) -> None:
    for seg in segments(cmd):
        seg_l = seg.lower()
        if re.search(r"\bgit\b", seg_l) and re.search(r"\bpush\b", seg_l) and not re.search(r"\bstash\b", seg_l):
            if PR_MODE == "none":
                deny("Rule 2: this team pushes nothing (PR MODE = none).")
            if not PUSH_OK.match(seg):
                deny(
                    "Rule 2: only `git push -u origin <type>/<KEY>-<NNN>-<desc>` is allowed "
                    "(exact task branch name; no main, HEAD, force, delete or tags)."
                )
        if re.match(r"^gh(\.exe)?\s", seg_l):
            if PR_MODE == "none":
                deny("Rule 2: this team opens no PRs (PR MODE = none).")
            if not GH_OK.match(seg):
                deny(
                    "Rule 2: only `gh pr create|view|list|edit|comment|checks|diff|status` is allowed. "
                    "Merging, approving, marking ready and other gh commands are the owner's."
                )
            if re.search(r"\bpr\s+create\b", seg) and PR_MODE == "draft" and "--draft" not in seg:
                deny("Rule 2: PR MODE = draft, so open the PR with --draft.")
            if re.search(r"\bpr\s+edit\b", seg) and re.search(r"--base\b", seg):
                deny("Rule 2: don't change a PR's base branch.")


# Workflow order: a role may not start while a role it depends on is still running.
WAITS_FOR = {"tester": ("developer",), "qa": ("developer", "tester")}


def running_subagents(event: dict, stale_after: float) -> list[str]:
    """Roles of this run's subagents that started but have not reported back yet (stale ones excluded)."""
    tp = event.get("transcript_path")
    if not tp:
        return []
    folder = Path(tp).with_suffix("") / "subagents"
    if not folder.is_dir():
        return []
    now, roles = time.time(), []
    for mf in folder.glob("*.meta.json"):
        meta = status.read_json(mf) or {}
        if meta.get("finished"):
            continue
        transcript = mf.with_name(mf.name[: -len(".meta.json")] + ".jsonl")
        try:
            last = (transcript if transcript.exists() else mf).stat().st_mtime
        except OSError:
            continue
        if now - last < stale_after:
            roles.append(str(meta.get("agentType") or "subagent"))
    return roles


def check_order(tin: dict, event: dict, cfg: dict) -> None:
    """QA judges a finished change and its test results, so it waits for the tester and developer."""
    want = str(tin.get("subagent_type", ""))
    deps = WAITS_FOR.get(want)
    if not deps or not cfg.get("pipeline", {}).get("enforce_order", True):
        return
    try:
        busy = sorted({r for r in running_subagents(event, status.thresholds(cfg)["stale_after"]) if r in deps})
    except Exception:  # a workflow rule, not a safety one: never block work because the check broke
        return
    if busy:
        deny(
            f"Order: wait for the {' and '.join(busy)} to finish and report back before starting {want}. "
            f"{want} must see the finished change and its results."
        )


def stop_requested(event: dict, cfg: dict) -> None:
    """A stop the owner asked for on the dashboard, or a project budget cap (kestrel.control).
    The runner's run is the Claude Code session; its subagents are `agent-<id>` (adapters/claude_code)."""
    if not TEAM or not event.get("session_id"):
        return
    try:
        from kestrel.control import check
        from kestrel.storage.store import open_store

        aid = event.get("agent_id")
        stop = check(open_store(), TEAM, str(event["session_id"]), f"agent-{aid}" if aid else "lead", cfg)
    except Exception:
        return  # the store is unavailable: the other rules still apply
    if stop is None:
        return
    if stop.scope == "run" or not event.get("agent_id"):
        halt(f"Stopped from the dashboard: {stop.reason}. Stop now.")
    deny(f"Stopped from the dashboard: {stop.reason}. Report what you have done so far, and stop.")


def pre(event: dict) -> None:
    if (HQ / "STOP").exists():
        halt("The owner raised the STOP flag. Stop now.")
    cfg = meter.load_config()
    if ALLOWANCE:
        u = used()
        if u >= ALLOWANCE * cfg["budget"].get("stop_at", 1.0):
            halt(f"Token allowance exhausted ({u:,}/{ALLOWANCE:,}). Run is over.")
    stop_requested(event, cfg)

    tool = event.get("tool_name", "")
    tin = event.get("tool_input") or {}
    if TEAM_DIR is None:
        return  # not an agent run (e.g. the owner opened a session here): rules only via settings

    repo = TEAM_DIR / "repo"
    SESSION_DIRS[:] = session_dirs(event)
    if tool in WRITE_TOOLS:
        target = norm(tin.get("file_path") or tin.get("notebook_path") or "")
        if not allowed(target):
            deny(f"Rule 3: you may only write inside {TEAM_DIR}.")
        if MODE == "advisory" and inside(target, repo):
            deny("Advisory mode: the repo is read-only. Write proposals in your report.")
        if target and target.name.startswith(".env") and not re.search(r"example|sample|template", target.name):
            deny("Rule 3: never write .env files.")
        text = json.dumps(tin)
        if HIDE_ATTRIBUTION and re.search(
            r"(?i)co-authored-by:\s*claude|generated with \[?claude code|noreply@anthropic", text
        ):
            deny("Rule 1: no Claude attribution in files.")
    elif tool in READ_TOOLS:
        target = norm(tin.get("file_path") or tin.get("path") or "")
        if target is not None and not allowed(target):
            deny(f"Rule 3: you may only read inside {TEAM_DIR}.")
        if (
            target is not None
            and target.name.startswith(".env")
            and not re.search(r"example|sample|template", target.name)
        ):
            deny("Rule 3: never read .env files.")
    elif tool in ("Bash", "PowerShell"):
        cmd = tin.get("command", "")
        for pattern, reason in BANNED_BASH:
            if re.search(pattern, cmd):
                deny(reason)
        check_push_and_gh(cmd)
        for m in ABS_PATH.finditer(cmd):
            p = norm(m.group(0))
            if p is not None and p in TOOLS:
                continue
            if p is not None and not allowed(p) and not HARMLESS_PATH.match(m.group(0)):
                deny(f"Rule 3: path outside your workspace: {m.group(0)}")
        if MODE == "advisory" and re.search(r"\bgit\b[^|;&]*\b(commit|merge|cherry-pick|am|apply|stash)\b", cmd):
            deny("Advisory mode: no commits.")
    elif tool in ("Agent", "Task"):
        check_order(tin, event, cfg)
    elif tool in ("WebFetch", "WebSearch"):
        deny("Web access is disabled for agents.")


def post(event: dict) -> None:
    if not (TEAM and ALLOWANCE):
        sys.exit(0)
    cfg = meter.load_config()
    u = used()
    if u >= ALLOWANCE * cfg["budget"].get("warn_at", 0.8):
        msg = (
            f"BUDGET WARNING: {u:,} of {ALLOWANCE:,} tokens used ({u / ALLOWANCE:.0%}). "
            "Start no new task. Commit finished work, update BACKLOG.md and STATE.md, "
            "write your report, then end the run. Subagents: finish and report back now."
        )
        out({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}})
    sys.exit(0)


def stop(event: dict) -> None:
    """Keep the lead from ending the run while agents it started are still working.

    When the run ends its agents are stopped mid-task and their work is lost. This nudges the lead
    once: Claude Code sets `stop_hook_active` on the retry, and then we let it end.
    """
    if not TEAM or event.get("stop_hook_active") or (HQ / "STOP").exists():
        sys.exit(0)
    cfg = meter.load_config()
    if ALLOWANCE and used() >= ALLOWANCE * cfg["budget"].get("stop_at", 1.0):
        sys.exit(0)
    busy = running_subagents(event, status.thresholds(cfg)["stale_after"])
    if busy:
        out(
            {
                "decision": "block",
                "reason": f"[Kestrel guard] {len(busy)} agent(s) you started are still working "
                f"({', '.join(sorted(busy))}). Wait for their results before you end the run: when the run "
                "ends they are stopped and their work is lost. Then commit, update STATE.md and write "
                "your report.",
            }
        )
    sys.exit(0)


def main() -> None:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except ValueError:
        event = {}
    name = event.get("hook_event_name", "PreToolUse")
    try:
        if name == "PostToolUse":
            post(event)
        elif name == "Stop":
            stop(event)
        else:
            pre(event)
    except SystemExit:
        raise
    except Exception as e:  # fail closed for pre, open for post and stop
        if name in ("PostToolUse", "Stop"):
            sys.exit(0)
        deny(f"guard error ({type(e).__name__}: {e}); action refused for safety.")
    sys.exit(0)


if __name__ == "__main__":
    main()
