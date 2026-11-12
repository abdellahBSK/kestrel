"""Claude Agent SDK adapter (spec 006): report a program built on the SDK with one line.

    from claude_agent_sdk import ClaudeAgentOptions, query
    from kestrel.adapters.claude_agent_sdk import hooks

    options = ClaudeAgentOptions(hooks=hooks(project="my-agent"))
    async for message in query(prompt="Fix the failing test", options=options):
        ...

The SDK hands its hook callbacks the same objects Claude Code hands command hooks, so this reuses
the Claude Code mapping: one prompt is one run, tool calls are actions, subagents are child
agents, tokens come from the transcript. Events go straight into this computer's store; run
`kestrel watch` to see them. Reporting never raises into your program.
"""

from __future__ import annotations

import time
from typing import Any

from kestrel.adapters import claude_code_hooks as cch

# Hook events the SDK forwards to Python callbacks. Session start and end are not among them in
# every SDK version, so a run is closed when the agent stops.
SDK_EVENTS = (
    "UserPromptSubmit",
    "PreToolUse",
    "PostToolUse",
    "PostToolUseFailure",
    "SubagentStart",
    "SubagentStop",
    "Notification",
    "Stop",
)


def callback(project: str | None = None, store=None):
    """A hook callback for the SDK that reports every event it receives. When the owner stops the
    run from the dashboard, or a budget cap is reached, it answers with the stop (spec 008)."""

    async def report(input_data: dict[str, Any], tool_use_id: str | None, context: Any) -> dict:
        try:
            event = dict(input_data)
            if tool_use_id and not event.get("tool_use_id"):
                event["tool_use_id"] = tool_use_id
            _, answer = cch.process(event, now=time.time(), store=store, project=project)
            return answer or {}
        except Exception:  # monitoring must never break the agent
            return {}

    return report


def hooks(project: str | None = None, *, events: tuple[str, ...] = SDK_EVENTS, store=None) -> dict:
    """`ClaudeAgentOptions(hooks=...)` that report to Kestrel. `project` defaults to the name of the
    repository (or folder) the agent works in. Merge with your own hooks by extending the lists."""
    from claude_agent_sdk import HookMatcher  # the SDK is your program's dependency, not Kestrel's

    report = callback(project, store)
    return {e: [HookMatcher(matcher="*" if e in cch.TOOL_EVENTS else None, hooks=[report])] for e in events}
