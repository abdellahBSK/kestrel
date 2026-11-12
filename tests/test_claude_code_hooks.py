"""Claude Code hooks and Claude Agent SDK adapters (spec 006).

The hook inputs below have the shape Claude Code 2.1 sends (captured from real sessions).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import types
import uuid

import pytest

from conftest import usage_record, write_transcript
from kestrel.adapters import claude_code_hooks as cch
from kestrel.cli import hook as hook_cli
from kestrel.core import runs
from kestrel.core.events import EventError, normalize

T0 = 1_800_000_000.0
TH = {"heartbeat_timeout": 45, "idle_after": 120, "stale_after": 600}


def iso(t: float) -> str:
    import datetime as dt

    return dt.datetime.fromtimestamp(t, dt.UTC).isoformat().replace("+00:00", "Z")


class Session:
    """Feeds hook events for one fake Claude Code session into the adapter."""

    def __init__(self, store, tmp_path, project="shop"):
        self.store, self.sid, self.project = store, str(uuid.uuid4()), project
        self.transcript = tmp_path / f"{self.sid}.jsonl"
        self.cwd = str(tmp_path)

    def send(self, name: str, at: float, **fields) -> list[dict]:
        event = {"hook_event_name": name, "session_id": self.sid, "cwd": self.cwd, **fields}
        event.setdefault("transcript_path", str(self.transcript))
        return cch.handle(event, now=at, store=self.store, project=self.project)

    def runs(self) -> list[dict]:
        return self.store.runs(self.project)

    def fold(self, run: str, now: float) -> dict:
        return runs.fold(self.store.run_events(self.project, run), heartbeat=None, now=now, th=TH)


def test_a_prompt_with_a_subagent_becomes_one_run(fresh_store, tmp_path):
    s = Session(fresh_store, tmp_path)
    write_transcript(s.transcript, [usage_record(iso(T0 + 3), "m1", "claude-sonnet-5-5", inp=100, out=20)])
    sub_transcript = write_transcript(
        tmp_path / "agent-a1.jsonl",
        [
            usage_record(
                iso(T0 + 6),
                "m2",
                "claude-haiku-5-5",
                inp=50,
                out=10,
                content=[{"type": "text", "text": "The tests pass."}],
            )
        ],
    )
    s.send("UserPromptSubmit", T0, prompt_id="p1", prompt="Fix the login bug")
    s.send(
        "PreToolUse",
        T0 + 2,
        prompt_id="p1",
        tool_name="Agent",
        tool_use_id="t1",
        tool_input={"subagent_type": "tester", "description": "Run tests"},
    )
    s.send("SubagentStart", T0 + 3, prompt_id="p1", agent_id="a1", agent_type="tester")
    s.send(
        "PreToolUse",
        T0 + 4,
        prompt_id="p1",
        agent_id="a1",
        agent_type="tester",
        tool_name="Bash",
        tool_use_id="t2",
        tool_input={"command": "npm test"},
    )
    s.send(
        "PostToolUse",
        T0 + 5,
        prompt_id="p1",
        agent_id="a1",
        agent_type="tester",
        tool_name="Bash",
        tool_use_id="t2",
        tool_response={"stdout": "42 passed"},
    )
    s.send(
        "SubagentStop",
        T0 + 7,
        prompt_id="p1",
        agent_id="a1",
        agent_type="tester",
        agent_transcript_path=str(sub_transcript),
        last_assistant_message="The tests pass.",
    )
    s.send("PostToolUse", T0 + 8, prompt_id="p1", tool_name="Agent", tool_use_id="t1", tool_response="done")
    s.send("Stop", T0 + 9, prompt_id="p1", last_assistant_message="Fixed.", background_tasks=[])

    [run] = s.runs()
    f = s.fold(run["id"], T0 + 10)
    assert f["run"]["title"] == "Fix the login bug" and f["run"]["state"] == "finished" and f["run"]["status"] == "ok"
    agents = {a["id"]: a for a in f["agents"]}
    assert agents["main"]["role"] == "lead" and agents["main"]["state"] == "finished"
    assert agents["a1"]["role"] == "tester" and agents["a1"]["parent"] == "main" and agents["a1"]["state"] == "finished"
    assert agents["main"]["raw_tokens"]["input"] == 100 and agents["a1"]["raw_tokens"]["input"] == 50
    test_run = next(i for i in f["feed"] if i.get("tool") == "Bash")
    assert test_run["status"] == "ok" and test_run["result"] == "42 passed" and test_run["agent_id"] == "a1"
    said = [i["text"] for i in f["feed"] if i["kind"] == "say"]
    assert said.count("The tests pass.") == 1 and "Fixed." in said  # once, even though both sources had it


def test_tokens_are_marked_interactive(fresh_store, tmp_path):
    s = Session(fresh_store, tmp_path)
    write_transcript(s.transcript, [usage_record(iso(T0 + 1), "m1", inp=10)])
    s.send("UserPromptSubmit", T0, prompt_id="p1", prompt="hi")
    s.send("Stop", T0 + 2, prompt_id="p1")
    [(_, _, data)] = fresh_store.tokens_since(0)
    assert data["interactive"] is True


def test_a_failed_tool_is_an_error(fresh_store, tmp_path):
    s = Session(fresh_store, tmp_path)
    s.send("UserPromptSubmit", T0, prompt_id="p1", prompt="build it")
    s.send("PreToolUse", T0 + 1, prompt_id="p1", tool_name="Bash", tool_use_id="t1", tool_input={"command": "exit 3"})
    s.send("PostToolUseFailure", T0 + 2, prompt_id="p1", tool_name="Bash", tool_use_id="t1", error="Exit code 3")
    f = s.fold(s.runs()[0]["id"], T0 + 3)
    [action] = [i for i in f["feed"] if i["kind"] == "tool"]
    assert action["status"] == "error" and action["result"] == "Exit code 3"
    assert f["agents"][0]["errors"] == 1


def test_a_new_prompt_closes_an_unfinished_one(fresh_store, tmp_path):
    s = Session(fresh_store, tmp_path)
    s.send("UserPromptSubmit", T0, prompt_id="p1", prompt="first")
    s.send(
        "PreToolUse", T0 + 1, prompt_id="p1", tool_name="Bash", tool_use_id="t1", tool_input={"command": "sleep 100"}
    )
    s.send("UserPromptSubmit", T0 + 30, prompt_id="p2", prompt="second")  # the user pressed Esc and moved on
    first = s.fold("p1", T0 + 31)["run"]
    assert first["state"] == "finished" and first["status"] == "interrupted"
    assert s.fold("p2", T0 + 31)["run"]["state"] == "running"


def test_a_background_agent_reporting_back_continues_the_run(fresh_store, tmp_path):
    s = Session(fresh_store, tmp_path)
    s.send("UserPromptSubmit", T0, prompt_id="p1", prompt="audit the code")
    s.send("Stop", T0 + 5, prompt_id="p1", background_tasks=[])
    s.send("UserPromptSubmit", T0 + 20, prompt_id="p2", prompt="<task-notification>\n<task-id>a1</task-id>")
    s.send("PreToolUse", T0 + 21, prompt_id="p2", tool_name="Read", tool_use_id="t9", tool_input={"file_path": "x.py"})
    assert [r["id"] for r in s.runs()] == ["p1"]  # no extra run for the notification
    assert any(i.get("tool") == "Read" for i in s.fold("p1", T0 + 22)["feed"])


def test_stop_with_background_work_keeps_the_run_open(fresh_store, tmp_path):
    s = Session(fresh_store, tmp_path)
    s.send("UserPromptSubmit", T0, prompt_id="p1", prompt="review")
    s.send("Stop", T0 + 5, prompt_id="p1", background_tasks=[{"id": "a1"}])
    assert s.fold("p1", T0 + 6)["run"]["state"] == "running"


def test_ending_the_session_mid_prompt_interrupts_the_run(fresh_store, tmp_path):
    s = Session(fresh_store, tmp_path)
    s.send("UserPromptSubmit", T0, prompt_id="p1", prompt="long task")
    s.send("SessionEnd", T0 + 10, reason="prompt_input_exit")
    run = s.fold("p1", T0 + 11)["run"]
    assert run["status"] == "interrupted" and "prompt_input_exit" in run["summary"]


def test_claude_code_runs_tolerate_long_silences(fresh_store, tmp_path):
    s = Session(fresh_store, tmp_path)
    s.send("UserPromptSubmit", T0, prompt_id="p1", prompt="write a big file")
    assert s.fold("p1", T0 + 200)["run"]["state"] == "running"  # the model may write for minutes
    assert s.fold("p1", T0 + cch.HEARTBEAT_TIMEOUT + 1)["run"]["state"] == "lost"


def test_resent_hooks_add_nothing(fresh_store, tmp_path):
    s = Session(fresh_store, tmp_path)
    for _ in range(2):
        s.send("UserPromptSubmit", T0, prompt_id="p1", prompt="go")
        s.send("PreToolUse", T0 + 1, prompt_id="p1", tool_name="Bash", tool_use_id="t1", tool_input={"command": "ls"})
    assert len(fresh_store.run_events("shop", "p1")) == 3  # run.started, agent.started, the action


def test_hooks_installed_mid_session_start_a_run(fresh_store, tmp_path):
    s = Session(fresh_store, tmp_path)
    s.send("PreToolUse", T0, prompt_id="p7", tool_name="Read", tool_use_id="t1", tool_input={"file_path": "a.py"})
    [run] = s.runs()
    assert run["id"] == "p7" and s.fold("p7", T0 + 1)["run"]["title"] == "Claude Code session"


def test_the_project_is_the_repository(tmp_path, monkeypatch):
    monkeypatch.delenv("KESTREL_PROJECT", raising=False)
    repo = tmp_path / "my repo!"
    (repo / ".git").mkdir(parents=True)
    (repo / "src").mkdir()
    assert cch.project_for(str(repo / "src")) == "my-repo"
    monkeypatch.setenv("KESTREL_PROJECT", "override")
    assert cch.project_for(str(repo)) == "override"


def test_the_hook_never_fails_and_never_prints(home):
    for stdin in ("not json", "", '{"hook_event_name": "PreToolUse"}', "[1, 2]"):
        r = subprocess.run(
            [sys.executable, "-m", "kestrel", "--home", str(home), "hook", "claude-code"],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert r.returncode == 0 and r.stdout == ""


# ───────────────────────────── install ─────────────────────────────


def test_install_is_idempotent_and_keeps_other_settings(tmp_path):
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    mine = {"type": "command", "command": "echo mine"}
    settings.write_text(json.dumps({"model": "opus", "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [mine]}]}}))

    hook_cli.install("project", cwd=tmp_path)
    hook_cli.install("project", cwd=tmp_path)
    data = json.loads(settings.read_text())
    assert data["model"] == "opus"
    assert data["hooks"]["PreToolUse"][0]["hooks"] == [mine]
    ours = [e for entries in data["hooks"].values() for e in entries if hook_cli._ours(e)]
    assert len(ours) == len(cch.EVENTS)
    assert hook_cli.installed("project", cwd=tmp_path)

    assert hook_cli.uninstall("project", cwd=tmp_path)[1] is True
    data = json.loads(settings.read_text())
    assert data == {"model": "opus", "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [mine]}]}}
    assert hook_cli.uninstall("project", cwd=tmp_path)[1] is False


def test_install_refuses_a_broken_settings_file(tmp_path):
    settings = tmp_path / ".claude" / "settings.local.json"
    settings.parent.mkdir()
    settings.write_text("{ not json")
    with pytest.raises(SystemExit):
        hook_cli.install("local", cwd=tmp_path)
    assert settings.read_text() == "{ not json"


def test_the_hook_command_names_this_python_and_home(home):
    cmd = hook_cli.hook_command("C:\\Python\\python.exe")
    assert cmd.startswith('"C:/Python/python.exe" -m kestrel hook claude-code --home "')
    assert home.as_posix() in cmd


# ───────────────────────────── Claude Agent SDK ─────────────────────────────


@pytest.fixture
def fake_sdk(monkeypatch):
    class HookMatcher:
        def __init__(self, matcher=None, hooks=None):
            self.matcher, self.hooks = matcher, hooks

    monkeypatch.setitem(sys.modules, "claude_agent_sdk", types.SimpleNamespace(HookMatcher=HookMatcher))


def test_sdk_hooks_report_through_the_same_mapping(fake_sdk, fresh_store):
    import asyncio

    from kestrel.adapters import claude_agent_sdk

    hooks = claude_agent_sdk.hooks(project="sdk-app", store=fresh_store)
    assert hooks["PreToolUse"][0].matcher == "*" and hooks["Stop"][0].matcher is None
    report = hooks["UserPromptSubmit"][0].hooks[0]
    sid = str(uuid.uuid4())
    base = {"session_id": sid, "cwd": ".", "prompt_id": "p1"}
    asyncio.run(report({**base, "hook_event_name": "UserPromptSubmit", "prompt": "summarize"}, None, None))
    asyncio.run(report({**base, "hook_event_name": "PreToolUse", "tool_name": "Read", "tool_input": {}}, "t1", None))
    assert [r["id"] for r in fresh_store.runs("sdk-app")] == ["p1"]
    rows = fresh_store.run_events("sdk-app", "p1")
    assert any(r[1] == "agent.action" and r[3]["call"] == "t1" for r in rows)  # the SDK's tool_use_id is kept


def test_sdk_reporting_never_raises(fake_sdk, monkeypatch):
    import asyncio

    from kestrel.adapters import claude_agent_sdk

    monkeypatch.setattr(cch, "handle", lambda *a, **k: 1 / 0)
    report = claude_agent_sdk.callback()
    assert asyncio.run(report({"hook_event_name": "Stop"}, None, None)) == {}


# ───────────────────────────── format additions ─────────────────────────────


def test_heartbeat_timeout_is_validated():
    ok = normalize({"type": "run.started", "project": "p", "run": "r", "data": {"heartbeat_timeout": 300}})
    assert ok["data"]["heartbeat_timeout"] == 300
    for bad in (0, 2, -1, "300", True, 10**6):
        with pytest.raises(EventError):
            normalize({"type": "run.started", "project": "p", "run": "r", "data": {"heartbeat_timeout": bad}})


def test_interactive_tokens_are_not_counted_as_agent_usage(fresh_store, monkeypatch):
    import time

    from kestrel import meter
    from kestrel.api import server

    now = time.time()
    fresh_store.add(
        [
            normalize(
                {"type": "agent.tokens", "project": "p", "run": "r", "agent": "a", "ts": now, "data": {"input": 100}}
            ),
            normalize(
                {
                    "type": "agent.tokens",
                    "project": "p",
                    "run": "r",
                    "agent": "a",
                    "ts": now,
                    "data": {"input": 1000, "interactive": True},
                }
            ),
        ]
    )
    monkeypatch.setattr(server, "store", lambda: fresh_store)
    u = server.usage(meter.load_config())
    assert u["today"] == 100  # agents only
    assert u["proj_today"]["p"] == 1100  # the project still shows everything spent on it


def test_conftest_home_is_used(home):
    assert os.environ["KESTREL_HOME"] == str(home)
