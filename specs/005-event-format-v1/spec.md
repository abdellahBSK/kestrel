# 005: Event format v1

- **Status:** Done
- **Created:** 2026-11-11
- **Contract:** [docs/events.md](../../docs/events.md) (normative)
- **Related:** [ADR 0002](../../docs/adr/0002-sqlite-event-store.md),
  [ADR 0004](../../docs/adr/0004-server-decides-liveness.md)

## Problem

The dashboard could only show agents run by its own runner, by reading that runner's files. To
be useful to anyone else it needs a contract: a small, stable format any agent, in any language,
can send.

## Goals

- Easy to emit by hand: one `curl` per event, no SDK required.
- Safe to resend: idempotent by `id`.
- Rich enough for the dashboard: runs, agent trees, actions, tokens, notices, PRs.
- Stable: versioned, unknown fields kept, additive changes only within v1.

## Functional requirements

| ID | Requirement |
|---|---|
| FR-001 | An event MUST have `type` and `project`; `run` for all but `pr.*`; `agent` for `agent.*`. |
| FR-002 | Types: `run.started`, `run.heartbeat`, `run.finished`, `agent.started`, `agent.action`, `agent.message`, `agent.tokens`, `agent.notice`, `agent.heartbeat`, `agent.finished`, `pr.opened`, `pr.closed`. |
| FR-003 | `ts` MAY be omitted (time received); if given it MUST carry a timezone or be Unix seconds. |
| FR-004 | An event whose `id` is already stored MUST be ignored and counted as a duplicate. |
| FR-005 | Secrets MUST be scrubbed from every string before storage. |
| FR-006 | Strings MUST be cut at 8,000 characters and `data` limited to 64 kB. |
| FR-007 | `POST /v1/events` MUST require the bearer token and accept one event, an array, `{"events": [...]}` or NDJSON, up to 5,000 events or 5 MB. |
| FR-008 | The response MUST report accepted, duplicates and rejected-with-reason; valid events in a batch MUST be kept. |
| FR-009 | Within v1, changes MUST be additive: new optional fields or types only. |

## Acceptance criteria

1. **Given** a batch with three valid events and one with an unknown type, **then** three are
   stored and the response names the rejected index and why.
2. **Given** the same event sent twice with one `id`, **then** it is stored once.
3. **Given** a request without the token, **then** it is refused with 401.

Tests: `tests/test_events.py`, `tests/test_ingest.py`, `tests/test_cli_tools.py`.
