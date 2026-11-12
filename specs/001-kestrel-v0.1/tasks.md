# 001: Kestrel v0.1, tasks

Spec: [spec.md](spec.md) · Plan: [plan.md](plan.md)

## Phase 0: foundation

- [x] T001 Make the runner and dashboard an installable package with a `src/` layout
- [x] T002 Resolve all data paths from one home folder (`$KESTREL_HOME`, default `~/.kestrel`)
- [x] T003 Give every config key a default; run with no config file at all
- [x] T004 Baseline tests for meter, guard, runner and dashboard
- [x] T005 CI on Linux, macOS and Windows; ruff lint and format

## Phase 1: trust

- [x] T010 Runner heartbeat and lost-run detection (spec 002)
- [x] T011 Agent states working / waiting / idle / stale / finished / cut off (spec 002)
- [x] T012 UTC API, local display, clock preference (spec 003)
- [x] T013 Guard enforces developer → tester → QA order; Stop hook keeps the lead waiting (spec 004)
- [x] T014 Rebuild the dashboard in React + TypeScript with a validated chart palette
- [x] T015 Refuse to share the dashboard port with another server

## Phase 2: agent-agnostic

- [x] T020 Event format v1 with validation and secret scrubbing (spec 005)
- [x] T021 SQLite event store with idempotent ids and heartbeats
- [x] T022 Fold events into runs and agents; serve the dashboard from the store
- [x] T023 `POST /v1/events` with a bearer token; `GET /v1/health`
- [x] T024 Python `Reporter` client with automatic heartbeats
- [x] T025 `kestrel emit`, `kestrel ingest`, `kestrel token`
- [x] T026 `kestrel demo` with six fictional projects in every state
- [x] T027 Claude Code runner as an adapter that converts transcripts into events

## Repository

- [x] T030 Rename to Kestrel behind one constant; layered package (`core`, `storage`, `api`, `cli`, `adapters`, `runner`)
- [x] T031 Specs, constitution, ADRs, architecture doc
- [x] T032 CONTRIBUTING, Code of Conduct, security policy, issue and PR templates, CHANGELOG
- [x] T033 Dependabot, CodeQL, release workflow, pre-commit, editorconfig, Dockerfile
- [ ] T034 README screenshots and a short GIF of the demo

## Phase 3: adapters

- [x] T040 Claude Code hooks adapter: `kestrel hook install` writes user-level hooks that report any session ([spec 006](../006-claude-code-hooks/spec.md))
- [x] T041 Claude Agent SDK adapter (Python): hook callbacks → events
- [x] T042 Runner: replace Windows-only pieces (CREATE_NO_WINDOW, `cmd /k`, `notify.ps1`, Edge paths) with portable ones
- [x] T043 Guard: recognize absolute POSIX paths, not only Windows-style ones
- [ ] T044 Adapter guide with a worked example for a third framework

## Phase 4: polish the runner

- [ ] T050 `kestrel init` writes a commented config into the home folder
- [ ] T051 Runner documentation page

## Phase 5: control and cost

- [ ] T060 Alerts: stuck, failed, budget threshold, PR waiting (in-app + desktop + webhook)
- [ ] T061 Estimated USD cost from a price table; Opus-equivalent normalization as an option
- [ ] T062 Stop per agent and per project through a control channel adapters poll
- [ ] T063 Budget caps that halt agents through the same channel
- [ ] T064 Error, retry and duration columns per agent
- [ ] T065 Event retention setting and `kestrel prune`

## Phase 6: release

- [ ] T070 Wheel includes the built web app; `pipx install kestrel-agents` and `uvx kestrel-agents demo` work
- [ ] T071 Publish to PyPI with trusted publishing on tag
- [ ] T072 Docker image on GHCR
- [ ] T073 v0.1.0
