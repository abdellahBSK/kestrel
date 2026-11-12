# 001: Kestrel v0.1, an open-source monitor for AI agents

- **Status:** In progress
- **Created:** 2026-11-10
- **Related:** [002](../002-honest-liveness/spec.md), [003](../003-utc-everywhere/spec.md),
  [004](../004-pipeline-order/spec.md), [005](../005-event-format-v1/spec.md)

## Problem

People now run AI agents that work for minutes or hours: coding agents that open pull requests,
research agents, multi-agent pipelines with a lead delegating to specialists. While they run,
the owner is blind:

- **Is it still working, or stuck?** A terminal that has been silent for ten minutes could be
  compiling or could be dead. Agents report "working" right up to the moment they are killed.
- **What did it actually do?** Tool calls scroll past in a log nobody reads.
- **What did it cost?** Token usage is spread across logs and providers' consoles, a day late.
- **What is waiting for me?** Pull requests to review, questions the agents left, failed runs.

Kestrel started as a private dashboard for one person's team of Claude Code agents. It had the
right idea and three bugs that destroyed trust in it (specs 002–004). This spec makes it a
product anyone can install and point at their own agents, whatever they are built with.

## Goals

- Anyone can see every agent run on their machine **live**, with honest status, in under five
  minutes from discovering the project.
- Works with **any** agent framework through a small documented event format.
- Shows cost in tokens (and money, when known), per agent, run and project.
- Lets the owner act: stop an agent or a project, cap a budget, see what needs review.

## Non-goals (v0.1)

- A hosted or multi-user service. Kestrel is local-first (constitution III).
- Replacing tracing platforms (OpenTelemetry backends, LLM observability SaaS). Kestrel is the
  owner's control room, not a trace store; an OpenTelemetry bridge is a later adapter.
- Running agents. The Claude Code runner is optional and stays an adapter.

## Users

- **Solo developers** running coding agents (Claude Code, Codex-style CLIs, Aider, custom SDK
  agents) on their own repositories, often overnight.
- **Agent builders** developing multi-agent systems who need to see the tree of agents, their
  actions and their failures while iterating.
- **Small teams** sharing one machine or devbox that runs scheduled agent work.

## User stories

1. As a developer, I run `kestrel demo` and immediately understand what the tool shows, without
   configuring anything.
2. As an agent builder, I add five lines with the Python client (or one `curl` per event from any
   language) and my runs appear live.
3. As a Claude Code user, I install a hook once and every session shows up, with subagents.
4. As an owner, I see at a glance which projects are running, stuck, lost, failed or never run,
   and the sidebar dot is never wrong.
5. As an owner, I open a run and see each agent's state, what it is doing in plain language (raw
   command on hover), tokens, cost, errors, retries and duration.
6. As an owner, I get an alert when an agent is stuck, a run fails, a budget is about to run out
   or a pull request is waiting.
7. As an owner, I stop one agent, or everything in a project, from the dashboard.
8. As an owner, I set a budget and agents are actually halted when they reach it.
9. As a contributor, I can write an adapter for my framework by reading one document.

## Functional requirements

| ID | Requirement |
|---|---|
| FR-001 | Kestrel MUST accept events in the documented v1 format through a Python client, a CLI and an authenticated HTTP endpoint. |
| FR-002 | Events MUST cover: run started, run heartbeat, run finished/failed, agent started, action, message, tokens, notice, heartbeat, finished, PR opened/closed. |
| FR-003 | Kestrel MUST derive run and agent state from evidence (spec 002); it MUST NOT trust a self-reported "working". |
| FR-004 | The dashboard MUST show project health in the sidebar and order active projects first, collapsing projects that never ran. |
| FR-005 | Times MUST be stored and served in UTC and shown in the viewer's local time (spec 003). |
| FR-006 | Action rows MUST show a human-readable summary, with the raw command available on hover. |
| FR-007 | Kestrel MUST show tokens per agent, run, project and day; it SHOULD show estimated cost in USD next to tokens, with Opus-equivalent normalization available as an option. |
| FR-008 | Kestrel MUST provide `kestrel demo`, which shows every state with realistic fake data in a throwaway folder. |
| FR-009 | Kestrel MUST read its settings from one TOML config file; every setting MUST have a working default. |
| FR-010 | Kestrel SHOULD alert (in-app, and optionally desktop notifications or a webhook) on stuck agents, failed runs, budget thresholds and PRs awaiting review. |
| FR-011 | Kestrel SHOULD offer stop controls per agent and per project, delivered to adapters that support them. |
| FR-012 | Budget caps SHOULD halt agents that report through an adapter able to enforce them. |
| FR-013 | Kestrel SHOULD show error count, retry count and wall-clock duration per agent. |
| FR-014 | Kestrel MUST ship a first-party adapter for Claude Code; it SHOULD ship one for the Claude Agent SDK. |
| FR-015 | The usage chart MUST NOT draw "You today / this week" bars when no limit or personal usage exists. |

## Non-functional requirements

- **Install:** one command (`pipx install kestrel-agents`, `uvx`, or `docker compose up`).
- **Security:** binds to 127.0.0.1; ingest token; secrets scrubbed from the feed; strict CSP; no
  telemetry (constitution III).
- **Performance:** dashboard API answers in under 200 ms for a store of 100,000 events; the page
  stays responsive with 50 live agents.
- **Portability:** Linux, macOS, Windows; Python 3.11–3.13; evergreen browsers.
- **Accessibility:** status is never conveyed by color alone; keyboard navigable; light and dark
  themes.
- **Rename-ability:** the display name lives in one constant (`kestrel.NAME`).

## Acceptance criteria

1. **Given** a fresh machine with Python 3.11, **when** the user runs the documented install and
   `kestrel demo`, **then** a browser shows six projects in every health state within one minute.
2. **Given** a script using `Reporter`, **when** it starts a run and crashes, **then** the run
   shows as *failed* with the exception, and its agents as *cut off*.
3. **Given** a run whose process was killed, **when** 45 seconds pass without events, **then**
   the run shows as *lost* and the project's sidebar dot is not green.
4. **Given** an event containing `ghp_…` or `sk-ant-…`, **when** it is stored, **then** the value
   is replaced by `[redacted]` everywhere it is shown.
5. **Given** a web page in the user's browser, **when** it tries to POST to `/v1/events`, **then**
   the request is refused.
6. **Given** no config file, **when** the server starts, **then** it runs and shows reported
   projects with no budget meters.

## Open questions

- Which alert channels ship in v0.1 (desktop notification, webhook, both)?
- Is a Docker image worth maintaining before v0.2, given the zero-dependency install?
