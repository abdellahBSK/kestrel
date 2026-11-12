"""`kestrel init` and `kestrel doctor` (spec 007): set up a home folder, and check a setup.

kestrel init [--force]   write a commented config into the home folder
kestrel doctor           check everything Kestrel depends on, and say how to fix what isn't right
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
import tomllib
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from kestrel import NAME, __version__, meter, paths

TEMPLATE = paths.PKG / "templates" / "config.toml"
KNOWN_SECTIONS = set(meter.CONFIG_DEFAULTS) | {"model_ids"}
PORT = 7777


# ───────────────────────────── init ─────────────────────────────


def init(force: bool = False) -> tuple[Path, Path | None]:
    """Write the config template into the home folder. Returns (config path, backup or None)."""
    paths.HOME.mkdir(parents=True, exist_ok=True)
    (paths.HOME / "data").mkdir(exist_ok=True)
    backup = None
    if paths.CONFIG.exists():
        if not force:
            raise FileExistsError(paths.CONFIG)
        backup = paths.CONFIG.with_name(f"config.toml.backup-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copyfile(paths.CONFIG, backup)
    shutil.copyfile(TEMPLATE, paths.CONFIG)
    return paths.CONFIG, backup


def cmd_init(args) -> int:
    try:
        config, backup = init(force=args.force)
    except FileExistsError:
        print(f"{paths.CONFIG} already exists; nothing was changed.")
        print("Use `kestrel init --force` to replace it (the current file is backed up first).")
        return 1
    from kestrel.api import ingest

    ingest.token()  # create it now, so `kestrel token` and HTTP reporters work right away
    print(f"{NAME} is set up in {paths.HOME}")
    print(f"  config  {config}" + (f"   (previous one saved as {backup.name})" if backup else ""))
    print("\nNext:")
    print("  kestrel watch           open the dashboard")
    print("  kestrel hook install    report every Claude Code session")
    print("  kestrel demo            see every state with fake data")
    print("  kestrel doctor          check the setup")
    return 0


# ───────────────────────────── doctor ─────────────────────────────


@dataclass
class Finding:
    level: str  # ok | info | warn | fail
    text: str
    fix: str = ""


def _config(findings: list[Finding]) -> dict | None:
    if not paths.CONFIG.exists():
        findings.append(Finding("info", "No config file: built-in defaults are used", "kestrel init  (optional)"))
        return {}
    try:
        with open(paths.CONFIG, "rb") as f:
            user = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        findings.append(
            Finding("fail", f"{paths.CONFIG} is not valid TOML: {e}", "fix that line, then run kestrel doctor again")
        )
        return None
    except OSError as e:
        findings.append(Finding("fail", f"Can't read {paths.CONFIG}: {e}", "check the file's permissions"))
        return None
    findings.append(Finding("ok", f"Config {paths.CONFIG}"))
    unknown = sorted(set(user) - KNOWN_SECTIONS)
    if unknown:
        findings.append(
            Finding(
                "warn",
                f"Unknown config section(s): {', '.join(unknown)} (ignored)",
                "check the spelling against kestrel init's template",
            )
        )
    for key, value in (user.get("monitor") or {}).items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            findings.append(
                Finding(
                    "fail", f"[monitor] {key} must be a number of seconds, got {value!r}", "set it to a positive number"
                )
            )
    return user


def _store(findings: list[Finding]) -> None:
    try:
        from kestrel.storage.store import open_store

        st = open_store()
        count = st.db.execute("SELECT count(*) FROM events").fetchone()[0]
        projects = len(st.projects())
        findings.append(Finding("ok", f"Event store: {count:,} events from {projects} project(s)"))
        if count == 0:
            findings.append(
                Finding(
                    "info",
                    "No events yet",
                    "kestrel hook install (Claude Code), or see docs/events.md to report from your agents",
                )
            )
    except Exception as e:
        findings.append(
            Finding(
                "fail",
                f"Can't open the event store in {paths.HOME / 'data'}: {e}",
                "check the folder's permissions and free disk space",
            )
        )


def _web_app(findings: list[Finding]) -> None:
    if (paths.STATIC / "index.html").exists():
        findings.append(Finding("ok", "Dashboard web app is built"))
    else:
        findings.append(
            Finding(
                "fail",
                f"Dashboard web app is not built ({paths.STATIC} is empty)",
                "cd frontend && npm ci && npm run build",
            )
        )


def _port(findings: list[Finding], port: int = PORT) -> None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/health", timeout=1) as r:
            health = json.loads(r.read())
        findings.append(
            Finding("ok", f"Dashboard running on http://127.0.0.1:{port} ({NAME} {health.get('version', '?')})")
        )
        if health.get("version") not in (None, __version__):
            findings.append(
                Finding(
                    "warn",
                    f"That dashboard runs version {health['version']}, this is {__version__}",
                    "restart it: close it, then kestrel watch",
                )
            )
        return
    except Exception:
        pass
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            findings.append(Finding("ok", f"Port {port} is free for the dashboard"))
        except OSError:
            findings.append(
                Finding("warn", f"Port {port} is used by another program", f"kestrel watch --port {port + 1}")
            )


def _hooks(findings: list[Finding]) -> None:
    from kestrel.adapters import claude_code_hooks as cch
    from kestrel.cli import hook as hook_cli

    found = False
    for scope in hook_cli.SCOPES:
        if not hook_cli.installed(scope):
            continue
        found = True
        path = hook_cli.settings_path(scope)
        data = json.loads(path.read_text(encoding="utf-8"))
        commands = {
            h.get("command", "")
            for entries in (data.get("hooks") or {}).values()
            for e in entries
            if isinstance(e, dict)
            for h in e.get("hooks", [])
            if hook_cli.MARK in str(h.get("command", ""))
        }
        for cmd in commands:
            py = cmd.split('"')[1] if cmd.startswith('"') else cmd.split()[0]
            home = cmd.split("--home", 1)[1].strip().strip('"') if "--home" in cmd else ""
            if not Path(py).exists():
                findings.append(
                    Finding(
                        "fail",
                        f"Claude Code hooks ({scope}) use a Python that no longer exists: {py}",
                        f"kestrel hook install --scope {scope}",
                    )
                )
            elif home and Path(home).resolve() != paths.HOME:
                findings.append(
                    Finding(
                        "warn",
                        f"Claude Code hooks ({scope}) report to another home folder: {home}",
                        f"to report here instead: kestrel hook install --scope {scope}",
                    )
                )
            else:
                findings.append(Finding("ok", f"Claude Code hooks installed ({scope}: {path})"))
    if not found:
        findings.append(
            Finding(
                "info",
                "Claude Code hooks are not installed",
                "kestrel hook install  (to see your Claude Code sessions)",
            )
        )
    errors = cch.state_dir() / "errors.log"
    if errors.exists() and errors.stat().st_size:
        last = errors.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-1]
        findings.append(
            Finding("warn", f"The Claude Code hook logged errors; last: {last}", f"see {errors}; delete it once fixed")
        )


def _runner(findings: list[Finding], cfg: dict) -> None:
    from kestrel.runner import orchestrator

    for tool, why in (
        ("claude", "runs the agents"),
        ("git", "manages the repositories"),
        ("gh", "opens pull requests"),
    ):
        if shutil.which(tool):
            findings.append(Finding("ok", f"Runner: `{tool}` found"))
        else:
            level = "warn" if tool == "gh" else "fail"
            findings.append(
                Finding(level, f"Runner: `{tool}` not found on PATH ({why})", f"install {tool} and open a new terminal")
            )
    if shutil.which("gh"):
        r = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
        if r.returncode != 0:
            findings.append(Finding("warn", "Runner: `gh` is not logged in", "gh auth login"))
    bad = orchestrator.parent_git_repo()
    if bad is not None:
        findings.append(
            Finding(
                "fail",
                f"Runner: the home folder is inside a git repository ({bad})",
                "move the home folder out of it (KESTREL_HOME), or the runner refuses to start",
            )
        )
    b = cfg["budget"]
    if not b.get("agents_daily") or not b.get("agents_weekly"):
        findings.append(
            Finding("fail", "Runner: [budget] agents_daily and agents_weekly must be set", "set both in config.toml")
        )
    if not any(cfg["schedule"].get(d) for d in orchestrator.DAYS):
        findings.append(
            Finding(
                "warn",
                "Runner: no team is scheduled on any day",
                "add teams to [schedule], or run one with kestrel run --team NAME",
            )
        )
    for team in cfg["teams"]:
        if not (orchestrator.TEAMS / team / "CLAUDE.md").exists():
            findings.append(Finding("warn", f"Runner: team {team} has no workspace yet", "kestrel setup"))


def doctor() -> list[Finding]:
    findings = [Finding("ok", f"{NAME} {__version__} on Python {sys.version.split()[0]} ({paths.PKG})")]
    if paths.HOME.exists():
        findings.append(Finding("ok", f"Home folder {paths.HOME}"))
    else:
        findings.append(
            Finding(
                "info",
                f"Home folder {paths.HOME} doesn't exist yet",
                "kestrel init  (or just start reporting: it is created on first use)",
            )
        )
    user = _config(findings)
    _store(findings)
    _web_app(findings)
    _port(findings)
    _hooks(findings)
    if user is not None and user.get("teams"):
        _runner(findings, meter.load_config())
    return findings


def _symbols() -> dict[str, str]:
    fancy = {"ok": "✓", "info": "·", "warn": "!", "fail": "✗", "fix": "→"}
    try:
        "".join(fancy.values()).encode(sys.stdout.encoding or "ascii")
        return fancy
    except (UnicodeEncodeError, LookupError):
        return {"ok": "ok", "info": "--", "warn": "!!", "fail": "XX", "fix": "->"}


def cmd_doctor(args) -> int:
    sym = _symbols()
    findings = doctor()
    for f in findings:
        print(f"{sym[f.level]:>2} {f.text}")
        if f.fix and f.level != "ok":
            print(f"   {sym['fix']} {f.fix}")
    fails = sum(f.level == "fail" for f in findings)
    warns = sum(f.level == "warn" for f in findings)
    print(f"\n{'All good.' if not fails and not warns else f'{fails} problem(s), {warns} warning(s).'}")
    return 1 if fails else 0


def add_parsers(sub) -> None:
    ip = sub.add_parser("init", help="write a commented config into the home folder")
    ip.add_argument("--force", action="store_true", help="replace an existing config (it is backed up first)")
    sub.add_parser("doctor", help="check the setup and say how to fix what isn't right")
