# 008: Control and cost: stop buttons, budget caps, alerts, dollars

- **Status:** Done
- **Created:** 2026-11-12
- **Parent:** [001](../001-kestrel-v0.1/spec.md) tasks T060–T065

## Problem

Kestrel shows what agents do, but the owner can't act on it. An agent stuck in a loop keeps
spending until someone finds the right terminal. A project can burn through a day's budget
before anyone looks. Failures and lost runs are only noticed when someone opens the dashboard.
Tokens are shown, but what people budget in is money.

## Goals

- **See the cost**: estimated dollars next to tokens for every agent, run, project and day.
- **Act from the dashboard**: stop one agent, one run, a whole project, or everything.
- **Set limits that hold**: per-project daily caps in tokens or dollars that halt agents.
- **Be told**: alerts in the dashboard, on the desktop and to a webhook (Slack, Discord, …).
- **Know each agent's record**: duration, errors and retries per agent.
- **Keep the store small**: a retention setting and `kestrel prune`.

## Non-goals

- Exact billing. Costs are estimates at first-party API list prices; subscription plans and
  partner platforms price differently.
- Killing processes. Stops are delivered through each source's control channel; Kestrel never
  kills arbitrary processes.

## Cost

| ID | Requirement |
|---|---|
| FR-001 | Kestrel MUST estimate the cost of every `agent.tokens` event from a built-in price table of Claude models (USD per million input, output, cache-write and cache-read tokens), unless the event carries its own `cost_usd`. |
| FR-002 | `[prices."<model name part>"]` in the config MUST add or override prices, so any provider's models can be priced. |
| FR-003 | Tokens from unknown models MUST NOT be guessed: their cost is unknown and shown as such. |
| FR-004 | The dashboard MUST show cost per agent, run and project and for today and the week, labelled as an estimate at API prices. Opus-equivalent token weighting stays available through `[model_weights]`. |

## Control

| ID | Requirement |
|---|---|
| FR-010 | The owner MUST be able to request a stop for one agent, one run, one project, or everything, from the dashboard and from the CLI (`kestrel stop [PROJECT] [--run R] [--agent A]`). |
| FR-011 | A stop MUST apply to the runs that exist when it is requested, never to runs started later, so a stopped project can start again. |
| FR-012 | Stops MUST reach agents through every source Kestrel ships: the Claude Code hook and the Claude Agent SDK adapter (blocking the agent's next tool call and ending the session or subagent), the Python client (`run.stop_requested`, `run.check()`), the runner's guard, and HTTP (`GET /v1/control`). |
| FR-013 | `[projects.<name>] daily_tokens` and `daily_usd` MUST cap a project's spend per local day: once reached, its agents are stopped with a budget reason, through the same channel. A run's own `budget` in `run.started` MUST cap that run. |
| FR-014 | The dashboard MUST show that a stop was requested until the agent or run finishes, and say why an agent was stopped. |
| FR-015 | The runner's global `STOP` flag keeps working as before and is shown as "Stop all". |

## Alerts

| ID | Requirement |
|---|---|
| FR-020 | Kestrel MUST raise alerts for: an agent that may be stuck (stale in a live run), a lost run, a failed run, a project or day reaching the budget warning share (`warn_at`), a project stopped by its cap, agents waiting for the owner (permission prompts, questions), and pull requests waiting for review. |
| FR-021 | The dashboard MUST show current alerts (a count in the top bar and a list), and toast new critical ones. |
| FR-022 | While `kestrel watch` runs, new alerts MUST be sent once each as desktop notifications (`[alerts] desktop`, default on) and to `[alerts] webhook` if set, as JSON that Slack and Discord accept. Which kinds are sent is configurable. |
| FR-023 | No alert may be sent anywhere except the desktop and the configured webhook. |

## Agents' record

| ID | Requirement |
|---|---|
| FR-030 | Each agent MUST show its wall-clock duration, its error count and its retry count. A retry is an action that repeats a failed action of the same agent (same tool and detail). |

## Retention

| ID | Requirement |
|---|---|
| FR-040 | `[storage] retention_days` (default 0: keep everything) MUST delete runs whose last event is older, when the dashboard starts and once a day. |
| FR-041 | `kestrel prune [--days N] [--dry-run]` MUST do the same on demand and report what it removed. |

## Acceptance criteria

1. **Given** tokens from `claude-sonnet-5-5`, **then** their cost is shown at Sonnet 5.5 prices;
   **given** tokens from an unknown model, **then** the cost shows as unknown, not zero.
2. **Given** a running Claude Code session, **when** the owner clicks Stop on its run, **then**
   the session's next tool call is refused, the session ends, and the run shows *stopped*.
3. **Given** a stop requested for a project, **when** a new run of that project starts later,
   **then** it is not stopped.
4. **Given** `daily_usd = 5` for a project that has spent $5 today, **then** its agents' next
   tool calls are refused with a budget reason and an alert is raised.
5. **Given** an agent stale for 11 minutes in a live run, **then** the dashboard shows an alert
   and, with `kestrel watch` running, one desktop notification and one webhook post are sent.
6. **Given** `retention_days = 30`, **then** runs last active 31 days ago are deleted and newer
   ones are kept.
