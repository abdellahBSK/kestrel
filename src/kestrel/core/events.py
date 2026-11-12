"""The event format, version 1: how any agent or orchestrator reports into the dashboard.

docs/events.md is the specification. This module turns an incoming event into its normalized form,
rejects malformed ones with a clear message, and scrubs secrets from every string before anything
is stored or shown.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import time
import uuid

VERSION = 1

RUN_TYPES = {"run.started", "run.heartbeat", "run.finished"}
AGENT_TYPES = {
    "agent.started",
    "agent.message",
    "agent.action",
    "agent.tokens",
    "agent.notice",
    "agent.heartbeat",
    "agent.finished",
}
PR_TYPES = {"pr.opened", "pr.closed"}
TYPES = RUN_TYPES | AGENT_TYPES | PR_TYPES
HEARTBEATS = {"run.heartbeat", "agent.heartbeat"}

ACTION_STATUSES = ("running", "ok", "error", "blocked")
FINISH_STATUSES = ("ok", "failed", "stopped", "interrupted")
NOTICE_LEVELS = ("info", "warning", "critical")

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@/+-]{0,127}$")
MAX_TEXT = 8000  # characters kept per string field
MAX_DATA_BYTES = 64_000
FUTURE_SKEW = 300  # seconds a timestamp may be ahead of this computer's clock
REDACTED = "[redacted]"


class EventError(ValueError):
    """The event is malformed; the message says what to fix."""


# ───────────────────────────── secret scrubbing ─────────────────────────────

_TOKENS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bsk-(?:proj-|live-|test-)?[A-Za-z0-9_-]{20,}"),
    re.compile(r"\b(?:rk|pk)_(?:live|test)_[A-Za-z0-9]{16,}"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{35}"),
    re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}"),
    re.compile(r"\bnpm_[A-Za-z0-9]{36}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWT
    re.compile(r"(?<=://)[^/\s:@]+:[^/\s@]+(?=@)"),  # user:password@ in URLs
]
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{12,}")
# key = value / key: value, where the key names a secret and the value has a letter in it
# (so "tokens: 400000" is left alone).
_ASSIGNMENT = re.compile(
    r"(?i)(?<![A-Za-z0-9])((?:api[_-]?key|secret|token|passw(?:or)?d|passwd|pwd|private[_-]?key|"
    r"client[_-]?secret|access[_-]?key|auth[_-]?token|credentials?)[\w-]*)"
    r"(\s*[:=]\s*)(['\"]?)((?=[^\s'\"]*[A-Za-z])[^\s'\",;]{8,})"
)


def scrub(text: str) -> str:
    """Replace anything that looks like a credential with [redacted]."""
    if not text:
        return text
    for pattern in _TOKENS:
        text = pattern.sub(REDACTED, text)
    text = _BEARER.sub(lambda m: f"{m.group(1)} {REDACTED}", text)
    return _ASSIGNMENT.sub(lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{REDACTED}", text)


def _clean(value):
    """Scrub and truncate every string in a JSON value."""
    if isinstance(value, str):
        value = scrub(value)
        return value if len(value) <= MAX_TEXT else value[: MAX_TEXT - 1] + "…"
    if isinstance(value, dict):
        return {str(k)[:64]: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value[:200]]
    return value


# ───────────────────────────── field helpers ─────────────────────────────


def _str(d: dict, key: str, *, required: bool = False, limit: int = MAX_TEXT) -> str | None:
    v = d.get(key)
    if v is None or v == "":
        if required:
            raise EventError(f"data.{key} is required")
        return None
    if not isinstance(v, str):
        raise EventError(f"data.{key} must be a string")
    return v[:limit]


def _choice(d: dict, key: str, choices: tuple, default: str) -> str:
    v = d.get(key, default)
    if v not in choices:
        raise EventError(f"data.{key} must be one of {', '.join(choices)} (got {v!r})")
    return v


def _count(d: dict, key: str) -> int:
    v = d.get(key, 0)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0 or v != v:
        raise EventError(f"data.{key} must be a number of tokens (0 or more)")
    return int(v)


def _ident(raw: dict, key: str, required: bool) -> str | None:
    v = raw.get(key)
    if v is None or v == "":
        if required:
            raise EventError(f"{key} is required for this event type")
        return None
    if not isinstance(v, str) or not ID_RE.match(v):
        raise EventError(
            f"{key} must be 1-128 characters: letters, digits and . _ : @ / + - (starting with a letter or digit)"
        )
    return v


def parse_ts(value, now: float) -> float:
    """ISO 8601 with a timezone ("2026-11-12T08:49:43Z") or Unix seconds → Unix seconds (UTC)."""
    if value is None:
        return now
    if isinstance(value, bool):
        raise EventError("ts must be an ISO 8601 string or Unix seconds")
    if isinstance(value, (int, float)):
        ts = float(value)
    elif isinstance(value, str):
        try:
            parsed = dt.datetime.fromisoformat(value.strip().replace("z", "Z"))
        except ValueError:
            raise EventError(f"ts {value!r} is not ISO 8601") from None
        if parsed.tzinfo is None:
            raise EventError("ts must include a timezone, e.g. 2026-11-12T08:49:43Z (use UTC)")
        ts = parsed.timestamp()
    else:
        raise EventError("ts must be an ISO 8601 string or Unix seconds")
    if ts < 946_684_800:  # 2000-01-01
        raise EventError("ts is before the year 2000: send seconds, not milliseconds, and in UTC")
    return now if ts > now + FUTURE_SKEW else ts  # a reporter whose clock runs far ahead


# ───────────────────────────── per-type data ─────────────────────────────


def _data(typ: str, d: dict) -> dict:
    out = dict(d)  # unknown fields are kept (forward compatible), and scrubbed like the rest
    if typ == "run.started":
        out.update(title=_str(d, "title", limit=300), source=_str(d, "source", limit=64))
        if "budget" in d:
            out["budget"] = _count(d, "budget")
        if "heartbeat_timeout" in d:  # seconds of silence before this run counts as lost
            hb = d["heartbeat_timeout"]
            if isinstance(hb, bool) or not isinstance(hb, (int, float)) or not 5 <= hb <= 86_400:
                raise EventError("data.heartbeat_timeout must be a number of seconds from 5 to 86400")
            out["heartbeat_timeout"] = int(hb)
    elif typ in ("run.finished", "agent.finished"):
        out.update(
            status=_choice(d, "status", FINISH_STATUSES, "ok"),
            summary=_str(d, "summary"),
            error=_str(d, "error"),
        )
    elif typ == "agent.started":
        role = _str(d, "role", limit=64) or "agent"
        out.update(
            role=role.lower(),
            description=_str(d, "description", limit=300),
            parent=_str(d, "parent", limit=128),
            model=_str(d, "model", limit=128),
        )
    elif typ == "agent.message":
        out["text"] = _str(d, "text", required=True)
    elif typ == "agent.action":
        tool, call = _str(d, "tool", limit=64), _str(d, "call", limit=128)
        if not tool and not call:
            raise EventError("data.tool is required (or data.call, to update an earlier action)")
        out.update(
            tool=tool,
            call=call,
            summary=_str(d, "summary", limit=300),
            detail=_str(d, "detail"),
            result=_str(d, "result"),
            status=_choice(d, "status", ACTION_STATUSES, "ok"),
        )
    elif typ == "agent.tokens":
        out.update(
            input=_count(d, "input"),
            output=_count(d, "output"),
            cache_read=_count(d, "cache_read"),
            cache_write=_count(d, "cache_write"),
            model=_str(d, "model", limit=128),
        )
        if "interactive" in d:
            out["interactive"] = bool(d["interactive"])
        if "cost_usd" in d:
            cost = d["cost_usd"]
            if isinstance(cost, bool) or not isinstance(cost, (int, float)) or cost < 0:
                raise EventError("data.cost_usd must be a number (0 or more)")
            out["cost_usd"] = float(cost)
    elif typ == "agent.notice":
        out.update(level=_choice(d, "level", NOTICE_LEVELS, "info"), text=_str(d, "text", required=True))
    elif typ in PR_TYPES:
        n = d.get("number")
        if isinstance(n, bool) or not isinstance(n, int) or n <= 0:
            raise EventError("data.number must be the pull request number")
        out["number"] = n
        url = _str(d, "url", limit=500)
        if url and not re.match(r"^https?://", url):
            raise EventError("data.url must be an http(s) link")
        out.update(url=url, title=_str(d, "title", limit=300), branch=_str(d, "branch", limit=200))
        if typ == "pr.opened":
            out["draft"] = bool(d.get("draft", False))
        else:
            out["merged"] = bool(d.get("merged", False))
    return {k: v for k, v in out.items() if v is not None}


def normalize(raw, now: float | None = None) -> dict:
    """Validate one incoming event and return its stored form:
    {id, ts (Unix seconds, UTC), type, project, run, agent, data}."""
    now = time.time() if now is None else now
    if not isinstance(raw, dict):
        raise EventError("an event must be a JSON object")
    v = raw.get("v", VERSION)
    if v != VERSION:
        raise EventError(f"unsupported event version {v!r}: this server speaks v{VERSION}")
    typ = raw.get("type")
    if typ not in TYPES:
        raise EventError(f"unknown event type {typ!r}; see docs/events.md for the list")
    data = raw.get("data", {})
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise EventError("data must be a JSON object")
    if len(json.dumps(data, default=str)) > MAX_DATA_BYTES:
        raise EventError(f"data is larger than {MAX_DATA_BYTES // 1000} kB")
    eid = raw.get("id")
    if eid is None:
        eid = uuid.uuid4().hex
    elif not isinstance(eid, str) or not 0 < len(eid) <= 200:
        raise EventError("id must be a string of up to 200 characters")
    return {
        "id": eid,
        "ts": parse_ts(raw.get("ts"), now),
        "type": typ,
        "project": _ident(raw, "project", True),
        "run": _ident(raw, "run", typ not in PR_TYPES),
        "agent": _ident(raw, "agent", typ in AGENT_TYPES),
        "data": _clean(_data(typ, data)),
    }
