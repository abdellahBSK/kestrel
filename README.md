# Kestrel

**See what your AI agents are doing, what they cost, and when they get stuck — live, on your own machine.**

> **Pre-release.** The name and the install story are still changing. Expect breaking changes
> until v0.1.0.

Kestrel is a local dashboard for agent runs. Any agent, framework or orchestrator reports
small JSON events (run started, agent spawned, tool call, tokens, heartbeat, finished, PR
opened) and the dashboard shows every run live: which agents are working, waiting, idle or stuck,
what each one did, what it cost in tokens, and which runs were lost or left work unfinished.

It also ships an optional **scheduled runner** for teams of [Claude Code](https://docs.claude.com/en/docs/claude-code)
agents (a lead plus developer, tester, QA, security and optimizer subagents) that work on your
repositories within a daily token budget, behind a guard that enforces branch, path and budget
rules.

- **Agent-agnostic.** A documented [event format](docs/events.md), a Python client, a CLI and
  an HTTP endpoint. The Claude Code runner is just one adapter.
- **Honest status.** It never trusts an agent's last word: runs need heartbeats, agents decay
  from working to idle to stale, and runs that ended mid-task show which agent was cut off.
- **Local and private.** Listens on 127.0.0.1, stores everything in one SQLite file, scrubs
  secrets before storing them, makes no third-party requests and sends no telemetry.

## Try it in one minute

Requires Python 3.11+ and, to build the web app, Node 20+.

```bash
git clone <this repo> && cd control-room
python -m venv .venv
.venv/bin/pip install -e ".[dev]"          # Windows: .venv\Scripts\pip install -e ".[dev]"
cd frontend && npm ci && npm run build && cd ..
.venv/bin/kestrel demo                  # opens http://127.0.0.1:7777
```

The demo runs six fictional projects through every state the dashboard knows (a live run, a
stuck agent, a run that left work unfinished, a failed run, a lost run) in a throwaway folder
that is deleted when you stop it.

## Report your own agents

Start the dashboard, then send events from anywhere.

```bash
kestrel watch                           # http://127.0.0.1:7777
```

**From Python** (writes straight to the local store; no server needed):

```python
from kestrel.client import Reporter

with Reporter("my-project").run("Fix the login bug") as run:  # sends heartbeats while open
    lead = run.agent("lead", role="lead", model="claude-opus-5-5")
    dev = run.agent("dev-1", role="developer", parent="lead", description="Implement the fix")
    dev.action("Bash", detail="npm test", summary="Ran the tests", result="42 passed")
    dev.tokens(input=1200, output=300, model="claude-sonnet-5-5")
    dev.finish()
    lead.finish()
```

**From any language**, with the CLI or over HTTP:

```bash
RUN=$(kestrel emit run.started --project my-project -d title="Fix the login bug")
kestrel emit agent.action --project my-project --run $RUN --agent dev-1 -d tool=Bash -d detail="npm test"
kestrel emit run.finished --project my-project --run $RUN

curl -X POST http://127.0.0.1:7777/v1/events -H "Authorization: Bearer $(kestrel token)" \
  -H "Content-Type: application/json" \
  -d '{"type":"agent.message","project":"my-project","run":"r1","agent":"lead","data":{"text":"hi"}}'
```

[`docs/events.md`](docs/events.md) is the full format, how the dashboard interprets it, and how
to write an adapter for your framework.

## Configuration

Everything lives in a home folder: `$KESTREL_HOME`, or `~/.kestrel` by default. A config
file is optional. To set budgets, a schedule, display names or runner teams, copy
[`config.example.toml`](config.example.toml) to `<home>/config.toml`:

```toml
[budget]
agents_daily = 800_000           # token budget lines on the dashboard (0 = none)

[projects.my-project]
title = "My project: what it is"
key = "MYP"
```

## The Claude Code runner (optional)

Teams declared under `[teams.<name>]` are run by `kestrel run`: one Claude Code session per
team per day, a lead delegating to subagents, every task on its own branch and pull request.
Requires the `claude` CLI and `gh`.

```bash
kestrel setup          # create the team workspaces
kestrel run --dry-run  # what today's scheduled run would do
kestrel status         # tokens used today and this week, budget left
```

On Windows, `src/kestrel/runner/install-schedule.ps1 -HomeDir <home> -Python <python.exe>`
registers a daily task. Don't put the home folder inside a git repository: Claude Code would
treat that repository as the agents' project, so the runner refuses to start.

**Safety.** The runner installs a guard hook that blocks pushes to anything but task branches,
writes outside the team folder, secret files and outbound HTTP; enforces the token budget; makes
QA wait for the tests; and stops a lead from ending a run while its agents still work. It is a
strong guardrail, **not a sandbox**: review agent changes before you merge them, and run agents
in a container or a VM for real isolation.

## How status works

- **Runs** are live while events or heartbeats keep coming. A run that goes silent without
  finishing is **lost**.
- **Agents** are *working*, *waiting* on agents they started, *idle* after 2 minutes, *stale*
  after 10 (maybe stuck), *finished*, *failed*, or **cut off** when the run ended first.
- **Time.** The API speaks UTC only. The dashboard shows times on this computer's clock by
  default (browsers' time-zone data can lag behind the OS), or in the browser's zone.

## Development

```bash
ruff check . && ruff format --check .   # Python lint and format
pytest                                  # Python tests
cd frontend
npm run dev          # http://localhost:5173, proxies /api to `kestrel watch` on :7777
npm run typecheck && npm run lint && npm run format:check && npm test
```

The dashboard is React + TypeScript (Vite, Tailwind CSS, Radix UI, TanStack Query).
`npm run build` writes it into `src/kestrel/static/`, which the Python server serves.

## License

[MIT](LICENSE)
