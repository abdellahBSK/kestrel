# Contributing to Kestrel

Thanks for helping. Kestrel is small on purpose, and every change is reviewed for whether it
keeps the [constitution](specs/constitution.md): honest status, agent-agnostic, local-first, a
zero-dependency Python core, one command to try.

## Ways to help

- **Try it and report what confused you.** First-run friction is a bug.
- **Write an adapter** for the framework you use: see [Writing an adapter](docs/events.md#writing-an-adapter).
- **Fix a [good first issue](../../issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).**
- **Improve the docs.** If you had to read the code to understand something, the docs missed it.

## How changes are made

Kestrel is built [spec-first](specs/README.md):

| Change | What to open |
|---|---|
| Typo, docs fix, obvious bug, dependency bump | A pull request directly. |
| New feature or behavior change | An issue first, then a spec PR (`specs/NNN-name/spec.md`), then implementation PRs. |
| Architecture change (new dependency, storage, protocol) | An ADR in `docs/adr/` alongside the spec. |

## Development setup

You need Python 3.11+ and Node 20+ (Node only for the web app).

```bash
git clone https://github.com/abdellahBSK/kestrel && cd kestrel
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install                 # runs ruff and basic checks on each commit

cd frontend && npm ci && npm run build && cd ..
kestrel demo                       # http://127.0.0.1:7777
```

For frontend work, run the API and the Vite dev server side by side:

```bash
kestrel demo --no-browser          # API on :7777
cd frontend && npm run dev         # http://localhost:5173, proxies /api to :7777
```

## Checks

CI runs all of these on Linux, macOS and Windows; run them before you push.

```bash
ruff check . && ruff format --check .
pytest
cd frontend && npm run typecheck && npm run lint && npm run format:check && npm test
```

`make check` runs everything on Linux and macOS.

## Code guidelines

- **Layers.** `kestrel.core` must not import from other Kestrel packages. See
  [docs/architecture.md](docs/architecture.md).
- **No new runtime dependencies** in the Python package without an ADR.
- **Tests** for every behavior change. Tests never touch your real home folder or
  `~/.claude`: `tests/conftest.py` points everything at temporary folders.
- **Times** are UTC everywhere except the final display.
- **Cross-platform.** No shell-specific syntax, hard-coded path separators or OS-only APIs
  outside clearly named optional modules.
- **Frontend**: TypeScript strict mode, components in `frontend/src/components`, API types in
  `frontend/src/lib/api.ts`. Colors come from the tokens in `index.css`; status is never shown by
  color alone.

## Commits and pull requests

- Small, focused commits. Messages are imperative and sentence case, with no prefix:
  `Show cut-off agents in the run header`, not `feat: added stuff`.
- One topic per pull request. Fill in the template, link the spec or issue, and add a line to
  `CHANGELOG.md` under *Unreleased* for anything user-visible.
- If AI tools wrote a meaningful part of your change, say so in the PR description. That is
  welcome here; we just want reviewers to know.

## Releases

Maintainers tag `vX.Y.Z` on `main`. The release workflow builds the web app and the wheel,
publishes to PyPI and creates the GitHub release from the changelog.

## Code of conduct

Everyone taking part follows the [Code of Conduct](CODE_OF_CONDUCT.md).
