# 009: OpenTelemetry bridge

- **Status:** Draft
- **Created:** 2026-11-15
- **Answers:** [Roadmap](../ROADMAP.md) L1
- **Target:** v0.2

## Problem

Many agent frameworks already emit OpenTelemetry traces (directly, or through instrumentation
libraries that follow the GenAI semantic conventions). Their users have to write a Kestrel
adapter today, even though their agents already describe every model call and tool call. One
bridge would make all of them report to Kestrel by setting an exporter endpoint.

## Goals

- An agent instrumented with OpenTelemetry reports to Kestrel by pointing its OTLP exporter at
  the dashboard. No Kestrel code in the agent.
- Spans become runs, agents, actions and tokens using the GenAI semantic conventions, with
  sensible fallbacks for spans that don't follow them.

## Non-goals

- Being a general trace store or trace viewer. Kestrel keeps what maps to its event format and
  drops the rest.
- Metrics and logs signals (traces only, first).

## User stories

1. As an agent builder whose framework exports OpenTelemetry traces, I set
   `OTEL_EXPORTER_OTLP_ENDPOINT=http://127.0.0.1:7777` and the token header, and my runs appear.
2. As a user of an OTel instrumentation library, my model calls show tokens and cost, and my tool
   calls show as actions, without configuration.

## Functional requirements

| ID | Requirement |
|---|---|
| FR-001 | `kestrel watch` MUST accept OTLP/HTTP trace exports at `POST /v1/traces`, authenticated with the ingest token. |
| FR-002 | The JSON encoding of OTLP MUST be supported. The protobuf encoding SHOULD be supported without adding a runtime dependency (constitution IV). [NEEDS CLARIFICATION: a minimal standard-library protobuf decoder for the trace messages, or JSON only with documented exporter settings?] |
| FR-003 | A trace MUST map to a run; the service name (or a configured attribute) MUST map to the project. |
| FR-004 | Spans following the GenAI semantic conventions MUST map as: agent spans to agents (with parent from the span tree), model-call spans to `agent.tokens` (model, input and output tokens), tool spans to `agent.action` (tool name, status from the span status). |
| FR-005 | Spans that match no convention MUST NOT be lost silently: they appear as actions named after the span, so users can see what to map. |
| FR-006 | Span events and attributes MUST pass through the same secret scrubbing as every event. |
| FR-007 | A trace whose root span ended MUST finish its run; a trace with open spans and no new spans for `heartbeat_timeout` MUST become *lost*, like any run. |
| FR-008 | The mapping MUST be documented with an example for at least two instrumentation libraries. |

## Acceptance criteria

1. **Given** a script instrumented with the OpenTelemetry SDK and an OTLP/HTTP JSON exporter
   pointed at Kestrel, **when** it makes a model call and a tool call inside an agent span,
   **then** the dashboard shows one run with one agent, one action and the call's tokens.
2. **Given** a span with an error status, **then** its action shows as an error.
3. **Given** no token, **then** the export is refused with 401.

## Open questions

- Which attribute names are stable enough in the GenAI conventions to rely on, and which need
  per-library fallbacks? Track the conventions' version in the mapping.
- Should Kestrel also accept OTLP on the standard port 4318 when asked?
