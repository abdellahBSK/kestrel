"""Report your agents into the dashboard from Python.

    from kestrel.client import Reporter

    with Reporter("my-project").run("Fix the login bug") as run:     # heartbeats while open
        lead = run.agent("lead", role="lead", model="claude-opus-5-5")
        dev = run.agent("dev-1", role="developer", parent="lead", description="Implement the fix")
        dev.action("Bash", detail="npm test", summary="Ran the tests", result="42 passed")
        dev.tokens(input=1200, output=300, model="claude-sonnet-5-5")
        dev.finish()
        lead.finish()
    # leaving the block finishes the run ("failed" if an exception escaped)

By default events go straight into this computer's store (<home>/data/events.db), no server
needed. Pass url="http://127.0.0.1:7777" to send them to a running dashboard over HTTP instead.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
import uuid
from pathlib import Path

from kestrel.api import ingest
from kestrel.core.events import normalize


class Reporter:
    def __init__(
        self,
        project: str,
        *,
        url: str | None = None,
        token: str | None = None,
        home: Path | None = None,
        store=None,
    ):
        self.project = project
        self.url = url.rstrip("/") if url else None
        self._token = token
        self._home = home
        self._store = store

    # ── transport ──

    def send(self, events: list[dict]) -> dict:
        """Send raw events (see docs/events.md). Invalid ones raise EventError before anything is sent."""
        now = time.time()
        clean = [normalize({"project": self.project, **e}, now) for e in events]
        if not self.url:
            from kestrel.storage.store import open_store

            store = self._store or open_store(self._home / "data" / "events.db" if self._home else None)
            accepted, duplicates = store.add(clean)
            return {"accepted": accepted, "duplicates": duplicates, "rejected": []}
        req = urllib.request.Request(
            f"{self.url}/v1/events",
            data=json.dumps({"events": clean}).encode(),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._token or ingest.token(self._home)}",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())

    def emit(self, type: str, *, run: str | None = None, agent: str | None = None, ts=None, id=None, **data) -> dict:
        e = {"type": type, "run": run, "agent": agent, "data": {k: v for k, v in data.items() if v is not None}}
        if ts is not None:
            e["ts"] = ts
        if id is not None:
            e["id"] = id
        return self.send([e])

    def run(
        self,
        title: str | None = None,
        *,
        run_id: str | None = None,
        budget: int | None = None,
        source: str = "python",
        ts=None,
    ) -> Run:
        """Start a run. Use it as a context manager to send heartbeats and finish it automatically.
        `source` names what produced the run (your framework or tool)."""
        r = Run(self, run_id or time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6])
        self.emit("run.started", run=r.id, ts=ts, title=title, budget=budget, source=source)
        return r


class Run:
    HEARTBEAT_EVERY = 10.0

    def __init__(self, reporter: Reporter, run_id: str):
        self.reporter, self.id = reporter, run_id
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def emit(self, type: str, *, agent: str | None = None, ts=None, **data) -> dict:
        return self.reporter.emit(type, run=self.id, agent=agent, ts=ts, **data)

    def agent(
        self,
        agent_id: str,
        *,
        role: str = "agent",
        description: str | None = None,
        parent: str | None = None,
        model: str | None = None,
        ts=None,
    ) -> Agent:
        self.emit(
            "agent.started", agent=agent_id, ts=ts, role=role, description=description, parent=parent, model=model
        )
        return Agent(self, agent_id)

    def heartbeat(self, ts=None) -> None:
        self.emit("run.heartbeat", ts=ts)

    def finish(self, status: str = "ok", *, summary: str | None = None, error: str | None = None, ts=None) -> None:
        self._stop.set()
        self.emit("run.finished", ts=ts, status=status, summary=summary, error=error)

    def _beat(self) -> None:
        while not self._stop.wait(self.HEARTBEAT_EVERY):
            try:
                self.heartbeat()
            except Exception:
                pass  # the dashboard may be restarting; the next beat retries

    def __enter__(self) -> Run:
        self._thread = threading.Thread(target=self._beat, name="kestrel-heartbeat", daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if not self._stop.is_set():
            self.finish("failed" if exc_type else "ok", error=f"{exc_type.__name__}: {exc}" if exc_type else None)
        self._stop.set()


class Agent:
    def __init__(self, run: Run, agent_id: str):
        self.run, self.id = run, agent_id

    def _emit(self, type: str, ts=None, **data) -> dict:
        return self.run.emit(type, agent=self.id, ts=ts, **data)

    def message(self, text: str, *, ts=None) -> None:
        self._emit("agent.message", ts=ts, text=text)

    def action(
        self,
        tool: str | None = None,
        *,
        summary: str | None = None,
        detail: str | None = None,
        status: str = "ok",
        result: str | None = None,
        call: str | None = None,
        ts=None,
    ) -> None:
        """One tool call. To report a slow one twice, send status="running" with a call id, then the
        same call id with its final status and result."""
        self._emit(
            "agent.action", ts=ts, tool=tool, summary=summary, detail=detail, status=status, result=result, call=call
        )

    def tokens(
        self,
        *,
        input: int = 0,
        output: int = 0,
        cache_read: int = 0,
        cache_write: int = 0,
        model: str | None = None,
        cost_usd: float | None = None,
        ts=None,
    ) -> None:
        self._emit(
            "agent.tokens",
            ts=ts,
            input=input,
            output=output,
            cache_read=cache_read,
            cache_write=cache_write,
            model=model,
            cost_usd=cost_usd,
        )

    def notice(self, text: str, *, level: str = "info", ts=None) -> None:
        self._emit("agent.notice", ts=ts, text=text, level=level)

    def heartbeat(self, ts=None) -> None:
        self._emit("agent.heartbeat", ts=ts)

    def finish(self, status: str = "ok", *, summary: str | None = None, error: str | None = None, ts=None) -> None:
        self._emit("agent.finished", ts=ts, status=status, summary=summary, error=error)
