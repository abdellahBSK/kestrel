# Specs

Kestrel is built **spec-first**. Every user-visible change starts as a written spec, is turned
into a plan and a task list, and only then into code. The code and the tests are checked against
the spec, not the other way around.

```
constitution.md  ─▶  NNN-feature/spec.md  ─▶  plan.md  ─▶  tasks.md  ─▶  pull requests
 (principles)         (what and why)         (how)        (steps)       (one task each)
```

| File | Answers | Written by |
|---|---|---|
| [`constitution.md`](constitution.md) | What we never trade away. Every spec and plan is checked against it. | Maintainers |
| `NNN-name/spec.md` | **What** users need and **why**: problem, user stories, requirements, acceptance criteria. No implementation detail. | Anyone proposing a feature |
| `NNN-name/plan.md` | **How**: architecture, data, risks, phases. | The implementer |
| `NNN-name/tasks.md` | The ordered, reviewable steps, each small enough for one commit or PR. | The implementer |

Architecture decisions that outlive a single feature are recorded as ADRs in
[`docs/adr/`](../docs/adr).

## Index

| # | Spec | Status |
|---|---|---|
| 001 | [Kestrel v0.1: an open-source monitor for AI agents](001-kestrel-v0.1/spec.md) | In progress |
| 002 | [Honest liveness: heartbeats, stale and lost](002-honest-liveness/spec.md) | Done |
| 003 | [UTC in storage, local time on screen](003-utc-everywhere/spec.md) | Done |
| 004 | [QA waits for the tester](004-pipeline-order/spec.md) | Done |
| 005 | [Event format v1](005-event-format-v1/spec.md) | Done |
| 006 | [Claude Code and Claude Agent SDK adapters](006-claude-code-hooks/spec.md) | Done |

## Proposing a change

1. Open a [feature request](../../../issues/new?template=feature_request.yml) to check the idea
   fits before writing anything long.
2. Copy [`templates/spec.md`](templates/spec.md) to `specs/NNN-short-name/spec.md` (next free
   number) and open a pull request with just the spec. Discussion happens on that PR.
3. Once the spec is merged, add `plan.md` and `tasks.md` from the templates, then implement task
   by task. Each implementation PR links the spec and the task it completes.

Small fixes (a typo, a crash with an obvious cause, a dependency bump) need no spec: open the PR
directly.

## Writing a good spec

- Lead with the **problem a real user has**, in their words. "The sidebar says *running* for a
  run that died an hour ago" beats "improve status accuracy".
- Requirements are **testable**: each `FR-NNN` must be checkable by a test or a person in a
  minute. Use MUST / SHOULD / MAY.
- Acceptance criteria are written as **Given / When / Then**.
- Say what is **out of scope**. It is the cheapest way to keep a feature small.
- Mark anything undecided with `[NEEDS CLARIFICATION: question]` instead of guessing.
