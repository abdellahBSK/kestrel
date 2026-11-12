# 0002: Events are stored in one SQLite file

- **Status:** Accepted
- **Date:** 2026-11-11

## Context

Events arrive from several writers at once: the HTTP server, CLI invocations, the Python client
in other processes, and adapters. The store must be safe with concurrent writers, survive
crashes, and be easy to back up or delete.

## Decision

One SQLite database at `<home>/data/events.db` in WAL mode, with two tables: `events`
(append-only, unique `id` for idempotency) and `heartbeats` (one row per run and agent, upserted
with the latest time).

## Consequences

- Clients can write without a running server; the dashboard sees their events on its next read.
- Resending is harmless, so adapters can re-read logs from the start.
- Heartbeats cost one row per run instead of one per beat.
- Large histories will need retention (`kestrel prune`, planned).

## Alternatives considered

- **JSON Lines files per run**: simple, but concurrent appends and deduplication get fiddly.
- **DuckDB**: great for analytics, but a dependency (ADR 0001) and not built for many small
  writes.
