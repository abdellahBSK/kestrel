"""Everything the runner does differently on Windows, macOS and Linux, in one place.

Each function works everywhere and degrades quietly where the desktop offers nothing better: no
notification daemon means no notification, no terminal emulator means the app runs in the
background with its output in a log file.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"


def background_kwargs(window: bool = False) -> dict:
    """Popen arguments for a process that outlives the one starting it.
    `window`: on Windows, give it its own console window."""
    if WINDOWS:
        if window:
            return {"creationflags": subprocess.CREATE_NEW_CONSOLE}
        return {"creationflags": subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS}
    return {"start_new_session": True}


def notify(title: str, body: str, url: str = "", url2: str = "", runner_dir: Path | None = None) -> bool:
    """A desktop notification. Returns whether one could be shown."""
    try:
        if WINDOWS and runner_dir is not None:
            args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(runner_dir / "notify.ps1")]
            args += ["-Title", title, "-Body", body, "-Url", url] + (["-Url2", url2] if url2 else [])
            return subprocess.run(args, capture_output=True, timeout=30).returncode == 0
        if MACOS and shutil.which("osascript"):
            script = f"display notification {_applescript(body + (' ' + url if url else ''))} with title {_applescript(title)}"
            return subprocess.run(["osascript", "-e", script], capture_output=True, timeout=30).returncode == 0
        if shutil.which("notify-send"):
            text = body + (f"\n{url}" if url else "")
            return (
                subprocess.run(
                    ["notify-send", "--app-name=Kestrel", title, text], capture_output=True, timeout=30
                ).returncode
                == 0
            )
    except (OSError, subprocess.SubprocessError):
        pass
    return False


def _applescript(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


LINUX_TERMINALS = (
    ("x-terminal-emulator", ["-e"]),
    ("gnome-terminal", ["--"]),
    ("konsole", ["-e"]),
    ("xfce4-terminal", ["-x"]),
    ("kitty", []),
    ("alacritty", ["-e"]),
    ("xterm", ["-e"]),
)


def open_terminal(command: str, cwd: Path, title: str, log: Path) -> str:
    """Run a shell command in a new terminal window the user can close to stop it.
    Returns where it runs: "window" or the log file it writes to."""
    if WINDOWS:
        subprocess.Popen(
            ["cmd", "/k", f"title {title} & {command}"], cwd=cwd, close_fds=True, **background_kwargs(window=True)
        )
        return "window"
    if MACOS and shutil.which("osascript"):
        script = f'tell application "Terminal" to do script {_applescript(f"cd {_sh(str(cwd))} && {command}")}'
        if subprocess.run(["osascript", "-e", script], capture_output=True).returncode == 0:
            return "window"
    if os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"):
        for term, flag in LINUX_TERMINALS:
            if shutil.which(term):
                subprocess.Popen([term, *flag, "sh", "-c", f"{command}; exec $SHELL"], cwd=cwd, **background_kwargs())
                return "window"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "ab") as out:
        subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            stdout=out,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            **background_kwargs(),
        )
    return str(log)


def _sh(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


BROWSERS = {
    "win32": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ],
    "darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ],
}
BROWSER_COMMANDS = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "microsoft-edge",
    "msedge",
    "chrome",
)


def headless_browser() -> str | None:
    """A Chromium-based browser that can take headless screenshots, or None."""
    if os.environ.get("KESTREL_BROWSER"):
        return os.environ["KESTREL_BROWSER"]
    for candidate in BROWSERS.get(sys.platform, []):
        if Path(candidate).exists():
            return candidate
    for name in BROWSER_COMMANDS:
        found = shutil.which(name)
        if found:
            return found
    return None
