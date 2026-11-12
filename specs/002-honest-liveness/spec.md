# 002: Honest liveness: heartbeats, stale and lost

- **Status:** Done
- **Created:** 2026-11-10
- **Related:** [ADR 0004](../../docs/adr/0004-server-decides-liveness.md)

## Problem

The dashboard showed a project as *running* for hours after its run had died. Two causes:

1. A background subagent was killed when the run ended. It never wrote a "finished" record, so
   it stayed *working* forever.
2. The runner process itself crashed and left its lock file behind, so the project stayed
   *running* until someone deleted the file by hand.

Status that is wrong in the optimistic direction is worse than no status: the owner stops
checking, and stuck work sits unnoticed.

## Functional requirements

| ID | Requirement |
|---|---|
| FR-001 | A run MUST be shown live only while events or heartbeats arrive within `heartbeat_timeout` (default 45 s). |
| FR-002 | A run that goes silent without `run.finished` MUST be shown as **lost**. |
| FR-003 | An agent MUST be *working* while it acts, *idle* after `idle_after` (120 s) without activity, *stale* after `stale_after` (600 s). |
| FR-004 | An agent MUST be *waiting* while agents it started are still active. |
| FR-005 | An agent is *finished* only if its `agent.finished` comes after its last activity. |
| FR-006 | An agent that never finished in a run that ended MUST be shown as **cut off**. |
| FR-007 | A project's sidebar dot MUST be the worst state of its latest run: running, may be stuck, lost, failed, unfinished work, idle, never run. |
| FR-008 | The runner MUST write a heartbeat every 10 s and record a lost run, with a handoff note, when it finds a dead runner's marker. |
| FR-009 | The runner's lead agent MUST NOT be able to end its session while subagents it started are still working (Stop hook). |

## Acceptance criteria

1. **Given** a live run, **when** its process is killed, **then** within 45 s the run is *lost*
   and the sidebar dot is red.
2. **Given** an agent that stops acting for 11 minutes, **then** it shows *stale*, and the
   project shows *may be stuck*.
3. **Given** a run that finished while a subagent never reported finishing, **then** that
   subagent shows *cut off* and the project shows *unfinished work*.
4. **Given** a lost runner marker from a dead process, **when** the runner next starts, **then**
   it records the run as lost, writes a handoff note to the team's `STATE.md`, and proceeds.

Tests: `tests/test_liveness.py`, `tests/test_status.py`, `tests/test_store_runs.py`,
`tests/test_guard_order.py`.
