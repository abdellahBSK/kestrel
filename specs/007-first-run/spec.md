# 007: First run: `kestrel init` and `kestrel doctor`

- **Status:** Done
- **Created:** 2026-11-12
- **Parent:** [001](../001-kestrel-v0.1/spec.md) tasks T050, T051

## Problem

Kestrel works with no config at all, but the moment someone wants a budget line, a project's
display name or the runner, they have to find `config.example.toml` in the repository, guess
where to copy it, and edit an example full of teams that aren't theirs. When something doesn't
show up (no events, hook not firing, dashboard not built, port taken), there is no way to find
out why short of reading the code.

## Goals

- One command writes a commented config, in the right place, that does nothing surprising.
- One command checks a setup and says, in plain words, what is wrong and how to fix it.
- The runner is documented well enough to set up without reading its code.

## Functional requirements

| ID | Requirement |
|---|---|
| FR-001 | `kestrel init` MUST create the home folder and write `<home>/config.toml` from a template shipped in the package, then print what to do next. |
| FR-002 | Every active value in that template MUST equal Kestrel's built-in default, so `init` changes nothing until the user edits it. Runner teams, schedules and project names MUST be present but commented out. |
| FR-003 | `kestrel init` MUST NOT overwrite an existing config unless given `--force`, and then MUST back it up first. |
| FR-004 | `kestrel doctor` MUST check: Python version; the home folder; whether the config parses (showing the line of a TOML error); the event store; that the web app is built; whether the dashboard port is free or held by Kestrel; Claude Code hooks (installed, pointing at this Python and this home, logged errors). When runner teams are configured, it MUST also check `claude`, `git` and `gh`, and that the home folder is not inside a git repository. |
| FR-005 | Every `kestrel doctor` finding MUST say how to fix it. It MUST exit 1 when a check fails (warnings alone exit 0). |
| FR-006 | `docs/runner.md` MUST explain requirements, setup, configuration, what happens during a run, the guard's rules, scheduling on Windows, macOS and Linux, and troubleshooting. |
| FR-007 | `docs/adapters.md` MUST show how to report from an agent framework Kestrel doesn't support yet, with a worked example. |

## Acceptance criteria

1. **Given** an empty home, **when** the user runs `kestrel init`, **then** `config.toml` exists,
   loads to the same values as no config, and the command lists the next steps.
2. **Given** an existing config, **then** `kestrel init` refuses and changes nothing; with
   `--force` it saves a backup and writes a fresh one.
3. **Given** a config with a TOML syntax error, **then** `kestrel doctor` names the file and the
   line, and exits 1.
4. **Given** Claude Code hooks pointing at another home folder, **then** `kestrel doctor` warns
   that events go elsewhere and says how to reinstall.
