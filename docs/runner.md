# The runner

The runner is the optional half of Kestrel: it runs **teams of Claude Code agents on your
repositories, on a schedule, within a token budget**. Each scheduled day, a lead agent reads its
team's backlog, delegates tasks to developer, tester, QA, security and optimizer subagents, and
leaves every finished task as its own branch and pull request for you to review. The dashboard
shows it all live.

You don't need the runner to use Kestrel. If you only want to watch agents you already run, see
[Claude Code](claude-code.md) or the [event format](events.md).

> **Agents with shell access can do damage.** The runner's guard blocks the obvious dangers, but
> it is a guardrail, not a sandbox. Review every pull request before merging, and run the
> runner in a container or VM if you need real isolation.

## Requirements

- [Claude Code](https://docs.claude.com/en/docs/claude-code) (`claude`), logged in.
- `git`, and [`gh`](https://cli.github.com/) logged in (`gh auth login`) for teams that open
  pull requests.
- A home folder **outside any git repository** (Claude Code would treat that repository as the
  agents' project, so the runner refuses to start). The default, `~/.kestrel`, is fine.

`kestrel doctor` checks all of this.

## Set up a team

1. Create the config and open it:

   ```bash
   kestrel init
   ```

2. Set a budget, a schedule and a team in `<home>/config.toml`:

   ```toml
   [budget]
   agents_daily = 800_000        # tokens all teams may use per day
   agents_weekly = 4_000_000     # ...and per rolling 7 days

   [schedule]
   mon = ["my-app"]
   wed = ["my-app"]
   fri = ["my-app"]
   start_hour = 9                # don't start before 9:00 local time

   [teams.my-app]
   title = "My app: a small REST service"
   repo = "https://github.com/you/my-app.git"
   key = "APP"                   # backlog IDs and branches: APP-014, feat/APP-014-rate-limits
   mode = "build"
   pr_mode = "draft"
   focus = "Harden the API and raise test coverage. Keep the tests green."
   ```

3. Create the workspace and check what today's run would do:

   ```bash
   kestrel setup
   kestrel run --dry-run
   ```

4. Run once by hand while you watch the dashboard (`kestrel watch` in another terminal):

   ```bash
   kestrel run --team my-app --force
   ```

### Team settings

| Key | Meaning |
|---|---|
| `title` | Shown on the dashboard. |
| `repo` | A GitHub URL to clone, or `""` for a new local-only repository. |
| `key` | A short code for backlog IDs and branch names (`APP-014`). |
| `mode` | `build`: the team writes code on task branches. `advisory`: the team only reads and writes proposals in its report; the repository is read-only. |
| `pr_mode` | `ready`: push task branches and open pull requests. `draft`: open draft pull requests. `none`: push nothing; everything stays local. |
| `weight` | The team's share of the day's budget when several teams run the same day. |
| `enabled` | `false` keeps a team from running, even when scheduled. |
| `specs` | Files copied into the team's `specs/` folder: requirements the agents read but can't change. |
| `focus` | One or two sentences on what matters now. The lead plans from it. |

Repositories you own (set `[owner] github`) get an `agent` label on agent pull requests.

## What happens during a run

`kestrel run` is meant to be triggered often (at log-on, on wake, hourly); it decides itself
whether to work:

1. It stops if the `STOP` flag is raised, if the home folder is inside a git repository, if it
   is before `start_hour`, or if it already ran today (`--force` skips the last two checks).
2. It records any earlier run that died mid-way as **lost**, and leaves the team a handoff note
   in `STATE.md`.
3. It computes today's **pool**: what is left of the daily and weekly budgets. If your own
   Claude Code usage this week is above `personal_week_high`, agents get half.
4. Each team scheduled today gets a share of the pool by weight. A share below `min_team_run`
   is skipped: a run needs about 25–30k tokens just to read its charter, state and backlog.
5. For each team, Claude Code starts the **lead** with the team's charter (`CLAUDE.md`), state,
   backlog and the subagent definitions. The lead:
   - follows up on its open pull requests, addressing your review comments first;
   - takes backlog items in priority order, one branch per item;
   - has a **developer** implement it, a **tester** test it, then **QA** judge it (in that order:
     the guard enforces it), plus **security** and **optimizer** passes where useful;
   - pushes the branch and opens the pull request, then updates `BACKLOG.md` and `STATE.md`;
   - gets a **budget warning** at `warn_at` (80%) and wraps up; is **stopped** at `stop_at`.
6. The run writes `reports/<date>.md` per team and a daily brief in `<home>/reports/`, and
   shows a desktop notification with the new pull requests.

### The team workspace

```
<home>/teams/my-app/
├── CLAUDE.md        the charter: project, rules, PR mode, tools (regenerated by `kestrel setup`)
├── BACKLOG.md       prioritised tasks with IDs; the lead maintains it
├── STATE.md         notes from one run to the next
├── demo.json        how to run the app, for `kestrel launch` and screenshots
├── repo/            the git repository: one task branch per backlog item
├── specs/           your requirements, read-only to agents
├── reports/         one report per run, and pull request bodies
└── previews/        screenshots the agents take
```

You can edit `BACKLOG.md` and `STATE.md` between runs to steer the team. Questions the agents
want you to answer appear under *Questions for the owner* in their report and on the dashboard.

## The guard

Every tool call of every agent goes through `kestrel/runner/guard.py` first. It **fails closed**:
if it can't decide, the action is denied.

| Rule | What it blocks |
|---|---|
| Stop and budget | Everything after `kestrel stop`, or once the team's allowance is used up. |
| Stay in the workspace | Reading or writing outside the team folder; `.env` files; `~/.ssh`, `~/.aws`, `~/.claude` and other credential locations; absolute paths elsewhere on disk. |
| Only task branches leave | `git push` except `-u origin <type>/<KEY>-<NNN>-<desc>`; force pushes; `gh` except `pr create/view/list/edit/comment/checks/diff/status`; merging. |
| No history rewriting | `--no-verify`, `git reset --hard`, `rebase`, `filter-branch`, force flags. |
| No outside world | Outbound HTTP except to localhost; `ssh`/`scp`/`rsync`; deploy CLIs; `npm publish` and similar; `docker push`; web tools. |
| Git identity | Changing `git config` user, email or global settings. |
| Advisory mode | Any write to the repository, and commits. |
| Pipeline order | Starting a tester while a developer is still at work, or QA before both finish (`[pipeline] enforce_order`). |
| Finish the job | The lead ending the run while subagents it started are still working (it is told once to wait). |
| AI attribution (opt-in) | `Co-Authored-By: Claude` and similar lines, when `[pipeline] hide_ai_attribution = true`. |

## Commands

| Command | What it does |
|---|---|
| `kestrel setup [team …]` | Create or refresh team workspaces (charter, settings, roles, repository). Safe to re-run. |
| `kestrel run` | Today's scheduled run. `--team T` one team · `--force` ignore "already ran" and `start_hour` · `--dry-run` show what would happen · `--allowance N` cap each team · `--extra N` one-off extra tokens · `--lead-model M`. |
| `kestrel stop` / `kestrel resume` | Raise or lower the `STOP` flag: running agents halt at their next action; no new runs start. Also a button on the dashboard. |
| `kestrel status` | Tokens used today and this week, budget left, today's teams. |
| `kestrel brief [date]` | Rebuild the daily brief. |
| `kestrel prs` | Open agent pull requests across all teams. |
| `kestrel launch TEAM [PR]` | Run a team's app (a pull request, a branch, or main) in its own copy and open it in the browser. |

## Scheduling

The runner works best triggered often: at log-on, on wake and every hour. It runs once a day.

**Windows**: a scheduled task that triggers at log-on, unlock, wake and daily:

```powershell
powershell -ExecutionPolicy Bypass -File <kestrel package>\runner\install-schedule.ps1 -HomeDir <home> -Python <python.exe>
```

(`-Remove` uninstalls it. Find the package folder with `python -c "import kestrel, os; print(os.path.dirname(kestrel.__file__))"`.)

**macOS and Linux**: cron, hourly:

```bash
crontab -e
# then add (use the full path from `which kestrel`):
0 * * * * KESTREL_HOME="$HOME/.kestrel" /path/to/kestrel run >> "$HOME/.kestrel/cron.log" 2>&1
```

cron runs with a minimal `PATH`: if `claude` or `gh` aren't found, add
`PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin` as the first line of the crontab. Claude
Code must already be logged in for that user.

## Troubleshooting

| Message | Meaning and fix |
|---|---|
| `REFUSING TO RUN: … is a git repository` | The home folder is inside a repository. Move it (set `KESTREL_HOME`). |
| `Already ran today.` | Expected; `--force` runs again. |
| `Too early (start_hour)` | Expected before `start_hour`; `--force` overrides. |
| `<team>: skipped, only N tokens left` | The day's or week's budget is used up, or the share is below `min_team_run`. |
| `Claude CLI is not logged in` | Run `claude` once and log in; the run retries at the next trigger. |
| `Claude usage limit reached` | Your plan's limit; the run stops for the day. |
| A run shows **lost** on the dashboard | The runner process died. The next run records it and leaves a note in `STATE.md`. |
| Agents keep getting `[Kestrel guard]` denials | Read the reason in the activity feed; adjust the team's `focus` or the task if it needs something the guard forbids. |

`kestrel doctor` diagnoses most setup problems.
