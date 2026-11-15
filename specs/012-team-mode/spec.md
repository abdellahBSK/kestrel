# 012: Team mode

- **Status:** Draft (problem statement only; to be detailed after v0.2)
- **Created:** 2026-11-15
- **Answers:** [Roadmap](../ROADMAP.md) L8
- **Target:** v0.4

## Problem

Kestrel is one dashboard for one person on one computer. Teams that run agents on several
machines (laptops, a shared devbox, CI runners) can't see them in one place, and anyone who
exposes the dashboard beyond localhost has no login to protect it.

## Goals

- Several machines report to one Kestrel; several people view and control it.
- Exposing Kestrel to a network is safe by default: authentication is required, and the
  local-first, zero-telemetry promise (constitution III) still holds for single-user installs.

## Non-goals

- A hosted service run by the project.

## Questions this spec must answer before planning

- Identity: local accounts, a reverse proxy's identity (OIDC via a proxy), or both?
- Permissions: who may stop agents, change caps, see costs?
- Storage: does SQLite hold for a team, or is an optional server database needed (and how does
  that square with constitution IV)?
- Transport: do reporters on other machines send over HTTPS directly, or through a local relay
  that buffers when offline?
- Privacy: secret scrubbing happens on the reporting machine, before anything leaves it.
