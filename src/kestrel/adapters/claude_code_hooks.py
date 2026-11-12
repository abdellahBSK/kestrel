"""Claude Code adapter for anyone's sessions: Claude Code hooks → Kestrel events (spec 006).

`kestrel hook install` registers `kestrel hook claude-code` for Claude Code's lifecycle events.
Claude Code then runs it with one JSON object on stdin per event; this module turns that into
events and writes them straight into the local store. The same `handle()` serves the Claude
Agent SDK adapter, whose hook callbacks receive the same objects.

One user prompt is one run. Tool calls are actions, subagents are child agents, and tokens and
the agents' messages come from the transcripts when each agent stops. The hook never prints and
never fails: a monitoring tool must not get in the way of the work it watches.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import uuid
from pathlib import Path

from kestrel import paths
from kestrel.core.events import EventError, normalize

SOURCE = "claude-code"
MAIN = "main"  # the agent the user talks to
HEARTBEAT_TIMEOUT = 300  # Claude Code is silent while a model writes a long answer or a tool runs
NOTIFICATION_PREFIX = "<task-notification>"  # a background agent finished: same run, not a new prompt
EVENTS = (  # Claude Code hook events this adapter handles
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "SubagentStart",
    "SubagentStop",
    "Stop",
    "Notification",
    "SessionEnd",
)
TOOL_EVENTS = ("PreToolUse", "PostToolUse", "PostToolUseFailure")


def state_dir() -> Path:
    return paths.HOME / "data" / "claude-code"


# ───────────────────────────── helpers ─────────────────────────────


def _short(text, n: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _ident(value: str) -> str:
    """Something usable as a project, run or agent id (see docs/events.md)."""
    s = re.sub(r"[^A-Za-z0-9._:@/+-]+", "-", str(value)).strip("-._:@/+")[:128]
    return s or "unknown"


def project_for(cwd: str) -> str:
    """The repository's folder name (the folder holding .git), else the working folder's name."""
    if os.environ.get("KESTREL_PROJECT"):
        return _ident(os.environ["KESTREL_PROJECT"])
    here = Path(cwd or ".").resolve()
    for p in (here, *here.parents):
        if (p / ".git").exists():
            return _ident(p.name)
    return _ident(here.name)


def describe(tool: str, inp: dict, cwd: str) -> str:
    from kestrel.adapters.claude_code import describe as _describe

    return _describe(tool, inp or {}, str(cwd or "").replace("\\", "/"))


def _result(response) -> str:
    """A short, readable result from a tool's response."""
    if isinstance(response, dict):
        for key in ("stdout", "content", "result", "output", "message"):
            v = response.get(key)
            if isinstance(v, str) and v.strip():
                return _short(v[-400:], 300)
            if isinstance(v, list):  # content blocks
                text = " ".join(c.get("text", "") for c in v if isinstance(c, dict))
                if text.strip():
                    return _short(text[-400:], 300)
        if response.get("stderr"):
            return _short(response["stderr"][-400:], 300)
        if "filePath" in response or "file" in response:
            return ""
        return ""
    if isinstance(response, str):
        return _short(response[-400:], 300)
    return ""


# ───────────────────────────── per-session state ─────────────────────────────


