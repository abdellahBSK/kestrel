"""Liveness and health: what the dashboard may honestly claim about a run and its agents.

Nothing here trusts an agent's last word about itself. A run is live only while its runner keeps
writing a heartbeat (or its agent process is demonstrably still alive); an agent is "working" only
while it keeps producing activity inside a live run. Everything else decays to idle, stale or lost.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import threading
import time
from pathlib import Path

HEARTBEAT_EVERY = 10  # seconds between runner heartbeats

DEFAULTS = {
    "heartbeat_timeout": 45,  # a run whose heartbeat is older than this is lost
    "idle_after": 120,  # an agent quiet for this long is idle
    "stale_after": 600,  # ...and after this long, stale (maybe stuck)
}

# Agent and project states, from best to worst.
AGENT_STATES = ("working", "waiting", "idle", "finished", "stale", "lost", "failed")
FAILED_STATUSES = ("error", "usage-limit", "not-logged-in")


def thresholds(cfg: dict) -> dict:
    """[monitor] overrides from the config, in seconds."""
    mon = cfg.get("monitor", {}) or {}
    return {k: float(mon.get(k, v)) for k, v in DEFAULTS.items()}


# ───────────────────────────── processes ─────────────────────────────


def pid_alive(pid: int | None) -> bool:
    """True if a process with this PID is running. Never signals the process.

    (On Windows `os.kill(pid, 0)` would terminate it, so we ask the kernel instead.)
    """
    if not pid or pid <= 0:
        return False
    if sys.platform == "win32":
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.OpenProcess.restype = ctypes.c_void_p
        k32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        k32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        k32.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = k32.OpenProcess(0x1000, 0, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return ctypes.get_last_error() == 5  # access denied: it exists, it just isn't ours
        try:
            code = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            k32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


# ───────────────────────────── run heartbeat ─────────────────────────────


def read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def write_json_atomic(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


class Heartbeat:
    """Keeps `current.json` fresh while a run is alive; removes it when the run ends.

    with Heartbeat(state_dir / "current.json", {"team": ..., "session": ...}) as hb:
        proc = subprocess.Popen(...)
        hb.update(child_pid=proc.pid)
        ...
    """

    def __init__(self, path: Path, info: dict, every: float = HEARTBEAT_EVERY):
        self.path, self.every = path, every
        self.info = {**info, "pid": os.getpid()}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="heartbeat", daemon=True)

    def beat(self) -> None:
        self.info["heartbeat"] = time.time()
        try:
            write_json_atomic(self.path, self.info)
        except OSError:
            pass  # a reader had the file open (Windows): the next beat retries

    def update(self, **fields) -> None:
        self.info.update(fields)
        self.beat()

    def _loop(self) -> None:
        while not self._stop.wait(self.every):
            self.beat()

    def __enter__(self) -> Heartbeat:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.beat()
        self._thread.start()
        return self

    def __exit__(self, *exc) -> None:
        self._stop.set()
        self._thread.join(timeout=5)
        self.path.unlink(missing_ok=True)
        self.path.with_name(self.path.name + ".tmp").unlink(missing_ok=True)


def run_state(state_dir: Path, timeout: float, now: float | None = None) -> dict | None:
    """The run recorded in state/current.json, with `state` = "running" or "lost". None when idle.

    Running means: the runner's heartbeat is fresh, or the agent process it started is still alive
    (the runner itself may have died while the agents carry on). Anything else is a lost run.
    """
    now = time.time() if now is None else now
    f = state_dir / "current.json"
    cur = read_json(f)
    if not cur:
        return None
    if "heartbeat" in cur:
        last = float(cur["heartbeat"])
        alive = (now - last <= timeout and pid_alive(cur.get("pid"))) or pid_alive(cur.get("child_pid"))
    else:  # written by a runner from before heartbeats: all we have is the PID in run.lock
        try:
            last = f.stat().st_mtime
            lock_pid = int((state_dir / "run.lock").read_text().strip() or 0)
        except (OSError, ValueError):
            lock_pid = 0
        alive = pid_alive(lock_pid)
    return {**cur, "state": "running" if alive else "lost", "last_heartbeat": last}


# ───────────────────────────── agents and projects ─────────────────────────────


def agent_state(
    *,
    finished: bool,
    live: bool,
    last_activity: float | None,
    now: float,
    th: dict,
    ended_cleanly: bool = False,
    waiting: bool = False,
    failed: bool = False,
) -> str:
    """One agent's state. `live` = its run is still running (see run_state)."""
    if failed:
        return "failed"
    if finished:
        return "finished"
    if not live:
        # The run is over but this agent never reported back: it was cut off mid-task.
        return "finished" if ended_cleanly else "lost"
    if waiting:
        return "waiting"
    age = now - last_activity if last_activity else 0.0
    if age >= th["stale_after"]:
        return "stale"
    if age >= th["idle_after"]:
        return "idle"
    return "working"


def team_health(run: str | None, has_runs: bool, agent_states: list[str]) -> str:
    """The project's state for its status dot: the worst thing that is true right now.

    running · stale (live run with a stuck agent) · lost (runner died mid-run) ·
    failed / incomplete (last run failed, or left an agent cut off) · idle · never
    """
    if run == "lost":
        return "lost"
    if run == "running":
        return "stale" if "stale" in agent_states else "running"
    if not has_runs:
        return "never"
    if "failed" in agent_states:
        return "failed"
    if "lost" in agent_states:
        return "incomplete"
    return "idle"


def run_results(state_dir: Path) -> dict[str, str]:
    """session id → final status, from the runner's state/run-<date>.json files."""
    out: dict[str, str] = {}
    for f in sorted(state_dir.glob("run-*.json")):
        try:
            rows = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in rows if isinstance(rows, list) else []:
            if isinstance(r, dict) and r.get("session"):
                out[r["session"]] = str(r.get("status", ""))
    return out


def is_failure(status: str | None) -> bool:
    return bool(status) and (status in FAILED_STATUSES or status.startswith("failed"))


def iso(epoch: float) -> str:
    """Epoch seconds → ISO 8601 in UTC ("…Z"). The browser formats it for the viewer."""
    import datetime as dt

    return dt.datetime.fromtimestamp(epoch, dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json_list(path: Path) -> list[dict]:
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
