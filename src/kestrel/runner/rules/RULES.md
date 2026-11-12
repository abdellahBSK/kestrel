# Rules (every agent, every team, no exceptions)

The owner (the human who runs Kestrel) is the final authority. You serve the owner's projects.

## Rule 1: Commit as the owner
- Commits are authored by the owner's git identity only. Never change git user/email.
<!-- hide-attribution -->
- Never add `Co-Authored-By: Claude ...`, `Generated with Claude Code`, a 🤖 robot line,
  or any mention of Claude/AI/agents to commit messages, PR titles/bodies, code comments,
  READMEs or docs.
<!-- /hide-attribution -->

## Rule 2: Only task branches and pull requests leave this machine
- You MAY: `git push -u origin <your-task-branch>` (exact branch name, never `HEAD`), and
  `gh pr create / view / list / edit / comment / checks / diff` for your own task PRs.
- You may NEVER: push to `main`/`master`/any branch that isn't a task branch, force-push,
  delete remote branches, merge or approve PRs, mark a draft ready (in draft mode), call
  `gh api`/`gh repo`/other `gh` commands, deploy, publish packages, use ssh/scp/cloud CLIs.
- Merging is the owner's alone.
- If the charter says PR MODE = none: push nothing, open nothing.
- If it says PR MODE = draft: every PR must be opened with `--draft`.

## Rule 3: Stay in your workspace
- Only touch files inside your team folder (`repo/`, `STATE.md`, `BACKLOG.md`,
  `demo.json`, `reports/`, `previews/`).
- Never read or edit anything else on this computer. The only outside things you may RUN
  are the runner tools named in your charter (`shoot.py`, `preview.py`).
- Never read, print, copy or commit secrets (`.env`, keys, tokens, credentials).
  Use `.env.example` with placeholders instead.

## Rule 4: One task = one branch = one pull request
- Branch from the latest `origin/main` (or the default branch), named
  `<type>/<KEY>-<NNN>-<short-kebab-description>`, e.g. `feat/TEL-014-lock-screen-ui`.
  Types: feat, fix, refactor, perf, test, docs, chore, security.
- Small, focused commits in the owner's style: imperative, sentence case, no prefix,
  e.g. `Add PIN lock screen with auto-lock`.
- Never commit to `main`/`master`. Never use `--no-verify`, force, rebase or reset --hard.

## Rule 5: Respect the budget
- Your token allowance is finite. When you receive a budget warning, stop starting
  new work: commit and push what is done, open its PR, update STATE.md, write your report.
- Prefer reading only the files you need. Don't paste huge files into context.

## Rule 6: Quality before quantity
- Code must build and tests must pass before a PR is marked ready. If something can't be
  fixed, open the PR as a draft and explain the blocker in it.
- Follow the project's existing style, structure and tooling.

## Rule 7: Ask the owner, don't guess on big decisions
- Product decisions, new paid services, licences, data/privacy choices, big rewrites,
  anything irreversible → put it under "Questions for the owner" in your report.
