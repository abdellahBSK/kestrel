# 001: Kestrel v0.1, plan

Spec: [spec.md](spec.md) · Architecture: [docs/architecture.md](../../docs/architecture.md)

## Constitution check

| Principle | How this plan respects it |
|---|---|
| I. Honest status | Liveness is computed server-side from heartbeats and event times (spec 002). |
| II. Agent-agnostic | Everything flows through the v1 event format (spec 005); Claude Code is an adapter. |
| III. Local-first | 127.0.0.1 bind, Host check, ingest token, secret scrubbing, no telemetry. |
| IV. Zero-dependency core | Python stdlib only: `http.server`, `sqlite3`, `tomllib`. |
| V. One command | `kestrel demo`; packaging with the built web app inside the wheel. |
| VI. UTC | API and store are UTC; the browser converts (spec 003). |
| VII. Tested | pytest + vitest; CI on three OSes and three Python versions. |
| VIII. Cross-platform | Process checks use `ctypes` on Windows and signals elsewhere; no PowerShell in core. |
| IX. Safe agents | The runner's guard hook fails closed; docs say it is not a sandbox. |

## Approach

Events are the single source of truth. Adapters and clients write events; the store keeps them;
`core.runs.fold` turns a run's events plus its latest heartbeat into the state the dashboard
shows. The API serves folded runs; the React app renders them. See the
[architecture](../../docs/architecture.md) for the layer diagram.

## Phases

| Phase | Scope | Status |
|---|---|---|
| 0 | Installable package, home folder, config defaults, tests, CI | Done |
| 1 | Specs 002–004 (liveness, UTC, pipeline order); professional React dashboard | Done |
| 2 | Event format v1, SQLite store, `POST /v1/events`, Python client, `emit`/`ingest`/`token`, demo mode | Done |
| 3 | Claude Code hooks adapter for any Claude Code user; Claude Agent SDK adapter; cross-platform runner | Done |
| 4 | Config and wording pass; `kestrel init` and `kestrel doctor`; runner and adapter guides | Done |
| 5 | Alerts, USD cost, stop per agent and project, enforced budget caps, retries and durations, UI polish ([spec 008](../008-control-and-cost/spec.md)) | Done |
| 6 | Packaging (`pipx`, `uvx`, Docker), README media, release automation, v0.1.0 | Next |

## Risks

- **Adapters drift** as frameworks change their logs: prefer hooks over log tailing, and give
  every adapter fixture-based tests.
- **Stop and budget enforcement** need a control channel back to agents; v0.1 delivers it only
  to adapters that poll for it (the runner and the Claude Code hook), and the UI says which.
- **SQLite growth**: add retention settings before v0.1.0.
