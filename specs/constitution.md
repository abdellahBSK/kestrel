# The Kestrel constitution

These principles outrank any single feature. A spec or plan that breaks one must say so
explicitly and explain why; reviewers reject changes that break one silently.

## I. Honest status over optimistic status

The dashboard never takes an agent's word that it is still working. A run is live only while
evidence keeps arriving (events or heartbeats). Silence decays into *idle*, *stale* and *lost*.
When Kestrel does not know, it says so. A wrong green dot is the worst bug this project can have.

## II. Agent-agnostic by contract

Kestrel's only interface to agents is the [documented event format](../docs/events.md). No
feature may depend on one framework's internals. Framework-specific code lives in
`kestrel.adapters` and turns that framework's output into ordinary events. The Claude Code runner
is one adapter, with no privileges the event format does not give everyone.

## III. Local-first and private by default

- The server binds to `127.0.0.1` and checks the `Host` header. Exposing it is an explicit,
  documented choice.
- No telemetry, no analytics, no third-party requests from the dashboard.
- Secrets are scrubbed before anything is stored. Ingest requires a token.
- All data lives in one home folder the user can read, back up or delete.

## IV. Zero-dependency core

The Python package runs on the standard library alone (Python 3.11+). A new runtime dependency
needs an ADR. The web app may use well-maintained libraries, pinned to exact versions.

## V. One command to try, one command to run

`kestrel demo` must show every state the dashboard knows, with no agents, no config and no
account. Installing must stay a single command. A feature that makes the first five minutes
worse needs a strong reason.

## VI. Times are UTC; people see their own clock

Storage and the API speak UTC ISO 8601 (`...Z`) only. Conversion to local time happens in the
browser, at display time.

## VII. Tested, typed, reviewable

- Every behavior in a spec's acceptance criteria has a test.
- Changes land as small, focused commits with imperative, sentence-case messages.
- CI (lint, format, type check, tests on Linux, macOS and Windows) is green before merge.

## VIII. Cross-platform

Linux, macOS and Windows are all first-class. No shell, path or process assumption specific to
one OS outside a clearly named, optional module.

## IX. Safe agents, honest limits

Guardrails Kestrel installs (budget caps, branch rules, the guard hook) fail closed. Docs never
call a guardrail a sandbox.

## Amending

Amend this file by pull request, with an ADR explaining the change. Principles are renumbered
never; retired ones are struck through and kept.