class Session:
    """A little state per session: which run is open, and how far each transcript was read.

    Hooks for one session can run at the same time (parallel subagents). Every write is atomic,
    and losing an update only means re-reading a transcript, which ids make harmless.
    """

    def __init__(self, session_id: str, cwd: str):
        self.id = _ident(session_id)
        self.path = state_dir() / f"{self.id}.json"
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        self.project = data.get("project") or project_for(cwd)
        self.runs: list = data.get("runs") or []  # [run id, start ts], oldest first
        self.open = data.get("open")  # the run in progress, if any
        self.alias: dict = data.get("alias") or {}  # prompt id → run it continues
        self.synced: dict = data.get("synced") or {}  # transcript path → last ts read
        self.said: list = data.get("said") or []  # keys of messages already reported
        self.stopped: dict = data.get("stopped") or {}  # run or "run/agent" → why it was stopped

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "project": self.project,
            "runs": self.runs[-200:],
            "open": self.open,
            "alias": dict(list(self.alias.items())[-50:]),
            "synced": self.synced,
            "said": self.said[-300:],
            "stopped": dict(list(self.stopped.items())[-50:]),
            "updated": time.time(),
        }
        tmp = self.path.with_name(f"{self.path.name}.{uuid.uuid4().hex[:8]}.tmp")
        tmp.write_text(json.dumps(data), encoding="utf-8")
        os.replace(tmp, self.path)

    def run_at(self, ts: float) -> str | None:
        """The run that was going on at `ts`."""
        best = None
        for rid, start in self.runs:
            if start <= ts + 1:
                best = rid
        return best

    def heard(self, text: str) -> bool:
        """Whether this message was reported already; remembers it either way."""
        key = hashlib.sha1(_short(text, 600).encode("utf-8")).hexdigest()[:16]
        if key in self.said:
            return True
        self.said.append(key)
        return False

    @property
    def last(self) -> str | None:
        return self.runs[-1][0] if self.runs else None


# ───────────────────────────── the mapping ─────────────────────────────


def handle(event: dict, *, now: float | None = None, store=None, project: str | None = None) -> list[dict]:
    """Turn one Claude Code hook input into stored Kestrel events. Returns the stored events."""
    return process(event, now=now, store=store, project=project)[0]


def stop_output(stop, whole_run: bool) -> dict:
    """What a PreToolUse hook answers to stop an agent: refuse the tool call, and for a whole run
    (or the main agent) also end the session. Claude Code and the Agent SDK read the same shape."""
    why = f"Stopped from Kestrel: {stop.reason}."
    deny = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": why
            + ("" if whole_run else " Do not continue this task: report what you have done so far, and stop."),
        }
    }
    return {**deny, "continue": False, "stopReason": why} if whole_run else deny


