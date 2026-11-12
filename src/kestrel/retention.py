"""Keeping the event store small (spec 008): delete runs nobody will look at again.

`[storage] retention_days` (0 = keep everything) is applied when the dashboard starts and once a
day while it runs; `kestrel prune` applies it, or any other number of days, on demand.
"""

from __future__ import annotations

import time

DAY = 86_400


def cutoff(days: float, now: float | None = None) -> float:
    return (time.time() if now is None else now) - days * DAY


def prune(store, days: float, *, dry_run: bool = False, now: float | None = None) -> dict:
    """Delete runs whose last event is older than `days` days. Returns what was (or would be) removed."""
    if days <= 0:
        return {"runs": 0, "events": 0, "dry_run": dry_run}
    limit = cutoff(days, now)
    if dry_run:
        old = store._all(
            "SELECT COUNT(*), COALESCE(SUM(n), 0) FROM (SELECT COUNT(*) AS n FROM events WHERE run IS NOT NULL "
            "GROUP BY project, run HAVING MAX(ts) < ?)",
            (limit,),
        )[0]
        return {"runs": old[0], "events": old[1], "dry_run": True}
    runs, events = store.delete_runs_before(limit)
    return {"runs": runs, "events": events, "dry_run": False}


def apply_setting(store, cfg: dict) -> dict | None:
    """Apply `[storage] retention_days`, if set."""
    days = float((cfg.get("storage") or {}).get("retention_days") or 0)
    return prune(store, days) if days > 0 else None
