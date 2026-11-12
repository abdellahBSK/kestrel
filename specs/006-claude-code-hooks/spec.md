# 006: Claude Code and Claude Agent SDK adapters

- **Status:** Done
- **Created:** 2026-11-12
- **Parent:** [001](../001-kestrel-v0.1/spec.md) tasks T040, T041

## Problem

Kestrel can show Claude Code agents only when they are started by its own runner. Most people
run Claude Code themselves, in a terminal or an IDE, or embed it with the Claude Agent SDK. They
should see those sessions too, live, with their subagents, without changing how they work.

## Goals

- One command, `kestrel hook install`, and every Claude Code session on the machine reports.
- The same mapping for programs built on the Claude Agent SDK, with one line of code.
- Never slow down or break Claude Code: the hook fails silently and prints nothing.

## Non-goals

- Controlling sessions (stop, budgets): that is spec 001 T062–T063.
- Reading sessions from before the hook was installed.

## Mapping

Claude Code calls the hook on its lifecycle events. Each call carries the session id, a
`prompt_id` for the current turn, the transcript path and, inside a subagent, `agent_id` and
`agent_type`.

| Claude Code event | Kestrel events |
|---|---|
| `UserPromptSubmit` | `run.started` (one run per prompt; title = the prompt) and `agent.started` for the main agent. A still-open previous run is finished as `interrupted`. A background-task notification continues the previous run instead of starting one. |
| `PreToolUse` | `agent.action` with `status: running` and `call` = the tool-use id |
| `PostToolUse` / `PostToolUseFailure` | the same `call` with `ok` and a short result, or `error` and the error |
| `SubagentStart` | `agent.started` with `role` = the subagent type and `parent` = the main agent |
| `SubagentStop` | the subagent's tokens and messages from its transcript; `agent.finished` |
| `Stop` | the main agent's tokens and messages from the transcript; `agent.finished` and `run.finished: ok`, unless background tasks are still running |
| `Notification` | `agent.notice` (for example "Claude needs your permission to use Bash") |
| `SessionEnd` | `run.finished: interrupted` if a run is still open |

## Functional requirements

| ID | Requirement |
|---|---|
| FR-001 | `kestrel hook install` MUST add Kestrel's hooks to the Claude Code user settings (`--scope project` or `local` for one repository), keep every other setting and hook, back up the file first, and be safe to run twice. |
| FR-002 | `kestrel hook uninstall` MUST remove only Kestrel's hooks. |
| FR-003 | The hook MUST exit 0, print nothing to stdout and finish quickly whatever happens, so Claude Code never blocks or receives unexpected context. |
| FR-004 | The project MUST be the name of the repository (the folder containing `.git`) or of the working folder; `KESTREL_PROJECT` overrides it. |
| FR-005 | Events MUST have deterministic ids, so repeated or concurrent hook calls never duplicate anything. |
| FR-006 | Runs from Claude Code MUST declare a `heartbeat_timeout` of 300 seconds in `run.started`, because Claude Code sends nothing while a model writes a long answer or a tool runs. |
| FR-007 | Token events from these sessions MUST be marked `interactive`, so they show per project but are not added to the agents' total, which already counts your own Claude Code usage separately. |
| FR-008 | A Python program using the Claude Agent SDK MUST be able to report with `ClaudeAgentOptions(hooks=kestrel.adapters.claude_agent_sdk.hooks())`. |
| FR-009 | Sessions run by Kestrel's own runner MUST NOT be reported twice. (The runner starts Claude Code without user settings, so user hooks do not run.) |

## Acceptance criteria

1. **Given** the hook installed, **when** a user runs a prompt that starts a subagent which runs a
   command, **then** the dashboard shows a run titled with the prompt, a main agent with a child
   agent of the subagent's type, the command as an action, and tokens for both agents.
2. **Given** a failing command, **then** its action shows as an error with the error message.
3. **Given** the user presses Ctrl+C and quits mid-turn, **then** the run shows as interrupted.
4. **Given** the hook is installed twice, **then** the settings file has one set of Kestrel
   hooks; after uninstall it has none, and other hooks are untouched.
5. **Given** an unreadable store or malformed input, **then** the hook still exits 0 silently.
