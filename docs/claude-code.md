# Claude Code and the Claude Agent SDK

Kestrel shows every Claude Code session on your computer live: each prompt as a run, the
subagents it starts as child agents, every tool call in plain language, tokens per agent, and
the notifications where Claude waits for you.

## Claude Code

```bash
kestrel hook install      # once
kestrel watch             # the dashboard
```

That's it. Every new session reports as soon as you send a prompt; restart sessions that were
already open. The project is the name of the repository you work in (or the folder, outside a
repository); set `KESTREL_PROJECT` to choose another.

| Command | What it does |
|---|---|
| `kestrel hook install` | Adds Kestrel's hooks to `~/.claude/settings.json`: every session, every project. |
| `kestrel hook install --scope project` | Only this repository, in `.claude/settings.json` (commit it to share with your team). |
| `kestrel hook install --scope local` | Only this repository, just for you (`.claude/settings.local.json`). |
| `kestrel hook status` | Where the hooks are installed. |
| `kestrel hook uninstall [--scope …]` | Removes Kestrel's hooks and nothing else. |

Installing keeps every other setting and hook, saves a backup of the file first, and is safe to
run again (for example after moving Kestrel to another Python).

### What you see

| In Claude Code | In Kestrel |
|---|---|
| You send a prompt | A new run, titled with your prompt |
| Claude uses a tool | An action on the main agent: *running*, then *ok* or *error* with the result |
| Claude starts a subagent | A child agent with the subagent's type as its role, and its own actions and tokens |
| Claude asks for permission | A notice on the run |
| Claude finishes its answer | The run finishes; its last message is the summary |
| You press Esc and send another prompt, or quit mid-answer | The run shows as *interrupted* |
| A background agent reports back | Its work continues the run it belongs to |

Claude Code sends nothing while a model writes a long answer or a tool runs, so its runs are only
called *lost* after 5 minutes of silence instead of 45 seconds.

### Your usage and the agents' budget

The dashboard already shows your own Claude Code usage as **You** (read from Claude Code's logs).
Tokens reported by the hook are marked `interactive`, so they appear on their projects but are not
added again to the agents' total.

### Privacy and performance

The hook writes straight into your local store; nothing leaves your computer. Secrets in commands
and results are scrubbed before they are stored, like every event. Each call takes about a tenth
of a second, mostly Python starting up, and it never blocks Claude Code: on any problem it exits
quietly and writes the error to `~/.kestrel/data/claude-code/errors.log` (`kestrel hook status`
tells you when there is one).

## Claude Agent SDK (Python)

Programs built on the [Claude Agent SDK](https://docs.claude.com/en/docs/agent-sdk/overview)
report with one line:

```python
from claude_agent_sdk import ClaudeAgentOptions, query
from kestrel.adapters.claude_agent_sdk import hooks

options = ClaudeAgentOptions(hooks=hooks(project="support-bot"))

async for message in query(prompt="Triage the new tickets", options=options):
    ...
```

The SDK passes its hook callbacks the same information Claude Code passes command hooks, so you
get the same runs, agents, actions and tokens. Already using hooks? Merge the lists:

```python
mine = {"PreToolUse": [HookMatcher(matcher="Bash", hooks=[check_command])]}
theirs = hooks(project="support-bot")
options = ClaudeAgentOptions(hooks={e: mine.get(e, []) + theirs.get(e, []) for e in {*mine, *theirs}})
```

Reporting never raises into your program. Install Kestrel in the same environment as your agent
(`pip install kestrel-agents`, once it is published; from source until then) and run
`kestrel watch` to see it.

## Kestrel's own runner

Sessions started by `kestrel run` are reported by the runner itself and are not reported twice:
the runner starts Claude Code without your user settings, so your user-level hooks don't run
there.
