"""Stops and budget caps (spec 008): should this agent stop, and why?

Every source asks the same question before an agent acts: the Claude Code hook and the Claude
Agent SDK adapter (before each tool call), the runner's guard, the Python client (with each
heartbeat) and HTTP clients (`GET /v1/control`). The answer comes from two places:

- stop requests the owner made from the dashboard or `kestrel stop`, stored in the `controls`
  table. A request covers everything, a project, a run or one agent, and applies only to runs
  that existed when it was made, so a stopped project can start again later;
- budget caps: `[projects.<name>] daily_tokens` / `daily_usd`, and a run's own `budget` from its
  run.started event. Reaching one records a stop request (source "budget"), so the dashboard and
  alerts see it like any other.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass

from kestrel.core import cost

ALL = "*"


@dataclass(frozen=True)
class Stop:
    reason: str
    scope: str  # "run": the whole run must end · "agent": only this agent
    source: str  # "owner" | "budget"


def day_start(now: float) -> float:
    """Local midnight before `now` (budgets are per local day)."""
    local = dt.datetime.fromtimestamp(now).astimezone()
    return local.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()


def requested(store, project: str, run: str | None, agent: str | None = None) -> Stop | None:
    """The newest stop request that covers this run (and agent), if any."""
    started = store.run_start(project, run) if run else None
    for c in store.controls_for(project):
        if c["run"] and c["run"] != run:
            continue
        if c["agent"] and c["agent"] != agent:
            continue
        if started is None or started > c["ts"] + 1e-6:
            continue  # the run started after the request (or hasn't reported anything yet)
        return Stop(c["reason"], "agent" if c["agent"] else "run", c["source"])
    return None


def _counted(d: dict, cfg: dict) -> float:
    b = cfg.get("budget", {})
    return (
        d.get("input", 0) * b.get("weight_input", 1.0)
        + d.get("output", 0) * b.get("weight_output", 1.0)
        + d.get("cache_write", 0) * b.get("weight_cache_write", 1.0)
        + d.get("cache_read", 0) * b.get("weight_cache_read", 0.0)
    )


def over_budget(store, project: str, run: str | None, cfg: dict, now: float) -> tuple[str, str | None] | None:
    """(reason, run the cap is for or None for the project), when a cap is reached."""
    caps = (cfg.get("projects") or {}).get(project) or {}
    daily_tokens, daily_usd = caps.get("daily_tokens") or 0, caps.get("daily_usd") or 0
    if daily_tokens or daily_usd:
        rows = store.tokens_for(project, day_start(now))
        if daily_tokens:
            used = sum(_counted(d, cfg) for d in rows)
            if used >= daily_tokens:
                return f"{project} reached its daily budget of {int(daily_tokens):,} tokens", None
        if daily_usd:
            table = cost.price_table(cfg)
            spent = sum(cost.cost(d.get("model", ""), d, table) or 0.0 for d in rows)
            if spent >= daily_usd:
                return f"{project} reached its daily budget of ${daily_usd:,.2f} (est. ${spent:,.2f})", None
    if run:
        budget = store.run_started(project, run).get("budget") or 0
        if budget:
            used = sum(_counted(d, cfg) for d in store.tokens_for(project, 0, run=run))
            if used >= budget:
                return f"this run reached its budget of {int(budget):,} tokens", run
    return None


def check(store, project: str, run: str | None, agent: str | None, cfg: dict, now: float | None = None) -> Stop | None:
    """Should this agent stop? Records a budget stop the first time a cap is reached."""
    now = time.time() if now is None else now
    stop = requested(store, project, run, agent)
    if stop:
        return stop
    hit = over_budget(store, project, run, cfg, now)
    if hit is None:
        return None
    reason, cap_run = hit
    store.add_control(project, cap_run, None, reason=reason, source="budget", ts=now)
    return Stop(reason, "run", "budget")


def request(store, project: str = ALL, run: str | None = None, agent: str | None = None, reason: str = "") -> str:
    """Record a stop requested by the owner. Returns a sentence saying what will stop."""
    what = (
        f"agent {agent} of run {run}"
        if agent and run
        else f"run {run}"
        if run
        else "every running agent"
        if project == ALL
        else f"every running agent of {project}"
    )
    store.add_control(project, run, agent, reason=reason or "Stopped by the owner", source="owner")
    return f"Stop requested for {what}. Agents stop at their next action."
