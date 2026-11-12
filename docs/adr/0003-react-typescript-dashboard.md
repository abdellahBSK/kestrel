# 0003: The dashboard is React + TypeScript, built into the package

- **Status:** Accepted
- **Date:** 2026-11-10

## Context

The first dashboard was a single hand-written HTML page. It was hard to extend and did not look
like a professional tool, which matters for an open-source project people judge in ten seconds.

## Decision

A Vite + React 19 + TypeScript app (Tailwind CSS 4, Radix UI primitives, TanStack Query, cmdk,
lucide icons), every version pinned. `npm run build` writes static files into
`src/kestrel/static/`, and the Python server serves them. The wheel ships the built files, so
users never need Node.

## Consequences

- Contributors need Node only for frontend work.
- The UI has typed API models, tests (vitest), and lint and format checks in CI.
- The page runs under a strict Content-Security-Policy with no inline scripts.

## Alternatives considered

- **Server-rendered templates with htmx**: no build step, but interactive views (agent trees,
  command menu, charts) would be harder to keep consistent.
- **Vue or Svelte**: fine choices; React has the largest contributor pool and component
  ecosystem.
