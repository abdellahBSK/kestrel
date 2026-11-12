# Releasing Kestrel

A release is a tag `vX.Y.Z` on `main`. Pushing the tag runs
[`.github/workflows/release.yml`](.github/workflows/release.yml), which builds the dashboard and
the package, checks that the tag matches the version, then:

1. publishes `kestrel-agents` to PyPI (trusted publishing: no token is stored anywhere),
2. creates the GitHub release with the changelog section as its notes and the files attached,
3. pushes the Docker image `ghcr.io/abdellahbsk/kestrel` (tags `X.Y.Z`, `X.Y` and `latest`) for
   `linux/amd64` and `linux/arm64`.

## One-time setup

1. **PyPI trusted publisher.** Sign in to [pypi.org](https://pypi.org), open
   *Your account → Publishing → Add a new pending publisher* and enter:

   | Field | Value |
   |---|---|
   | PyPI project name | `kestrel-agents` |
   | Owner | `abdellahBSK` |
   | Repository name | `kestrel` |
   | Workflow name | `release.yml` |
   | Environment name | `pypi` |

   The first successful release creates the project and turns the pending publisher into a
   normal one.
2. **GitHub environment** (recommended). In the repository's *Settings → Environments*, create
   `pypi` and add yourself as a required reviewer, so every PyPI upload waits for your click.
3. **Docker image visibility.** After the first release, open the package on GitHub
   (*Packages → kestrel → Package settings*) and make it public so `docker pull` works without
   logging in.

## Each release

1. Make sure `main` is green in CI and `CHANGELOG.md` lists everything under *Unreleased*.
2. Prepare it:

   ```bash
   python scripts/release.py 0.1.0
   ```

   This bumps `kestrel.__version__`, moves *Unreleased* to a dated `0.1.0` section, commits
   `Release 0.1.0` and creates the annotated tag `v0.1.0`. Nothing leaves your machine.
3. Publish it:

   ```bash
   git push origin main v0.1.0
   ```

4. Watch the *Release* workflow. If a step fails after PyPI accepted the upload, fix forward
   with a patch release: a version on PyPI can never be replaced.
5. After the release, start the next development version by adding `.dev0` (for example
   `0.2.0.dev0`) in `src/kestrel/__init__.py`.

## Versioning

[Semantic versioning](https://semver.org). Before 1.0, minor versions may break things; the
changelog's *Changed* section says what and how to adapt. The event format has its own version
(`v` in each event), which only changes with an incompatible format.
