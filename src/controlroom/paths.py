"""Where Control Room finds things.

Assets (the dashboard page, role prompts, the guard hook, git hooks, helper tools) ship inside
the package. Your data (config, team workspaces, state, logs, reports) lives in the home folder:
$CONTROLROOM_HOME if set, otherwise ~/.controlroom.
"""

from __future__ import annotations

import os
from pathlib import Path

HOME_ENV = "CONTROLROOM_HOME"

PKG = Path(__file__).resolve().parent
RUNNER = PKG / "runner"
STATIC = PKG / "static"

HOME = Path(os.environ.get(HOME_ENV) or Path.home() / ".controlroom").expanduser().resolve()
CONFIG = HOME / "config.toml"
