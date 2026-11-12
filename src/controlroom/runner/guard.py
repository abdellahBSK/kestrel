"""Guard hook — runs before/after every tool call of every agent (lead and subagents).

PreToolUse : enforces the STOP switch, the token allowance and the Laws (no push, no
             attribution, stay in workspace, advisory = read-only). Fails closed.
PostToolUse: warns the agent to wrap up when it reaches the warning threshold.

Environment (set by kingdom.py for each run):
  AGENTHQ_TEAM, AGENTHQ_ALLOWANCE (tokens), AGENTHQ_SINCE (epoch seconds), AGENTHQ_MODE
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
    os.environ["CONTROLROOM_HOME"] = sys.argv[sys.argv.index("--home") + 1]
if not __package__:  # run by path as a hook script: make the package importable
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from controlroom import meter, paths, status  # noqa: E402

HQ = meter.HQ
TEAM = os.environ.get("AGENTHQ_TEAM", "")
TEAM_DIR = (HQ / "teams" / TEAM).resolve() if TEAM else None
ALLOWANCE = int(os.environ.get("AGENTHQ_ALLOWANCE", "0") or 0)
SINCE = float(os.environ.get("AGENTHQ_SINCE", "0") or 0)
MODE = os.environ.get("AGENTHQ_MODE", "build")

WRITE_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read", "Glob", "Grep"}

PR_MODE = os.environ.get("AGENTHQ_PR_MODE", "none")
TASK_BRANCH = r"(feat|fix|refactor|perf|test|docs|chore|security)/[A-Z]{3}-\d{3}-[a-z0-9][a-z0-9-]*"
PUSH_OK = re.compile(
    r"^git(\s+-C\s+(\"[^\"]+\"|'[^']+'|\S+))?\s+push\s+(-u\s+|--set-upstream\s+)?origin\s+"
    + TASK_BRANCH
    + r"(\s+2>&1)?$"
)
GH_OK = re.compile(r"^gh(\.exe)?\s+pr\s+(create|view|list|edit|comment|checks|diff|status)\b")
TOOLS = {(paths.RUNNER / "shoot.py").resolve(), (paths.RUNNER / "preview.py").resolve()}

BANNED_BASH = [
    (r"\b(vercel|netlify|firebase|flyctl|heroku|railway|wrangler|eas|expo\s+publish)\b", "Law 2: no deploy CLIs."),
    (r"\b(ssh|scp|sftp|rsync)\b", "Law 2: no remote shells or copies."),
    (r"\b(npm|yarn|pnpm)\s+publish\b|\btwine\s+upload\b|\bmvn\b[^|;&]*\bdeploy\b", "Law 2: no publishing."),
    (r"\bdocker\s+(push|login)\b", "Law 2: no registry pushes."),
    (r"\bgit\s+config\b[^|;&]*(--global|--system|user\.(name|email))", "Law 1: never change git identity/config."),
    (
        r"--no-verify|\bgit\b[^|;&]*(--force\b|\s-f\b)|\bgit\s+reset\s+--hard\b|\bgit\s+filter-|\bgit\s+rebase\b",
        "Law 4: no history rewriting or skipping hooks.",
    ),
    (r"(?i)co-authored-by|generated with \[?claude|noreply@anthropic", "Law 1: no Claude attribution."),
    (r"(?i)(\.ssh|\.aws|\.azure|\.gnupg|\.claude|\.credentials|id_rsa|id_ed25519)", "Law 3: sensitive location."),
    (r"(?i)(^|[\s'\"=/\\])\.env(?!\.example|\.sample|\.template)\b", "Law 3: never read or write .env files."),
    (r"(?i)\$HOME|%USERPROFILE%|\$env:USERPROFILE|(^|\s)~[/\\]", "Law 3: stay in your workspace."),
    (
        r"(?i)\b(curl|wget|invoke-webrequest|iwr|invoke-restmethod|irm)\b(?![^|;&]*\b(localhost|127\.0\.0\.1)\b)[^|;&]*https?://",
        "Law 2: no outbound HTTP except localhost (use the package manager to install deps).",
    ),
]

ABS_PATH = re.compile(r"(?i)(?<![\w.])(?:[a-z]:[\\/]|/[a-z]/)[^\s'\"|;&]*")


def out(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj))
    sys.exit(0)


def deny(reason: str) -> None:
    out(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"[Kingdom guard] {reason}",
            }
        }
    )


def halt(reason: str) -> None:
    out({"continue": False, "stopReason": f"[Kingdom guard] {reason}"})


def norm(p: str) -> Path | None:
    if not p:
        return None
    s = p.strip().strip("'\"")
    m = re.match(r"^/([a-zA-Z])/(.*)$", s)  # git-bash style /c/Users/...
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
                deny("Law 2: this team pushes nothing (PR MODE = none).")
            if not PUSH_OK.match(seg):
                deny(
                    "Law 2: only `git push -u origin <type>/<KEY>-<NNN>-<desc>` is allowed "
                    "(exact task branch name; no main, HEAD, force, delete or tags)."
                )
        if re.match(r"^gh(\.exe)?\s", seg_l):
            if PR_MODE == "none":
                deny("Law 2: this team opens no PRs (PR MODE = none).")
            if not GH_OK.match(seg):
                deny(
                    "Law 2: only `gh pr create|view|list|edit|comment|checks|diff|status` is allowed. "
                    "Merging, approving, marking ready and other gh commands are the King's."
                )
            if re.search(r"\bpr\s+create\b", seg) and PR_MODE == "draft" and "--draft" not in seg:
                deny("Law 2: PR MODE = draft, so open the PR with --draft.")
            if re.search(r"\bpr\s+edit\b", seg) and re.search(r"--base\b", seg):
                deny("Law 2: don't change a PR's base branch.")


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


def pre(event: dict) -> None:
    if (HQ / "STOP").exists():
        halt("The King raised the STOP flag. Stop now.")
    cfg = meter.load_config()
    if ALLOWANCE:
        u = used()
        if u >= ALLOWANCE * cfg["budget"].get("stop_at", 1.0):
            halt(f"Token allowance exhausted ({u:,}/{ALLOWANCE:,}). Run is over.")

    tool = event.get("tool_name", "")
    tin = event.get("tool_input") or {}
    if TEAM_DIR is None:
        return  # not an agent run (e.g. the King opened a session here): laws only via settings

    repo = TEAM_DIR / "repo"
    SESSION_DIRS[:] = session_dirs(event)
    if tool in WRITE_TOOLS:
        target = norm(tin.get("file_path") or tin.get("notebook_path") or "")
        if not allowed(target):
            deny(f"Law 3: you may only write inside {TEAM_DIR}.")
        if MODE == "advisory" and inside(target, repo):
            deny("Advisory mode: the repo is read-only. Write proposals in your report.")
        if target and target.name.startswith(".env") and not re.search(r"example|sample|template", target.name):
            deny("Law 3: never write .env files.")
        text = json.dumps(tin)
        if re.search(r"(?i)co-authored-by:\s*claude|generated with \[?claude code|noreply@anthropic", text):
            deny("Law 1: no Claude attribution in files.")
    elif tool in READ_TOOLS:
        target = norm(tin.get("file_path") or tin.get("path") or "")
        if target is not None and not allowed(target):
            deny(f"Law 3: you may only read inside {TEAM_DIR}.")
        if (
            target is not None
            and target.name.startswith(".env")
            and not re.search(r"example|sample|template", target.name)
        ):
            deny("Law 3: never read .env files.")
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
            if p is not None and not allowed(p) and not re.match(r"(?i)^/(dev/null|tmp)", m.group(0)):
                deny(f"Law 3: path outside your workspace: {m.group(0)}")
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
                "reason": f"[Kingdom guard] {len(busy)} agent(s) you started are still working "
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
