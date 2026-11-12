"""The runner's OS-specific helpers degrade quietly where the desktop offers nothing."""

from __future__ import annotations

import sys
import time

from kestrel.runner import system


def test_background_processes_detach_on_every_os():
    kw = system.background_kwargs()
    assert ("creationflags" in kw) if sys.platform == "win32" else kw == {"start_new_session": True}


def test_a_browser_can_be_named_explicitly(monkeypatch):
    monkeypatch.setenv("KESTREL_BROWSER", "/opt/my-chromium")
    assert system.headless_browser() == "/opt/my-chromium"


def test_no_browser_is_none(monkeypatch):
    monkeypatch.delenv("KESTREL_BROWSER", raising=False)
    monkeypatch.setattr(system, "BROWSERS", {})
    monkeypatch.setattr(system.shutil, "which", lambda name: None)
    assert system.headless_browser() is None


def test_notifications_are_optional(monkeypatch):
    monkeypatch.setattr(system, "WINDOWS", False)
    monkeypatch.setattr(system, "MACOS", False)
    monkeypatch.setattr(system.shutil, "which", lambda name: None)
    assert system.notify("title", "body") is False


def test_without_a_desktop_the_app_runs_in_the_background(tmp_path, monkeypatch):
    monkeypatch.setattr(system, "WINDOWS", False)
    monkeypatch.setattr(system, "MACOS", False)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    if sys.platform == "win32":  # start_new_session is POSIX-only; use the Windows flags here
        monkeypatch.setattr(system, "background_kwargs", lambda window=False: {})
    log = tmp_path / "logs" / "app.log"
    assert system.open_terminal("echo started", tmp_path, "demo", log) == str(log)
    deadline = time.time() + 20
    while time.time() < deadline and "started" not in (log.read_text() if log.exists() else ""):
        time.sleep(0.2)
    assert "started" in log.read_text()