def process(
    event: dict, *, now: float | None = None, store=None, project: str | None = None
) -> tuple[list[dict], dict | None]:
    """(stored events, the hook's answer to Claude Code or None). The answer is only ever a stop."""
    now = time.time() if now is None else now
    name = event.get("hook_event_name", "")
    sid = event.get("session_id")
    if name not in EVENTS or not sid:
        return [], None
    s = Session(sid, event.get("cwd", ""))
    if project:
        s.project = _ident(project)
    out: list[dict] = []
    answer: dict | None = None
    dirty = False

    def emit(typ: str, run: str, eid: str, agent: str | None = None, ts: float | None = None, **data) -> None:
        out.append(
            {
                "id": f"cch:{s.id}:{eid}",
                "type": typ,
                "project": s.project,
                "run": run,
                "agent": agent,
                "ts": now if ts is None else ts,
                "data": {k: v for k, v in data.items() if v not in (None, "")},
            }
        )

    def start_run(run: str, title: str) -> None:
        nonlocal dirty
        if s.open and s.open != run:  # the previous prompt never finished: interrupted
            emit("agent.finished", s.open, f"{s.open}:main:interrupted", MAIN, status="interrupted")
            emit("run.finished", s.open, f"{s.open}:interrupted", status="interrupted")
        if run not in {r for r, _ in s.runs}:
            s.runs.append([run, now])
            emit(
                "run.started",
                run,
                f"{run}:start",
                title=_short(title, 200) or "Claude Code session",
                source=SOURCE,
                heartbeat_timeout=HEARTBEAT_TIMEOUT,
            )
            emit("agent.started", run, f"{run}:main:start", MAIN, role="lead", description="Claude Code")
        s.open = run
        dirty = True

    def current_run() -> str:
        """The run for this event; starts one if the hook was installed mid-session."""
        pid = event.get("prompt_id")
        run = s.alias.get(pid) if pid else None
        run = run or (_ident(pid) if pid else None) or s.open or s.last
        if run is None or run not in {r for r, _ in s.runs}:
            run = run or _ident(f"{s.id}-1")
            start_run(run, "Claude Code session")
        elif s.open != run:
            nonlocal dirty
            s.open, dirty = run, True
        return run

    def agent_of() -> str:
        aid = event.get("agent_id")
        return _ident(aid) if aid else MAIN

    def ensure_agent(run: str, aid: str) -> None:
        if aid != MAIN:  # deterministic id: emitting it again is free
            emit(
                "agent.started", run, f"{run}:{aid}:start", aid, role=event.get("agent_type") or "subagent", parent=MAIN
            )

    def sync_transcript(path: str | None, run_hint: str, aid: str) -> None:
        """Tokens and messages since the last read, each assigned to the run it happened in."""
        nonlocal dirty
        if not path or not Path(path).is_file():
            return
        from kestrel.adapters.claude_code import transcript_events

        since = float(s.synced.get(path, 0))
        events, info = transcript_events(Path(path), s.project, s.id, aid, "")
        for e in events:
            if e["ts"] <= since - 2 or e["type"] not in ("agent.tokens", "agent.message"):
                continue
            run = s.run_at(e["ts"]) or run_hint
            data = dict(e["data"])
            if e["type"] == "agent.message" and s.heard(data.get("text", "")):
                continue
            if e["type"] == "agent.tokens":
                data["interactive"] = True
            out.append({**e, "id": "cch:" + e["id"], "run": run, "data": data})
        if info["last"]:
            s.synced[path] = info["last"]
            dirty = True

    def last_words(run: str, aid: str) -> None:
        """The agent's final message, which may not be in its transcript yet when it stops."""
        nonlocal dirty
        text = event.get("last_assistant_message")
        if text and str(text).strip() and not s.heard(str(text)):
            key = s.said[-1]
            emit("agent.message", run, f"{run}:{aid}:said:{key}", aid, text=_short(text, 600))
            dirty = True

    if name == "UserPromptSubmit":
        prompt = str(event.get("prompt") or "")
        pid = event.get("prompt_id")
        if prompt.lstrip().startswith(NOTIFICATION_PREFIX) and s.last:
            if pid:  # a background agent reported back: the same piece of work goes on
                s.alias[pid] = s.last
            s.open, dirty = s.last, True
        else:
            start_run(_ident(pid) if pid else _ident(f"{s.id}-{len(s.runs) + 1}"), prompt)

    elif name in TOOL_EVENTS:
        run, aid = current_run(), agent_of()
        ensure_agent(run, aid)
        tool = event.get("tool_name") or "tool"
        call = event.get("tool_use_id") or ""
        if name == "PreToolUse":
            stop = _should_stop(store, s.project, run, aid, now)
            detail = describe(tool, event.get("tool_input") or {}, event.get("cwd", ""))
            eid = call or uuid.uuid4().hex
            if stop:
                whole = stop.scope == "run" or aid == MAIN
                answer = stop_output(stop, whole)
                s.stopped[run if whole else f"{run}/{aid}"] = stop.reason
                dirty = True
                emit(
                    "agent.action",
                    run,
                    f"{eid}:pre",
                    aid,
                    tool=tool,
                    call=call or None,
                    detail=detail,
                    status="blocked",
                    result=f"Stopped: {stop.reason}",
                )
                emit("agent.notice", run, f"{run}:{aid}:stopped", aid, level="critical", text=f"Stopped: {stop.reason}")
            else:
                emit(
                    "agent.action",
                    run,
                    f"{eid}:pre",
                    aid,
                    tool=tool,
                    call=call or None,
                    detail=detail,
                    status="running",
                )
        elif call:
            failed = name == "PostToolUseFailure"
            result = _short(event.get("error"), 300) if failed else _result(event.get("tool_response"))
            emit(
                "agent.action",
                run,
                f"{call}:post",
                aid,
                tool=tool,
                call=call,
                status="error" if failed else "ok",
                result=result,
            )

    elif name == "SubagentStart":
        run, aid = current_run(), agent_of()
        ensure_agent(run, aid)

    elif name == "SubagentStop":
        run, aid = current_run(), agent_of()
        ensure_agent(run, aid)
        sync_transcript(event.get("agent_transcript_path"), run, aid)
        last_words(run, aid)
        emit(
            "agent.finished",
            run,
            f"{run}:{aid}:finished:{int(now)}",
            aid,
            ts=now + 0.001,
            status="stopped" if f"{run}/{aid}" in s.stopped or run in s.stopped else "ok",
            summary=_short(s.stopped.get(f"{run}/{aid}") or event.get("last_assistant_message"), 300),
        )

    elif name == "Stop":
        run = current_run()
        sync_transcript(event.get("transcript_path"), run, MAIN)
        last_words(run, MAIN)
        stopped = s.stopped.get(run)
        if stopped or not event.get("background_tasks"):  # nothing left running in the background: done
            summary = _short(stopped or event.get("last_assistant_message"), 300)
            status = "stopped" if stopped else "ok"
            emit(
                "agent.finished",
                run,
                f"{run}:main:finished:{int(now)}",
                MAIN,
                ts=now + 0.001,
                status=status,
                summary=summary,
            )
            emit("run.finished", run, f"{run}:finished:{int(now)}", ts=now + 0.002, status=status, summary=summary)
            s.open, dirty = None, True

    elif name == "Notification":
        run = current_run()
        text = _short(event.get("message") or "Claude Code needs your attention", 300)
        emit("agent.notice", run, f"{run}:notice:{int(now)}", MAIN, level="warning", text=text)

    elif name == "SessionEnd":
        if s.open:
            run = s.open
            sync_transcript(event.get("transcript_path"), run, MAIN)
            why = _short(event.get("reason"), 60)
            stopped = s.stopped.get(run)
            status = "stopped" if stopped else "interrupted"
            summary = _short(stopped, 300) if stopped else (f"Session ended ({why})" if why else None)
            emit("agent.finished", run, f"{run}:main:end", MAIN, ts=now + 0.001, status=status)
            emit("run.finished", run, f"{run}:end", ts=now + 0.002, status=status, summary=summary)
            s.open, dirty = None, True

    stored = _store(out, store, now)
    if dirty:
        s.save()
    return stored, answer


