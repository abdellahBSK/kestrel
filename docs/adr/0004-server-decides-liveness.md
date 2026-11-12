# 0004: The server decides liveness from evidence, at read time

- **Status:** Accepted
- **Date:** 2026-11-10

## Context

The original dashboard trusted the last thing an agent wrote. Agents that were killed never
wrote "finished", so they showed as working forever ([spec 002](../../specs/002-honest-liveness/spec.md)).

## Decision

Clients report **facts** (events and heartbeats), never status. The server computes run and
agent state when it is read, from the events, the latest heartbeat and the current time, using
the thresholds under `[monitor]` in the config.

## Consequences

- A dead process cannot lie: silence becomes *idle*, then *stale*, then *lost*.
- No background job maintains state, and a restart loses nothing.
- Clients must send heartbeats during long silent work. The Python client does it automatically.

## Alternatives considered

- **Clients send their status**: simpler, and wrong exactly when it matters.
- **A background sweeper writes state**: correct, but adds a moving part and a window in which
  the stored state is out of date.
