# Roadmap

This page starts every release. It lists, honestly, what Kestrel does not do well yet, why that
matters, and which spec answers it. The first principle of the [constitution](constitution.md)
is honest status; that applies to Kestrel itself too.

Last reviewed for **v0.1.0** (2026-11-15).

## Known limitations of v0.1.0

| # | Limitation | Who it hurts | Answer | Release |
|---|---|---|---|---|
| L1 | **Automatic reporting covers Claude Code and the Claude Agent SDK only.** Agents built with anything else must send events themselves. | Most agent builders: LangGraph, CrewAI, OpenAI Agents SDK, AutoGen, custom stacks. | [009 OpenTelemetry bridge](009-opentelemetry-bridge/spec.md), then [010 framework adapters](010-framework-adapters/spec.md). | v0.2 |
| L2 | **Each Claude Code hook call costs about 130 ms**, mostly Python starting up, twice per tool call. | Heavy Claude Code users, long sessions with hundreds of tool calls. | [011 Faster hook](011-faster-hook/spec.md). | v0.2 |
| L3 | **Costs are list-price estimates.** Most Claude Code users pay a subscription, so "$3.62 today" is not their bill. | Subscription users, who may misread the number. | [013 Cost modes](013-cost-modes/spec.md). | v0.2 |
| L4 | **Alerts are sent only while `kestrel watch` runs.** Close the dashboard and a stuck agent goes unnoticed. | Anyone running agents overnight. | A background service (`kestrel service install`) for macOS, Linux and Windows. *Spec to write.* | v0.3 |
| L5 | **A stop reaches only agents that ask.** A process that never checks for stops can't be halted from the dashboard. | Custom agents that report but don't poll. | Optional process registration (a PID in `run.started`) so local runs can be ended as a last resort. *Spec to write.* | v0.3 |
| L6 | **The runner schedules itself only on Windows.** macOS and Linux need a hand-written cron entry. | Runner users off Windows. | `kestrel schedule install` with launchd and systemd timers. *Spec to write.* | v0.3 |
| L7 | **Unmeasured at scale.** The server polls, folds runs on read and has not been benchmarked past about 100,000 events. | Busy machines with months of history. | A performance budget, a benchmark in CI, and incremental folding if needed. *Spec to write.* | v0.3 |
| L8 | **One computer, one person.** No shared dashboard, no accounts. | Small teams, shared devboxes, companies. | [012 Team mode](012-team-mode/spec.md) (draft). | v0.4 |

## Releases

| Release | Theme | Done when |
|---|---|---|
| **v0.2** | **Any agent** | Agents instrumented with OpenTelemetry report with no Kestrel code (009); first-party adapters for the OpenAI Agents SDK, LangGraph and CrewAI (010); the Claude Code hook adds under 20 ms per call (011); costs read correctly for subscription users (013). |
| **v0.3** | **Always on** | Alerts without the dashboard open (L4), last-resort stops for registered processes (L5), scheduling on every OS (L6), a measured performance budget (L7). |
| **v0.4** | **Teams** | Several people and machines on one dashboard, with authentication (012). |
| **v1.0** | **Stable** | The v1 event format unchanged for six months; adapters for the five most used agent frameworks; no known data-loss or wrong-status bug open; upgrade path documented. |

Dates follow the work, not the other way round. Each release is cut with
[`scripts/release.py`](../scripts/release.py) once its specs are done.

## How this list is kept

- **Before each release**, re-read every limitation: close the ones the release answers, and
  add what users ran into (issues labelled `bug` and `enhancement` are the main source).
- **A limitation becomes work through a spec.** Rows marked *spec to write* get one before
  anyone starts building.
- **Anyone can propose a row** by opening an issue: describe what you hit, not the fix.
