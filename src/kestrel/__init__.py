"""Kestrel: see what your AI agents are doing, what they cost, and when they get stuck.

Layers (dependencies point inward):

    kestrel.core      the event format, run folding and liveness rules (pure logic)
    kestrel.storage   the SQLite event store
    kestrel.adapters  turn other tools' logs into events (Claude Code)
    kestrel.api       the local HTTP server: dashboard, JSON API, POST /v1/events
    kestrel.client    the Python SDK for reporting events (`Reporter`)
    kestrel.cli       the `kestrel` command
    kestrel.runner    the optional scheduled runner for Claude Code agent teams
"""

# The project's display name. Change it here; the dashboard and CLI read it from this constant.
# (The package and command name `kestrel` also appear in pyproject.toml and the src/ folder name.)
NAME = "Kestrel"
__version__ = "0.1.0"
