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

Build the web dashboard once (needs Node 20+):

```bash
cd frontend && npm ci && npm run build && cd ..
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

## How status works

The dashboard never trusts an agent's own last word about itself:

- **Runs.** While a run is in progress the runner rewrites `state/current.json` with a heartbeat
  every 10 seconds. If the heartbeat stops (crash, sleep, closed window) and the agent process is
  gone too, the run shows as **lost**, and the next run records it and leaves the team a note
  about any uncommitted work.
- **Agents.** *Working*, *waiting* (a lead waiting on its agents), *idle* after 2 minutes without
  activity, *stale* after 10 (it may be stuck), *finished*, *failed*, or **cut off** when the run
  ended before the agent reported back. Thresholds live under `[monitor]` in the config.
- **Order.** The guard refuses to start QA while a developer or tester is still running, and
  stops the lead from ending a run while agents it started are still working (`[pipeline]`).
- **Time.** The API speaks UTC only. The dashboard shows times on this computer's clock by
  default (browsers' time-zone data can lag behind the OS), or in the browser's zone if you prefer.

## Safety

The runner installs a guard hook that blocks pushes to anything but task branches, writes outside
the team folder, secret files and outbound HTTP, and enforces the token budget. It is a strong
guardrail, **not a sandbox**: review agent changes before you merge them, and run agents in a
container or a VM for real isolation.

The dashboard listens on `127.0.0.1` only, checks the `Host` header, and its buttons reject
cross-site requests. It sends no telemetry.

## Development

```bash
ruff check . && ruff format --check .   # Python lint and format
pytest                                  # Python tests
```

The dashboard is a React + TypeScript app in `frontend/` (Vite, Tailwind CSS, Radix UI, TanStack
Query). For live reload, run `controlroom watch --no-browser` and, in another terminal:

```bash
cd frontend
npm run dev          # http://localhost:5173, proxies /api to the Python server on :7777
npm run typecheck && npm run lint && npm run format:check
```

`npm run build` writes the production bundle into `src/controlroom/static/`, which the Python
server serves. Fonts are bundled locally: the page makes no requests to other hosts.

## License

[MIT](LICENSE)
