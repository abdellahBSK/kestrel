# 013: Cost that reads right for subscription users

- **Status:** Draft
- **Created:** 2026-11-15
- **Answers:** [Roadmap](../ROADMAP.md) L3
- **Target:** v0.2

## Problem

Kestrel prices tokens at API list prices. Most Claude Code users pay a flat subscription: for
them "$3.62 today" is not money they spent, and a large number can alarm or mislead. API users,
on the other hand, want exactly that number. One label does not fit both.

## Goals

- Every user sees a cost figure that means something for how they pay.
- No guessing about plans or prices Kestrel can't know.

## Functional requirements

| ID | Requirement |
|---|---|
| FR-001 | `[cost] mode` MUST choose how cost is shown: `api` (dollars at list prices, today's behavior), `subscription` (the share of a configured monthly price, or "API-equivalent value" if none is set), or `off` (tokens only). |
| FR-002 | `kestrel init` and the first dashboard visit SHOULD let the user pick the mode in one step; the default MUST be clearly labelled until they do. |
| FR-003 | In `subscription` mode, figures MUST be labelled "API-equivalent" and never presented as spend. |
| FR-004 | Budget caps in dollars (`daily_usd`) MUST keep working in every mode, computed at list prices, and say so. |
| FR-005 | Different projects MAY use different modes (an API-billed agent next to a subscription Claude Code). |

## Acceptance criteria

1. **Given** `mode = "subscription"`, **then** the overview shows "API-equivalent value" and no
   "cost" wording.
2. **Given** `mode = "off"`, **then** no dollar figure appears anywhere; caps in dollars still work
   and the docs say they use list prices.

## Open questions

- Can Kestrel detect, safely and locally, that Claude Code runs on a subscription, to pick the
  default? Only from information already on disk, never by calling a service.
