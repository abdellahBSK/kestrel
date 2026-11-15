# 011: A faster Claude Code hook

- **Status:** Draft
- **Created:** 2026-11-15
- **Answers:** [Roadmap](../ROADMAP.md) L2
- **Target:** v0.2

## Problem

The Claude Code hook starts a Python process for every hook event: about 130 ms on Windows, of
which about 85 ms is Python starting and the rest importing and writing. A tool call fires two
hooks, so a session with 500 tool calls spends over two minutes in Kestrel. Users notice
latency in an interactive tool, and some will uninstall over it.

## Goals

- The hook adds **under 20 ms** to a tool call in the common case, on every OS.
- No behavior changes: same events, same stops, same failure safety (spec 006, 008).

## Non-goals

- A compiled binary distributed separately. Kestrel stays one Python package (constitution V).

## Functional requirements

| ID | Requirement |
|---|---|
| FR-001 | The hook command MUST hand events to a long-lived local reporter when one is running (the dashboard, or a small background process the hook starts on first use), and only fall back to doing the work itself when none is. |
| FR-002 | The handoff MUST be local only (loopback or a user-only socket/pipe) and authenticated with the ingest token. |
| FR-003 | PreToolUse MUST still be able to refuse a tool call for a stop, within the latency goal. |
| FR-004 | If the reporter is unreachable or slow (over 1 s), the hook MUST do the work itself or give up silently: Claude Code is never blocked. |
| FR-005 | A benchmark MUST measure the per-call overhead on Linux, macOS and Windows in CI, and fail if it regresses past the goal by more than 50%. |

## Acceptance criteria

1. **Given** the dashboard running, **then** the median hook call takes under 20 ms.
2. **Given** no reporter running, **then** events are still recorded (slower path).
3. **Given** a stop requested, **then** the next tool call is refused, as before.

## Open questions

- Is the smallest possible launcher (a tiny script that only forwards stdin) fast enough on
  Windows, where process start dominates? Measure before choosing.
