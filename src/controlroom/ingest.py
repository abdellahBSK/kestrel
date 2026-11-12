"""Getting events in: request parsing, the ingest token, and storing a batch.

Over HTTP, `POST /v1/events` needs `Authorization: Bearer <token>`. The token lives in
<home>/ingest.token (created on first use, readable only by you) and `controlroom token` prints it.
A custom header means browsers must ask permission first (CORS preflight), which this server never
grants, so a web page you visit cannot post fake events into your dashboard.
"""

from __future__ import annotations

import hmac
import json
import os
import secrets
import time
from pathlib import Path

from controlroom import paths
from controlroom.events import EventError, normalize
from controlroom.store import Store

MAX_BODY = 5_000_000  # bytes per request
MAX_EVENTS = 5_000  # events per request
TOKEN_FILE = "ingest.token"


def token_path(home: Path | None = None) -> Path:
    return (home or paths.HOME) / TOKEN_FILE


def token(home: Path | None = None) -> str:
    """The ingest token, created on first use."""
    f = token_path(home)
    try:
        value = f.read_text(encoding="utf-8").strip()
        if value:
            return value
    except FileNotFoundError:
        pass
    f.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_urlsafe(32)
    f.write_text(value + "\n", encoding="utf-8")
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass
    return value


def authorized(header: str | None, home: Path | None = None) -> bool:
    if not header or not header.startswith("Bearer "):
        return False
    return hmac.compare_digest(header[7:].strip().encode(), token(home).encode())


def parse_body(body: bytes, content_type: str = "application/json") -> list:
    """An event, a JSON array of events, {"events": [...]}, or NDJSON (one event per line)."""
    text = body.decode("utf-8")
    if "ndjson" in content_type or "jsonl" in content_type:
        items = []
        for n, line in enumerate(text.splitlines(), 1):
            if line.strip():
                try:
                    items.append(json.loads(line))
                except ValueError as e:
                    raise EventError(f"line {n} is not JSON: {e}") from None
        return items
    try:
        payload = json.loads(text)
    except ValueError as e:
        raise EventError(f"body is not JSON: {e}") from None
    if isinstance(payload, dict) and isinstance(payload.get("events"), list):
        return payload["events"]
    return payload if isinstance(payload, list) else [payload]


def ingest(store: Store, raw_events: list, now: float | None = None) -> dict:
    """Validate and store a batch. Valid events are kept even if others in the batch are rejected."""
    if len(raw_events) > MAX_EVENTS:
        raise EventError(f"at most {MAX_EVENTS} events per request")
    now = time.time() if now is None else now
    good, rejected = [], []
    for i, raw in enumerate(raw_events):
        try:
            good.append(normalize(raw, now))
        except EventError as e:
            rejected.append({"index": i, "error": str(e)})
    accepted, duplicates = store.add(good) if good else (0, 0)
    return {"accepted": accepted, "duplicates": duplicates, "rejected": rejected}
