# Changelog

All notable changes to Kestrel are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **`kestrel init`** writes a commented config into the home folder, every value a default.
- **`kestrel doctor`** checks Python, the home folder, the config (with the line of a TOML error),
  the event store, the web app, the dashboard port, Claude Code hooks and, for the runner,
  `claude`, `git`, `gh`, budgets and workspaces, and says how to fix each problem.
- Guides: [the runner](docs/runner.md), [writing an adapter](docs/adapters.md) with a worked
  example that the tests run, and a [docs index](docs/README.md).
- `kestrel --help` groups the commands; every runner command has help text; `--home` works with
  the installed `kestrel` command too.
- `Reporter.run(source=...)` names what produced a run.
- **Claude Code adapter**: `kestrel hook install` reports every Claude Code session: one run per
  prompt, subagents as child agents, tool calls with results and errors, tokens, permission
  notices. `kestrel hook status` and `kestrel hook uninstall`. ([docs](docs/claude-code.md))
- **Claude Agent SDK adapter**: `ClaudeAgentOptions(hooks=kestrel.adapters.claude_agent_sdk.hooks())`.
- `run.started` accepts `heartbeat_timeout` for sources that go quiet during long work;
  `agent.tokens` accepts `interactive` for sessions a person drives.
- The runner works on macOS and Linux: notifications (`osascript`, `notify-send`), demo
  windows (Terminal, common Linux terminals, or a log file without a desktop) and screenshots
  with any Chromium-based browser (`KESTREL_BROWSER` to choose one).
- `--home` works on every command.
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
- The runner's guard now recognizes absolute macOS and Linux paths (`/home/…`, `/Users/…`,
  `/etc/…`) as outside the workspace, not only Windows-style ones.

[Unreleased]: https://github.com/abdellahBSK/kestrel/commits/main
