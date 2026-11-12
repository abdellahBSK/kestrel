# Control Room

> **Work in progress.** The name, the event format and the install story are still changing.
> Expect breaking changes until v0.1.0.

A live dashboard, budget guard and scheduled runner for teams of AI coding agents.

Today it runs teams of [Claude Code](https://docs.claude.com/en/docs/claude-code) agents (a lead plus
developer, tester, QA, security and optimizer subagents) on your projects within a daily token
budget, and shows what every agent is doing in a local web dashboard. An agent-agnostic event
format, so any agent or orchestrator can report into the dashboard, is on the roadmap.

## Quick start (development)

Requires Python 3.11+, `git`, and for the runner the `claude` CLI and `gh`.

```bash
git clone <this repo> && cd control-room
python -m venv .venv
.venv/bin/pip install -e ".[dev]"     # Windows: .venv\Scripts\pip install -e ".[dev]"
```

Your config and data live in a home folder: `$CONTROLROOM_HOME`, or `~/.controlroom` by default.

```bash
mkdir -p ~/.controlroom && cp config.example.toml ~/.controlroom/config.toml
controlroom status        # token use today / this week, budget left
controlroom watch         # dashboard on http://127.0.0.1:7777
controlroom run --dry-run # what today's scheduled run would do
```

Don't put the home folder inside a git repository: Claude Code would treat that repository as
the agents' project, so the runner refuses to start.

## Safety

The runner installs a guard hook that blocks pushes to anything but task branches, writes outside
the team folder, secret files and outbound HTTP, and enforces the token budget. It is a strong
guardrail, **not a sandbox**: review agent changes before you merge them, and run agents in a
container or a VM for real isolation.

The dashboard listens on `127.0.0.1` only, checks the `Host` header, and its buttons reject
cross-site requests. It sends no telemetry.

## Development

```bash
ruff check . && ruff format --check .
pytest
```

## License

[MIT](LICENSE)
