# 0006: Hiding AI attribution in agent commits is opt-in

- **Status:** Accepted
- **Date:** 2026-11-12

## Context

The runner was first built for one owner who wanted agent commits and pull requests to carry
only their own name: it stripped `Co-Authored-By: Claude` lines and refused files that mentioned
Claude Code. As a default in an open-source tool, that would hide from collaborators and
reviewers that agents wrote the code, which many projects' contribution policies ask
contributors to disclose.

## Decision

Attribution is kept by default. `[pipeline] hide_ai_attribution = true` turns on the original
behavior: the guard blocks attribution lines, a `commit-msg` hook strips them, and the rule is
added to the agents' instructions.

## Consequences

- The default is transparent and matches common contribution policies.
- Owners who want the original behavior set one key. They remain responsible for following the
  policies of the repositories their agents contribute to.