def _should_stop(store, project: str, run: str, agent: str, now: float):
    """A stop requested from the dashboard, or a budget cap reached (kestrel.control)."""
    from kestrel import meter
    from kestrel.control import check

    if store is None:
        from kestrel.storage.store import open_store

        store = open_store()
    return check(store, project, run, agent, meter.load_config(), now)


def _store(raw: list[dict], store, now: float) -> list[dict]:
    good = []
    for r in raw:
        try:
            good.append(normalize(r, now=now + 1))
        except EventError:
            continue
    if good:
        if store is None:
            from kestrel.storage.store import open_store

            store = open_store()
        store.add(good)
    return good


def main(argv: list[str] | None = None) -> int:
    """`kestrel hook claude-code`: read one hook input from stdin. Always exits 0. It prints
    nothing, except the answer that stops an agent when a stop was requested or a cap reached."""
    try:
        raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")  # tolerate a BOM (PowerShell pipes)
        event = json.loads(raw) if raw.strip() else {}
        if isinstance(event, dict):
            _, answer = process(event)
            if answer:
                sys.stdout.write(json.dumps(answer))
    except Exception as e:  # never break Claude Code; leave a trace for debugging
        try:
            log = state_dir() / "errors.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {type(e).__name__}: {e}\n")
        except OSError:
            pass
    return 0
