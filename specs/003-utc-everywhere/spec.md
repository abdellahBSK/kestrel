# 003: UTC in storage, local time on screen

- **Status:** Done
- **Created:** 2026-11-10
- **Related:** [ADR 0005](../../docs/adr/0005-utc-api.md)

## Problem

Run times on the dashboard were an hour off. The server labelled runs with file modification
times in the server's local zone, and the browser converted again using its own time-zone data,
which can lag behind the operating system's after a country changes its rules. Two clocks, two
sources of truth, one wrong answer.

## Functional requirements

| ID | Requirement |
|---|---|
| FR-001 | The store and the API MUST use UTC only, as ISO 8601 with a `Z` suffix. |
| FR-002 | Events without a timezone MUST be rejected; timestamps more than 5 minutes in the future MUST be clamped to the time received. |
| FR-003 | Runs MUST be labelled by their start time from events, never by file modification time. |
| FR-004 | The dashboard MUST show times on the computer's clock by default (the server reports its UTC offset), with an option to use the browser's zone. |
| FR-005 | Every displayed time SHOULD show its full date and zone on hover. |

## Acceptance criteria

1. **Given** an event with `ts` `2026-11-12T08:00:00+01:00`, **then** the API returns
   `2026-11-12T07:00:00Z`.
2. **Given** a browser whose zone data disagrees with the OS, **then** times shown by default
   match the OS clock.
3. **Given** an event with a naive timestamp, **then** it is rejected with an explanation.

Tests: `tests/test_events.py`, `frontend/src/lib/format.test.ts`.
