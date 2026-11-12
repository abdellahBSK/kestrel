"""`kestrel hook`: connect Claude Code to Kestrel (spec 006).

kestrel hook install [--scope user|project|local]   every session reports to this computer's Kestrel
kestrel hook uninstall [--scope ...]                remove Kestrel's hooks, keep everything else
kestrel hook status                                 where the hooks are installed
kestrel hook claude-code                            what Claude Code runs (reads one event on stdin)
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

from kestrel import NAME, paths
from kestrel.adapters import claude_code_hooks as cch

MARK = " -m kestrel hook claude-code"  # how Kestrel recognizes its own hook entries
SCOPES = ("user", "project", "local")


def settings_path(scope: str, cwd: Path | None = None) -> Path:
    cwd = cwd or Path.cwd()
    if scope == "user":
        base = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
        return base / "settings.json"
    return cwd / ".claude" / ("settings.json" if scope == "project" else "settings.local.json")


def hook_command(python: str | None = None) -> str:
    py = (python or sys.executable).replace("\\", "/")
    return f'"{py}"{MARK} --home "{paths.HOME.as_posix()}"'


def _ours(entry: dict) -> bool:
    return any(MARK in str(h.get("command", "")) for h in entry.get("hooks", []) if isinstance(h, dict))


def _without_ours(hooks: dict) -> dict:
    out = {}
    for event, entries in hooks.items():
        kept = [e for e in entries if not (isinstance(e, dict) and _ours(e))] if isinstance(entries, list) else entries
        if kept:
            out[event] = kept
    return out


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(text) if text.strip() else {}
    except ValueError as e:
        raise SystemExit(f"{path} is not valid JSON ({e}); fix it first, nothing was changed.") from None
    if not isinstance(data, dict):
        raise SystemExit(f"{path} does not hold a JSON object; nothing was changed.")
    return data


def _write(path: Path, data: dict) -> Path | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    if path.exists():
        backup = path.with_name(f"{path.name}.kestrel-backup-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copyfile(path, backup)
    tmp = path.with_name(path.name + ".kestrel-tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)
    return backup


def install(scope: str = "user", cwd: Path | None = None, python: str | None = None) -> tuple[Path, Path | None]:
    path = settings_path(scope, cwd)
    data = _load(path)
    hooks = _without_ours(data.get("hooks") or {})
    cmd = {"type": "command", "command": hook_command(python), "timeout": 15}
    for event in cch.EVENTS:
        entry = {"hooks": [cmd]}
        if event in cch.TOOL_EVENTS:
            entry = {"matcher": "*", **entry}
        hooks.setdefault(event, []).append(entry)
    data["hooks"] = hooks
    return path, _write(path, data)


def uninstall(scope: str = "user", cwd: Path | None = None) -> tuple[Path, bool]:
    path = settings_path(scope, cwd)
    data = _load(path)
    hooks = data.get("hooks") or {}
    cleaned = _without_ours(hooks)
    if cleaned == hooks:
        return path, False
    if cleaned:
        data["hooks"] = cleaned
    else:
        data.pop("hooks", None)
    _write(path, data)
    return path, True


def installed(scope: str, cwd: Path | None = None) -> bool:
    try:
        hooks = _load(settings_path(scope, cwd)).get("hooks") or {}
    except SystemExit:
        return False
    return any(
        _ours(e) for entries in hooks.values() if isinstance(entries, list) for e in entries if isinstance(e, dict)
    )


# ───────────────────────────── command line ─────────────────────────────


def add_parsers(sub) -> None:
    hp = sub.add_parser("hook", help="report Claude Code sessions to Kestrel (install, uninstall, status)")
    hsub = hp.add_subparsers(dest="hook_cmd", required=True)
    for name, text in (("install", "add Kestrel's hooks to Claude Code"), ("uninstall", "remove them")):
        p = hsub.add_parser(name, help=text)
        p.add_argument(
            "--scope",
            choices=SCOPES,
            default="user",
            help="user: every session (default); project: this repository, committed; local: this repository, just you",
        )
    hsub.add_parser("status", help="where Kestrel's hooks are installed")
    hsub.add_parser("claude-code", help="(run by Claude Code) read one hook event from stdin")


def run(args) -> int:
    if args.hook_cmd == "claude-code":
        return cch.main()
    if args.hook_cmd == "install":
        path, backup = install(args.scope)
        print(f"Claude Code now reports to {NAME}: hooks added to {path}")
        if backup:
            print(f"(the previous file is saved as {backup.name})")
        print(
            "New sessions appear in `kestrel watch` as soon as you send a prompt. Restart running sessions to include them."
        )
        return 0
    if args.hook_cmd == "uninstall":
        path, changed = uninstall(args.scope)
        print(f"Removed {NAME}'s hooks from {path}" if changed else f"No {NAME} hooks in {path}")
        return 0
    for scope in SCOPES:
        path = settings_path(scope)
        print(f"{scope:<8} {'installed' if installed(scope) else '-':<10} {path}")
    errors = cch.state_dir() / "errors.log"
    if errors.exists():
        print(f"\nThe hook has logged errors: {errors}")
    return 0
