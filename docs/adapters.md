# Writing an adapter

An adapter makes a framework report to Kestrel without the people using it writing any
reporting code. Kestrel ships two (Claude Code and the Claude Agent SDK); this page shows how to
build one for anything else. Most adapters are one file of 50–150 lines.

Before you start, skim the [event format](events.md): twelve event types, and the rules the
dashboard applies to them.

## Choose where the events come from

| Your framework offers… | Do this | Example |
|---|---|---|
| Callbacks or hooks (on tool call, on LLM response, on finish) | Report from the callbacks with the Python client. **Preferred**: events arrive live. | [`claude_agent_sdk.py`](../src/kestrel/adapters/claude_agent_sdk.py) |
| A hook command line | Install a command that reads each hook's input and stores events. | [`claude_code_hooks.py`](../src/kestrel/adapters/claude_code_hooks.py) |
| Only logs or transcripts | Read them and convert each record, with an `id` derived from the file and line so re-reading adds nothing. | [`claude_code.py`](../src/kestrel/adapters/claude_code.py) |
| Nothing, and it isn't Python | `POST /v1/events` from your code, or `kestrel emit` from scripts. | [below](#from-another-language) |

## Worked example: your own agent loop

Most agents are a loop: ask the model, run the tools it asks for, repeat. Here is a complete
adapter for such a loop: a context manager that wraps a run, plus two calls inside the loop. It
works the same whatever model API you call.

```python
"""kestrel_loop.py: report a hand-written agent loop to Kestrel."""

from contextlib import contextmanager

from kestrel.client import Reporter


@contextmanager
def reported_run(project: str, task: str, model: str):
    """Wrap one task. Heartbeats run in the background; an exception marks the run failed."""
    with Reporter(project).run(task, source="my-agent") as run:
        agent = run.agent("main", role="lead", model=model, description=task)
        yield agent
        agent.finish()


def report_step(agent, response, tool_calls, results):
    """Call once per model turn: what the model said, what it ran, what it cost."""
    usage = response["usage"]
    agent.tokens(input=usage["input_tokens"], output=usage["output_tokens"], model=response["model"])
    if response.get("text"):
        agent.message(response["text"])
    for call, result in zip(tool_calls, results):
        agent.action(
            call["name"],
            detail=str(call["arguments"])[:500],  # the raw command or path; shown on hover
            status="error" if result.get("error") else "ok",
            result=str(result.get("error") or result.get("output"))[:300],
        )
```

Using it:

```python
with reported_run("support-bot", "Answer ticket #4521", model="claude-sonnet-5-5") as agent:
    while True:
        response = call_model(messages)  # your code
        tool_calls = response.get("tool_calls", [])
        results = [run_tool(c) for c in tool_calls]  # your code
        report_step(agent, response, tool_calls, results)
        if not tool_calls:
            break
```

That is a full adapter: the run appears live while it works, every tool call and token is on
the dashboard, and a crash shows as a failed run.

### Sub-agents

When your agent hands work to another agent, give the child a `parent`, so the dashboard draws
the tree and shows the parent as *waiting* while the child works:

```python
researcher = run.agent("researcher-1", role="researcher", parent="main", description="Find prior art")
...
researcher.finish()
```

### Long silent steps

If a step can take longer than 45 seconds without reporting anything (a long model call, a big
build), either keep the `Reporter` run open (it sends heartbeats every 10 seconds), or declare a
longer `heartbeat_timeout` in `run.started` when your process can't send heartbeats.

## From another language

Any language that can make an HTTP request can report. Start `kestrel watch`, read the token with
`kestrel token`, and post events. TypeScript:

```ts
const KESTREL = "http://127.0.0.1:7777/v1/events";
const TOKEN = process.env.KESTREL_TOKEN!; // export KESTREL_TOKEN=$(kestrel token)

async function report(events: object[]) {
  try {
    await fetch(KESTREL, {
      method: "POST",
      headers: { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify(events),
    });
  } catch {
    // never let monitoring break the agent
  }
}

const run = `run-${Date.now()}`;
await report([{ type: "run.started", project: "web-agent", run, data: { title: "Crawl docs" } }]);
await report([{ type: "agent.action", project: "web-agent", run, agent: "main", data: { tool: "fetch", detail: url } }]);
await report([{ type: "run.finished", project: "web-agent", run, data: { status: "ok" } }]);
```

Send `run.heartbeat` every 10–15 seconds while a run is alive, batch events when you can (up to
5,000 per request), and give events an `id` if your code might send them twice.

## Checklist for a good adapter

- [ ] Every run ends with `run.finished`, including on errors and interrupts.
- [ ] Agents that start others pass `parent`.
- [ ] Heartbeats, or a declared `heartbeat_timeout`, cover long silences.
- [ ] Tool calls have a short `summary` or a `detail` the dashboard can turn into a readable line.
- [ ] Tokens are reported with the `model`, so weights and costs work.
- [ ] Reporting failures are swallowed: monitoring never breaks the agent.
- [ ] Events that may be re-sent have deterministic `id`s.
- [ ] Tests feed recorded framework output through the adapter (see
      [`tests/test_claude_code_hooks.py`](../tests/test_claude_code_hooks.py)).

## Contributing an adapter

Adapters for popular frameworks are welcome in `src/kestrel/adapters/`. Open an
[adapter request](../../../issues/new?template=adapter_request.yml) first so we can agree on
the mapping, then follow [CONTRIBUTING.md](../CONTRIBUTING.md). An adapter must not add a
required dependency: import the framework inside the function that needs it, as
`claude_agent_sdk.py` does.
