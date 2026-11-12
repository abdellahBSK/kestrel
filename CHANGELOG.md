# Changelog

All notable changes to Kestrel are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Event format v1** ([docs](docs/events.md)): runs, agents, actions, messages, tokens,
  notices, heartbeats and pull requests, versioned and idempotent by `id`.
- **SQLite event store** with deduplication and per-run heartbeats.
- **`POST /v1/events`** with a bearer token (`kestrel token`), batches and NDJSON.
- **Python client** `kestrel.client.Reporter` with automatic heartbeats and failure reporting.
- **`kestrel emit`** and **`kestrel ingest`** to report from any language without a server.
- **`kestrel demo`**: six fictional projects in every state, in a throwaway folder.
- **Honest liveness**: runs need heartbeats; agents decay from working to idle to stale; runs
  that end mid-task show which agents were cut off; dead runners are detected as lost.
- **Pipeline order**: the runner's guard makes testers wait for developers and QA wait for both.
- **Dashboard** rebuilt in React and TypeScript: project health sidebar, live run view, agent
  tree, human-readable activity feed, pull requests, backlog, usage chart, command menu (Ctrl+K),
  light and dark themes.
- `--host` for `kestrel watch` and `kestrel demo`, for containers.
- `[pipeline] hide_ai_attribution` to keep AI attribution out of agent commits (off by default).
- Specs, constitution, architecture overview and ADRs.

### Changed

- Renamed from *Control Room* to **Kestrel**. The package is `kestrel` (installed as
  `kestrel-agents`), the command is `kestrel`, the home folder is `~/.kestrel` and environment
  variables start with `KESTREL_`.
- The API and the store use UTC only; the dashboard shows the computer's clock by default.

### Fixed

- The sidebar no longer shows a project as running after its run died.
- Run times are no longer an hour off when the browser's time-zone data is out of date.
- QA no longer starts while the tester is still running.
- Two dashboards can no longer share one port on Windows.

[Unreleased]: https://github.com/abdellahBSK/kestrel/commits/main
