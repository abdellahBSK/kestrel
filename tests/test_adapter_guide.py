"""The worked example in docs/adapters.md runs as written."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from kestrel.core import runs

DOC = Path(__file__).resolve().parent.parent / "docs" / "adapters.md"
TH = {"heartbeat_timeout": 45, "idle_after": 120, "stale_after": 600}


def python_blocks() -> list[str]:
    return re.findall(r"```python\n(.*?)```", DOC.read_text(encoding="utf-8"), re.S)


def test_the_agent_loop_example_reports_a_run(fresh_store):
    adapter, usage = python_blocks()[0], python_blocks()[1]
    replies = iter(
        [
            {
                "usage": {"input_tokens": 100, "output_tokens": 20},
                "model": "m",
                "text": "Looking.",
                "tool_calls": [{"name": "search", "arguments": {"q": "x"}}],
            },
            {"usage": {"input_tokens": 150, "output_tokens": 30}, "model": "m", "text": "Done.", "tool_calls": []},
        ]
    )
    scope = {
        "call_model": lambda messages: next(replies),
        "run_tool": lambda call: {"output": "3 results"},
        "messages": [],
    }
    exec(adapter, scope)  # noqa: S102 - the documented code, verbatim
    exec(usage, scope)  # noqa: S102

    [run] = fresh_store.runs("support-bot")
    f = runs.fold(fresh_store.run_events("support-bot", run["id"]), heartbeat=None, now=run["last"] + 1, th=TH)
    assert f["run"]["title"] == "Answer ticket #4521" and f["run"]["source"] == "my-agent"
    assert f["run"]["status"] == "ok"
    [agent] = f["agents"]
    assert agent["raw_tokens"]["input"] == 250 and agent["actions"] == 1 and agent["state"] == "finished"


def test_a_crash_in_the_loop_fails_the_run(fresh_store):
    adapter = python_blocks()[0]
    scope: dict = {}
    exec(adapter, scope)  # noqa: S102
    with pytest.raises(RuntimeError):
        with scope["reported_run"]("support-bot", "Broken", model="m"):
            raise RuntimeError("model API down")
    [run] = fresh_store.runs("support-bot")
    f = runs.fold(fresh_store.run_events("support-bot", run["id"]), heartbeat=None, now=run["last"] + 1, th=TH)
    assert f["run"]["status"] == "failed" and "model API down" in f["run"]["error"]
