# 004: QA waits for the tester

- **Status:** Done
- **Created:** 2026-11-10

## Problem

In the runner's agent pipeline (developer → tester → QA), the lead sometimes started QA while
the tester was still running. QA then judged untested code and passed changes the tester was
about to fail. A prompt asking politely was not enough.

## Functional requirements

| ID | Requirement |
|---|---|
| FR-001 | The guard MUST refuse to start a `tester` while a `developer` started by the same session is still running. |
| FR-002 | The guard MUST refuse to start `qa` while a `developer` or `tester` is still running. |
| FR-003 | The refusal message MUST tell the lead what to wait for. |
| FR-004 | The order MUST be configurable: `[pipeline] enforce_order` (default `true`). |
| FR-005 | If the guard cannot tell which agents are running, it MUST allow the call (fail open for ordering only; every other rule fails closed). |
| FR-006 | The lead's role prompt MUST describe the order explicitly. |

## Acceptance criteria

1. **Given** a running tester, **when** the lead starts QA, **then** the call is denied with
   "wait for the tester to finish".
2. **Given** finished developer and tester, **when** the lead starts QA, **then** it is allowed.
3. **Given** `enforce_order = false`, **then** QA may start at any time.

Tests: `tests/test_guard_order.py`.
