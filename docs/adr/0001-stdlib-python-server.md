# 0001: The server uses the Python standard library only

- **Status:** Accepted
- **Date:** 2026-11-10

## Context

Kestrel must install in one command on Linux, macOS and Windows and keep working for years on
machines that run agents unattended. Every dependency is a supply-chain risk and a source of
version conflicts in the user's environment, especially next to agent frameworks with heavy
dependency trees.

## Decision

The Python package has **no runtime dependencies**. The server is
`http.server.ThreadingHTTPServer`, storage is `sqlite3`, config is `tomllib`, and process checks
use `ctypes` on Windows.

## Consequences

- `pipx install kestrel-agents` pulls nothing else; the wheel is small and auditable.
- We write a little more code (routing, JSON responses, caching) than a framework would need.
- The server is built for one user on localhost, not the public internet. If Kestrel ever needs
  more, this ADR is revisited.

## Alternatives considered

- **FastAPI or Starlette with uvicorn**: nicer routing and async, but several transitive
  dependencies, some compiled.
- **Flask**: fewer dependencies, still not zero, and nothing we need from it.
