# 010: Adapters for the OpenAI Agents SDK, LangGraph and CrewAI

- **Status:** Draft
- **Created:** 2026-11-15
- **Answers:** [Roadmap](../ROADMAP.md) L1
- **Target:** v0.2 (OpenAI Agents SDK, LangGraph), v0.3 (CrewAI and more by demand)

## Problem

The OpenTelemetry bridge (009) helps frameworks that export traces, but setting up tracing is a
step many people skip, and traces don't carry everything Kestrel can use (the agent tree as the
framework sees it, stop checks). A one-line adapter per popular framework, like the Claude Agent
SDK's, is the shortest path for the most users.

## Goals

- One line of code per framework, in the style of `ClaudeAgentOptions(hooks=...)`.
- Each adapter reports runs, agents with parents, tool calls with results and errors, and tokens,
  and checks for stops before each tool call where the framework allows it.

## Non-goals

- Required dependencies: each adapter imports its framework only inside the function that needs
  it (constitution IV); Kestrel stays dependency-free.
- Supporting every framework in-tree. Beyond the most used ones, the adapter guide and the
  OpenTelemetry bridge are the answer.

## Functional requirements

| ID | Requirement |
|---|---|
| FR-001 | `kestrel.adapters.openai_agents` MUST report runs, agents (including handoffs as child agents), tool calls and token usage from the OpenAI Agents SDK, through the hooks or tracing interface the SDK provides. |
| FR-002 | `kestrel.adapters.langgraph` MUST report a graph invocation as a run, nodes that run models or tools as agents and actions, and token usage, through LangChain/LangGraph callbacks. |
| FR-003 | `kestrel.adapters.crewai` MUST report a crew kickoff as a run, crew agents as agents, task and tool steps as actions, and token usage. |
| FR-004 | Every adapter MUST swallow its own errors: reporting never breaks the agent. |
| FR-005 | Where the framework lets a callback stop or refuse a step, the adapter MUST honor Kestrel stops (spec 008); where it can't, the docs MUST say so. |
| FR-006 | Each adapter MUST have tests driven by recorded framework callbacks, runnable without the framework installed, plus one optional integration test that uses the real framework. |
| FR-007 | Each adapter MUST be documented with a complete, runnable example. |

## Acceptance criteria

1. **Given** a two-agent OpenAI Agents SDK program with one handoff and one tool, **when** it
   runs with the adapter, **then** the dashboard shows one run, two agents (the second a child of
   the first), the tool call and tokens for both.
2. **Given** a stop requested for the run, **then** the next tool call is refused, if the
   framework supports it.

## Open questions

- [NEEDS CLARIFICATION: the exact hook and callback interfaces of each framework's current
  version: verify against their docs before planning, not from memory.]
- Which framework comes after these three? Decide by adapter requests (issue label `adapter`).
