"""Token meter: reads Claude Code session logs (~/.claude/projects/**/*.jsonl).

Every API response in those logs carries a `usage` block. Sessions run by agent teams
live under project folders named after `<home>/teams/<team>`; everything else is
the owner's personal usage.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

from controlroom import paths

HQ = paths.HOME
PROJECTS = Path.home() / ".claude" / "projects"


CONFIG_DEFAULTS: dict = {
    "owner": {},
    # 0 = no cap. The dashboard hides meters for uncapped budgets; the runner needs real caps.
    "budget": {
        "agents_daily": 0,
        "agents_weekly": 0,
        "personal_week_high": 10**15,
        "warn_at": 0.8,
        "stop_at": 1.0,
        "min_team_run": 120_000,
        "weight_input": 1.0,
        "weight_output": 1.0,
        "weight_cache_write": 1.0,
        "weight_cache_read": 0.0,
    },
    "schedule": {},
    "models": {
        "lead": "opus",
        "lead_effort": "high",
        "lead_fallback": "sonnet",
        "developer": "sonnet",
        "security": "sonnet",
        "optimizer": "sonnet",
        "tester": "haiku",
        "qa": "haiku",
    },
    "model_ids": {},
    "model_weights": {"default": 1.0},
    "monitor": {},
    "pipeline": {},
    "teams": {},
    "projects": {},  # display names for projects that report events: [projects.<name>] title, key
}
MERGED = ("budget", "models", "monitor", "pipeline", "owner")  # sections whose keys fill in one by one


def load_config() -> dict:
    """The config, with defaults for anything missing. No config file at all is fine: the dashboard
    then shows whatever projects report events, with no budgets or schedule."""
    try:
        with open(paths.CONFIG, "rb") as f:
            user = tomllib.load(f)
    except FileNotFoundError:
        user = {}
    cfg = {k: dict(v) if isinstance(v, dict) else v for k, v in CONFIG_DEFAULTS.items()}
    for key, value in user.items():
        if key in MERGED and isinstance(value, dict):
            cfg[key] = {**cfg[key], **value}
        else:
            cfg[key] = value
    return cfg


def sanitize(path_or_name: str) -> str:
    """Claude Code names project folders by replacing non-alphanumerics with '-'."""
    return re.sub(r"[^A-Za-z0-9]", "-", path_or_name)


def teams_prefix() -> str:
    """Claude Code project-folder prefix shared by every team workspace (lowercase)."""
    return sanitize(str(HQ / "teams")).lower() + "-"


def owner_of(project_dir_name: str) -> str:
    low = project_dir_name.lower()
    prefix = teams_prefix()
    if not low.startswith(prefix):
        return "personal"
    return "team:" + low[len(prefix) :]


_CFG: dict | None = None


def model_factor(model: str) -> float:
    """Cost of a model's tokens relative to Opus (from [model_weights] in config.toml)."""
    global _CFG
    if _CFG is None:
        _CFG = load_config()
    weights = _CFG.get("model_weights", {})
    m = (model or "").lower()
    for family, w in weights.items():
        if family != "default" and family in m:
            return float(w)
    return float(weights.get("default", 1.0))


def weighted(c: Counter, cfg: dict) -> int:
    b = cfg["budget"]
    return int(
        c["input"] * b.get("weight_input", 1.0)
        + c["output"] * b.get("weight_output", 1.0)
        + c["cache_write"] * b.get("weight_cache_write", 1.0)
        + c["cache_read"] * b.get("weight_cache_read", 0.0)
    )


def _local(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()


def scan(since: dt.datetime, only_dirs: list[Path] | None = None) -> dict[str, dict[str, Counter]]:
    """Return {owner: {YYYY-MM-DD: Counter}} for usage at or after `since` (aware datetime)."""
    out: dict[str, dict[str, Counter]] = defaultdict(lambda: defaultdict(Counter))
    if not PROJECTS.exists():
        return out
    dirs = only_dirs if only_dirs is not None else [d for d in PROJECTS.iterdir() if d.is_dir()]
    since_epoch = since.timestamp()
    seen: set = set()
    for d in dirs:
        if not d.exists():
            continue
        owner = owner_of(d.name)
        for f in d.rglob("*.jsonl"):
            try:
                if f.stat().st_mtime < since_epoch:
                    continue
                with open(f, encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        if '"usage"' not in line:
                            continue
                        try:
                            rec = json.loads(line)
                        except ValueError:
                            continue
                        msg = rec.get("message")
                        if not isinstance(msg, dict) or not msg.get("usage") or not rec.get("timestamp"):
                            continue
                        key = (msg.get("id"), rec.get("requestId"))
                        if key in seen:
                            continue
                        seen.add(key)
                        when = _local(rec["timestamp"])
                        if when < since:
                            continue
                        u = msg["usage"]
                        f = model_factor(msg.get("model", ""))  # Opus-equivalent tokens
                        c = out[owner][when.date().isoformat()]
                        c["input"] += (u.get("input_tokens") or 0) * f
                        c["output"] += (u.get("output_tokens") or 0) * f
                        c["cache_write"] += (u.get("cache_creation_input_tokens") or 0) * f
                        c["cache_read"] += (u.get("cache_read_input_tokens") or 0) * f
                        c["calls"] += 1
            except OSError:
                continue
    return out


def team_dirs(team: str) -> list[Path]:
    name = teams_prefix() + sanitize(team).lower()
    if not PROJECTS.exists():
        return []
    return [d for d in PROJECTS.iterdir() if d.is_dir() and d.name.lower() == name]


def team_used_since(team: str, since: dt.datetime, cfg: dict) -> int:
    data = scan(since, team_dirs(team))
    total = Counter()
    for days in data.values():
        for c in days.values():
            total.update(c)
    return weighted(total, cfg)


def start_of_today() -> dt.datetime:
    now = dt.datetime.now().astimezone()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def summary(cfg: dict, days: int = 7) -> dict:
    """Totals for today and the last `days` days: personal, per team, all agents."""
    today0 = start_of_today()
    since = today0 - dt.timedelta(days=days - 1)
    data = scan(since)
    today = today0.date().isoformat()
    res: dict = {"today": {}, "week": {}}
    dates = [(today0 - dt.timedelta(days=i)).date().isoformat() for i in range(days - 1, -1, -1)]
    daily = {d: {"date": d, "agents": 0, "personal": 0} for d in dates}
    for owner, per_day in data.items():
        wk = Counter()
        for c in per_day.values():
            wk.update(c)
        res["week"][owner] = weighted(wk, cfg)
        res["today"][owner] = weighted(per_day.get(today, Counter()), cfg)
        for d, c in per_day.items():
            if d in daily:
                daily[d]["agents" if owner.startswith("team:") else "personal"] += weighted(c, cfg)
    for span in ("today", "week"):
        res[span]["agents"] = sum(v for k, v in res[span].items() if k.startswith("team:"))
        res[span].setdefault("personal", 0)
    res["daily"] = list(daily.values())
    return res


def baseline(cfg: dict) -> dict:
    """Personal usage stats over all history (active days only)."""
    data = scan(dt.datetime(2000, 1, 1).astimezone())
    per_day = data.get("personal", {})
    vals = sorted(weighted(c, cfg) for c in per_day.values())
    if not vals:
        return {"days": 0}
    n = len(vals)
    return {
        "days": n,
        "median": vals[n // 2],
        "p80": vals[int(n * 0.8)],
        "max": vals[-1],
        "avg": sum(vals) // n,
    }
