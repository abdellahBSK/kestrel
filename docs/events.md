# The event format (v1)

Any agent, framework or orchestrator can report into the dashboard by sending small JSON
events. This page is the whole contract. The reference implementation is
[`src/kestrel/core/events.py`](../src/kestrel/core/events.py).

## The shape of an event

```json
{
  "v": 1,
  "type": "agent.action",
  "ts": "2026-11-12T08:49:43.120Z",
  "project": "storefront",
  "run": "20261112-084900-3fa2c1",
  "agent": "developer-1",
  "id": "storefront:20261112-084900-3fa2c1:42",
  "data": { "tool": "Bash", "detail": "npm test", "status": "ok", "result": "128 passed" }
}
```

| Field | Required | Meaning |
|---|---|---|
| `type` | yes | One of the types below. |
| `project` | yes | What the agents work on. Projects appear in the dashboard on their first event. |
| `run` | yes, except `pr.*` | One attempt at work, from start to finish. Any unique string. |
| `agent` | for `agent.*` | One agent inside a run (`lead`, `developer-1`…). Unique within the run. |
| `ts` | no | When it happened: ISO 8601 **with a timezone** (use UTC, `Z`), or Unix seconds. Default: when received. |
| `id` | no | Makes resending harmless: an event whose `id` is already stored is ignored. |
| `v` | no | Format version. Default and only value: `1`. |
| `data` | depends | The type's fields, below. Unknown fields are kept. |

`project`, `run` and `agent` are 1–128 characters: letters, digits and `. _ : @ / + -`, starting
with a letter or digit.

## Types

### Runs

| Type | `data` |
|---|---|
| `run.started` | `title` (what this run does), `budget` (token allowance, optional), `source` (your tool's name), `heartbeat_timeout` (seconds of silence before the run counts as lost, 5–86400; for sources that cannot send heartbeats during long work) |
| `run.heartbeat` | — |
| `run.finished` | `status`: `ok` · `failed` · `stopped` · `interrupted`; `summary`, `error` (optional) |

### Agents

| Type | `data` |
|---|---|
| `agent.started` | `role` (e.g. `lead`, `developer`, `tester`, `qa`, `security`), `description`, `parent` (the agent that started this one), `model` |
| `agent.action` | `tool` (required unless updating by `call`), `summary` (one human line), `detail` (the raw command or path), `status`: `running` · `ok` · `error` · `blocked`, `result`, `call` |
| `agent.message` | `text` |
| `agent.tokens` | `input`, `output`, `cache_read`, `cache_write` (counts), `model`, `cost_usd` (optional), `interactive` (true for sessions a person drives: shown on the project, not added to the agents' total) |
| `agent.notice` | `level`: `info` · `warning` · `critical`; `text` |
| `agent.heartbeat` | — |
| `agent.finished` | `status`: `ok` · `failed` · `stopped` · `interrupted`; `summary`, `error` |

A slow action can be reported twice: first with a `call` id and `"status": "running"`, then
again with the same `call` and its final `status` and `result`. The second only needs `call`.

`agent.tokens` can be sent once per model call or as running totals per call; they add up.

### Pull requests

| Type | `data` |
|---|---|
| `pr.opened` | `number` (required), `title`, `url` (http/https), `branch`, `draft` |
| `pr.closed` | `number` (required), `merged` |

## How the dashboard reads events

You report what happened; the dashboard decides what it means. It never takes an agent's word
that it is still working:

- **A run is live** while events or heartbeats keep arriving. After 45 seconds of silence (or the
  run's own `heartbeat_timeout`) a run that never sent `run.finished` is shown as **lost**. Send `run.heartbeat` every 10–15 seconds
  while a run is alive, including while an agent waits on a long command.
- **An agent** is *working* while it acts, *idle* after 2 minutes without activity, *stale* after
  10 (it may be stuck), and *waiting* while agents it started are still at work. It is *finished*
  only if its `agent.finished` comes after its last activity. An agent that never finished in a
  run that ended is shown as **cut off**.
- **A project's** status dot is the worst thing true of its latest run: running, may be stuck,
  run lost, last run failed, unfinished work, idle, or never run.

The thresholds live under `[monitor]` in `config.toml`.

## Sending events

**Python** (no server needed; writes to this computer's store):

```python
from kestrel.client import Reporter

with Reporter("storefront").run("Apple Pay in checkout") as run:  # heartbeats while open
    lead = run.agent("lead", role="lead", model="claude-opus-5-5")
    dev = run.agent("dev-1", role="developer", parent="lead", description="Implement it")
    dev.action("Bash", detail="npm test", summary="Ran the tests", result="128 passed")
    dev.tokens(input=5200, output=900, model="claude-sonnet-5-5")
    dev.finish()
    lead.finish()
```

**Command line** (any language, no server needed):

```bash
RUN=$(kestrel emit run.started --project storefront -d title="Apple Pay in checkout")
kestrel emit agent.started --project storefront --run $RUN --agent dev-1 -d role=developer
kestrel emit agent.action  --project storefront --run $RUN --agent dev-1 -d tool=Bash -d detail="npm test"
kestrel emit run.finished  --project storefront --run $RUN
kestrel ingest events.jsonl            # a file of events, one JSON object per line
```

**HTTP**, to a running dashboard (`kestrel watch`):

```bash
curl -X POST http://127.0.0.1:7777/v1/events \
  -H "Authorization: Bearer $(kestrel token)" \
  -H "Content-Type: application/json" \
  -d '{"type":"run.started","project":"storefront","run":"r1","data":{"title":"Apple Pay"}}'
```

The body may be one event, an array, `{"events": [...]}`, or JSON Lines with
`Content-Type: application/x-ndjson`. Up to 5,000 events or 5 MB per request. The response
says how many were accepted, how many were duplicates, and why any were rejected; valid events
in a batch are kept even if others are not. `GET /v1/health` needs no token.

## Security

- The token lives in `<home>/ingest.token`. Because it travels in a custom header, browsers must
  ask before sending it, and the server never says yes, so a web page cannot post into your
  dashboard. The server only listens on `127.0.0.1` and checks the `Host` header.
- **Secrets are scrubbed before anything is stored**: API keys and tokens (GitHub, Anthropic,
  OpenAI, AWS, Slack, Stripe, npm, GitLab, Google), JWTs, private keys, passwords in URLs and
  `key=value` assignments of secret-looking names become `[redacted]`. It is a safety net; don't
  send secrets on purpose.
- Strings are cut at 8,000 characters; `data` may be at most 64 kB.

## Writing an adapter

An adapter turns one agent setup into these events. Two good patterns:

1. **Hooks** (preferred): call the `Reporter` or `kestrel emit` from your framework's
   callbacks: run start and end, each tool call and its result, each model response's usage.
2. **Log tailing**: read the framework's own logs or transcripts and convert them, giving every
   event a deterministic `id` (derived from the file and line) so re-reading is harmless.
   [`adapters/claude_code.py`](../src/kestrel/adapters/claude_code.py) works this way.

The [Claude Code hooks adapter](../src/kestrel/adapters/claude_code_hooks.py) combines both:
lifecycle hooks for runs and tool calls, the transcript for tokens. See
[Claude Code and the Claude Agent SDK](claude-code.md).

Either way: send `agent.started` with a `parent` so the dashboard can draw the tree, send
heartbeats while a run is alive, and always end with `run.finished`, including on errors.
