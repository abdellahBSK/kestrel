"""The guard hook, exercised the way Claude Code runs it: a separate process fed JSON on stdin."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys

import pytest

from conftest import ROOT, team_project_dir, usage_record, write_transcript
from controlroom import meter

GUARD = ROOT / "src" / "controlroom" / "runner" / "guard.py"


def run_guard(home, event: dict, user_home=None, **env) -> dict | None:
    e = {**os.environ, "AGENTHQ_TEAM": "sandbox", "AGENTHQ_MODE": "build", "AGENTHQ_PR_MODE": "ready", **env}
    if user_home is not None:  # where the guard looks for ~/.claude/projects
        e["HOME"] = e["USERPROFILE"] = str(user_home)
    r = subprocess.run(
        [sys.executable, str(GUARD), "--home", str(home)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env=e,
        timeout=60,
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout) if r.stdout.strip() else None


def pre(tool: str, **tool_input) -> dict:
    return {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}


def decision(out: dict | None) -> str:
    if out is None:
        return "allow"
    if out.get("continue") is False:
        return "halt"
    return out["hookSpecificOutput"].get("permissionDecision", "context")


@pytest.mark.parametrize(
    "command, env, expected",
    [
        ("git -C repo push -u origin feat/SBX-001-add-cli", {}, "allow"),
        ("git push origin main", {}, "deny"),
        ("git push --force -u origin feat/SBX-001-add-cli", {}, "deny"),
        ("git -C repo push -u origin feat/SBX-001-add-cli", {"AGENTHQ_PR_MODE": "none"}, "deny"),
        ("gh pr create --repo a/b --title x --body-file r.md", {}, "allow"),
        ("gh pr create --repo a/b --title x --body-file r.md", {"AGENTHQ_PR_MODE": "draft"}, "deny"),
        ("gh pr create --draft --repo a/b --title x --body-file r.md", {"AGENTHQ_PR_MODE": "draft"}, "allow"),
        ("gh pr merge 3 --repo a/b", {}, "deny"),
        ("gh api repos/a/b", {}, "deny"),
        ("cat .env", {}, "deny"),
        ("curl https://example.com", {}, "deny"),
        ("curl http://localhost:8080/health", {}, "allow"),
        ("ssh host", {}, "deny"),
        ('git commit -m "x" -m "Co-Authored-By: Claude"', {}, "deny"),
        ("npm test", {}, "allow"),
    ],
)
def test_bash_rules(home, command, env, expected):
    assert decision(run_guard(home, pre("Bash", command=command), **env)) == expected


def test_paths_must_stay_in_the_team_folder(home):
    team = home / "teams" / "sandbox"
    assert decision(run_guard(home, pre("Write", file_path=str(team / "repo" / "a.py")))) == "allow"
    assert decision(run_guard(home, pre("Write", file_path=str(home / "config.toml")))) == "deny"
    assert decision(run_guard(home, pre("Read", file_path=str(home / "teams" / "todo-api" / "STATE.md")))) == "deny"
    assert decision(run_guard(home, pre("Read", file_path=str(team / "repo" / ".env")))) == "deny"


def test_advisory_teams_cannot_write_to_the_repo(home):
    target = str(home / "teams" / "sandbox" / "repo" / "a.py")
    assert decision(run_guard(home, pre("Write", file_path=target), AGENTHQ_MODE="advisory")) == "deny"
    assert decision(run_guard(home, pre("Bash", command="git -C repo commit -m x"), AGENTHQ_MODE="advisory")) == "deny"


def test_stop_flag_halts_every_agent(home):
    (home / "STOP").write_text("test")
    try:
        assert decision(run_guard(home, pre("Bash", command="npm test"))) == "halt"
    finally:
        (home / "STOP").unlink()


def test_no_team_means_no_workspace_rules(home):
    out = run_guard(home, pre("Write", file_path=str(home / "config.toml")), AGENTHQ_TEAM="")
    assert decision(out) == "allow"


def test_budget_warning_then_hard_stop(home, tmp_path):
    projects = tmp_path / ".claude" / "projects"
    ts = dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z")
    write_transcript(team_project_dir(projects, "sandbox") / "s.jsonl", [usage_record(ts, "m1", inp=900)])
    since = str(dt.datetime.now().timestamp() - 3600)
    env = {"AGENTHQ_SINCE": since}

    post = {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}}
    warned = run_guard(home, post, user_home=tmp_path, AGENTHQ_ALLOWANCE="1000", **env)  # 90% used
    assert "BUDGET WARNING" in warned["hookSpecificOutput"]["additionalContext"]
    assert (
        decision(run_guard(home, pre("Bash", command="ls"), user_home=tmp_path, AGENTHQ_ALLOWANCE="1000", **env))
        == "allow"
    )
    assert (
        decision(run_guard(home, pre("Bash", command="ls"), user_home=tmp_path, AGENTHQ_ALLOWANCE="900", **env))
        == "halt"
    )


def test_guard_errors_fail_closed(home, tmp_path):
    broken = tmp_path / "broken-home"
    broken.mkdir()
    (broken / "config.toml").write_text("this is [not toml", encoding="utf-8")
    assert decision(run_guard(broken, pre("Bash", command="ls"))) == "deny"


def test_meter_sees_the_same_home_as_the_guard(home):
    assert meter.HQ == home.resolve()
