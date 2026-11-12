# 0005: The API speaks UTC; the browser converts

- **Status:** Accepted
- **Date:** 2026-11-10

## Context

Times were shown an hour off because the server and the browser each applied a time zone, and
the browser's zone data was out of date ([spec 003](../../specs/003-utc-everywhere/spec.md)).

## Decision

Storage and every API field use UTC (`...Z`). The server also reports its UTC offset. The
dashboard shows times on the computer's clock by default and offers the browser's zone as an
option.

## Consequences

- One source of truth; conversion happens once, at display.
- Event producers must send a timezone (or Unix seconds); naive timestamps are rejected.
