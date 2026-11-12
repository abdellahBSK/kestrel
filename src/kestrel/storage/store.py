"""The event store: one SQLite file (<home>/data/events.db) that every adapter writes to and the
dashboard reads from.

Events are append-only and deduplicated by id, so an adapter may safely resend. Heartbeats only
matter as "the latest one", so they live in a small table of their own instead of the log.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

from kestrel import paths
from kestrel.core.events import HEARTBEATS

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    seq      INTEGER PRIMARY KEY AUTOINCREMENT,
    id       TEXT NOT NULL UNIQUE,
    ts       REAL NOT NULL,
    type     TEXT NOT NULL,
    project  TEXT NOT NULL,
    run      TEXT,
    agent    TEXT,
    data     TEXT NOT NULL,
    received REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS events_run ON events (project, run, ts);
CREATE INDEX IF NOT EXISTS events_type ON events (type, ts);
CREATE TABLE IF NOT EXISTS heartbeats (
    project TEXT NOT NULL,
    run     TEXT NOT NULL,
    agent   TEXT NOT NULL DEFAULT '',
    ts      REAL NOT NULL,
    PRIMARY KEY (project, run, agent)
);
"""


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), timeout=15, check_same_thread=False, isolation_level=None)
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=NORMAL")
            self.db.executescript(SCHEMA)

    def close(self) -> None:
        with self.lock:
            self.db.close()

    # ── writing ──

    def add(self, events: list[dict]) -> tuple[int, int]:
        """Store normalized events (see events.normalize). Returns (accepted, duplicates)."""
        now = time.time()
        rows, beats = [], []
        for e in events:
            if e["type"] in HEARTBEATS:
                beats.append((e["project"], e["run"], e.get("agent") or "", e["ts"]))
            else:
                rows.append(
                    (e["id"], e["ts"], e["type"], e["project"], e["run"], e.get("agent"), json.dumps(e["data"]), now)
                )
        with self.lock:
            self.db.execute("BEGIN IMMEDIATE")
            try:
                before = self.db.total_changes
                self.db.executemany(
                    "INSERT OR IGNORE INTO events (id, ts, type, project, run, agent, data, received) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    rows,
                )
                inserted = self.db.total_changes - before
                self.db.executemany(
                    "INSERT INTO heartbeats (project, run, agent, ts) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT (project, run, agent) DO UPDATE SET ts = MAX(ts, excluded.ts)",
                    beats,
                )
                self.db.execute("COMMIT")
            except BaseException:
                self.db.execute("ROLLBACK")
                raise
        return inserted + len(beats), len(rows) - inserted

    # ── reading ──

    def _all(self, sql: str, args: tuple = ()) -> list[tuple]:
        with self.lock:
            return self.db.execute(sql, args).fetchall()

    def projects(self) -> list[str]:
        """Every project that has reported anything, most recently active first."""
        return [r[0] for r in self._all("SELECT project FROM events GROUP BY project ORDER BY MAX(ts) DESC")]

    def runs(self, project: str, limit: int = 20) -> list[dict]:
        """A project's runs, newest first: {id, started, last}."""
        rows = self._all(
            "SELECT run, MIN(ts), MAX(ts) FROM events WHERE project = ? AND run IS NOT NULL "
            "GROUP BY run ORDER BY MIN(ts) DESC LIMIT ?",
            (project, limit),
        )
        return [{"id": r[0], "started": r[1], "last": r[2]} for r in rows]

    def run_events(self, project: str, run: str) -> list[tuple]:
        """(ts, type, agent, data) for one run, in time order."""
        rows = self._all(
            "SELECT ts, type, agent, data FROM events WHERE project = ? AND run = ? ORDER BY ts, seq", (project, run)
        )
        return [(r[0], r[1], r[2], json.loads(r[3])) for r in rows]

    def run_version(self, project: str, run: str) -> tuple:
        """Changes whenever the run gets a new event or heartbeat (a cache key)."""
        seq = self._all("SELECT MAX(seq) FROM events WHERE project = ? AND run = ?", (project, run))[0][0]
        return seq, self.heartbeat(project, run)

    def heartbeat(self, project: str, run: str) -> float | None:
        return self._all("SELECT MAX(ts) FROM heartbeats WHERE project = ? AND run = ?", (project, run))[0][0]

    def tokens_since(self, since: float) -> list[tuple]:
        """(project, ts, data) of every agent.tokens event at or after `since`."""
        rows = self._all("SELECT project, ts, data FROM events WHERE type = 'agent.tokens' AND ts >= ?", (since,))
        return [(r[0], r[1], json.loads(r[2])) for r in rows]

    def pull_requests(self, project: str) -> list[dict]:
        """Pull requests reported for a project and not closed since, newest first."""
        state: dict[int, dict] = {}
        for ts, typ, data in (
            (r[0], r[1], json.loads(r[2]))
            for r in self._all(
                "SELECT ts, type, data FROM events WHERE project = ? AND type IN ('pr.opened', 'pr.closed') "
                "ORDER BY ts, seq",
                (project,),
            )
        ):
            if typ == "pr.opened":
                state[data["number"]] = {**data, "ts": ts}
            else:
                state.pop(data["number"], None)
        return sorted(state.values(), key=lambda p: p["ts"], reverse=True)


_STORES: dict[Path, Store] = {}
_LOCK = threading.Lock()
DEFAULT_PATH: Path | None = None  # tests and the demo point this elsewhere


def open_store(path: Path | None = None) -> Store:
    """The process-wide store for this home folder."""
    path = (path or DEFAULT_PATH or paths.HOME / "data" / "events.db").resolve()
    with _LOCK:
        if path not in _STORES:
            _STORES[path] = Store(path)
        return _STORES[path]
