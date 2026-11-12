"""`kestrel init` and `kestrel doctor` (spec 007)."""

from __future__ import annotations

import json
import types

import pytest

from kestrel import meter, paths
from kestrel.cli import hook as hook_cli
from kestrel.cli import setup
from kestrel.core import status


@pytest.fixture
def new_home(tmp_path, monkeypatch):
    home = tmp_path / "kestrel-home"
    monkeypatch.setattr(paths, "HOME", home)
    monkeypatch.setattr(paths, "CONFIG", home / "config.toml")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-config"))  # never the real ~/.claude
    monkeypatch.chdir(tmp_path)
    return home


def test_init_writes_a_config_that_changes_nothing(new_home):
    config, backup = setup.init()
    assert config.exists() and backup is None
    cfg = meter.load_config()
    defaults = meter.CONFIG_DEFAULTS
    assert cfg["budget"] == defaults["budget"]
    assert cfg["models"] == defaults["models"]
    assert cfg["model_weights"] == defaults["model_weights"]
    assert cfg["teams"] == {} and cfg["schedule"] == {} and cfg["projects"] == {}
    assert {k: float(v) for k, v in cfg["monitor"].items()} == {k: float(v) for k, v in status.DEFAULTS.items()}
    assert cfg["pipeline"] == {"enforce_order": True, "hide_ai_attribution": False}


def test_init_never_overwrites_without_force(new_home):
    setup.init()
    paths.CONFIG.write_text("# mine\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        setup.init()
    assert paths.CONFIG.read_text(encoding="utf-8") == "# mine\n"
    _, backup = setup.init(force=True)
    assert backup.read_text(encoding="utf-8") == "# mine\n"
    assert "[monitor]" in paths.CONFIG.read_text(encoding="utf-8")


def test_init_command_explains_what_next(new_home, capsys):
    assert setup.cmd_init(types.SimpleNamespace(force=False)) == 0
    out = capsys.readouterr().out
    assert "kestrel watch" in out and "kestrel hook install" in out
    assert (new_home / "ingest.token").exists()
    assert setup.cmd_init(types.SimpleNamespace(force=False)) == 1  # already there


def levels(findings) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for f in findings:
        out.setdefault(f.level, []).append(f.text)
    return out


def test_doctor_names_the_line_of_a_broken_config(new_home, capsys):
    new_home.mkdir()
    paths.CONFIG.write_text("[monitor]\nidle_after = = 3\n", encoding="utf-8")
    found = levels(setup.doctor())
    assert any("not valid TOML" in t and "line 2" in t for t in found["fail"])
    assert setup.cmd_doctor(types.SimpleNamespace()) == 1


def test_doctor_flags_bad_values_and_unknown_sections(new_home):
    new_home.mkdir()
    paths.CONFIG.write_text("[monitor]\nidle_after = -5\n[moniter]\nx = 1\n", encoding="utf-8")
    found = levels(setup.doctor())
    assert any("idle_after" in t for t in found["fail"])
    assert any("moniter" in t for t in found["warn"])


def test_doctor_on_a_fresh_machine_has_no_failures_but_the_build(new_home, monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "STATIC", tmp_path / "no-static")
    found = levels(setup.doctor())
    assert found["fail"] == [f"Dashboard web app is not built ({tmp_path / 'no-static'} is empty)"]
    assert any("Claude Code hooks are not installed" in t for t in found["info"])


def test_doctor_warns_when_hooks_report_to_another_home(new_home, tmp_path, monkeypatch):
    other = tmp_path / "other-home"
    monkeypatch.setattr(paths, "HOME", other)
    hook_cli.install("user")
    monkeypatch.setattr(paths, "HOME", new_home)
    found = levels(setup.doctor())
    assert any("another home folder" in t for t in found["warn"])


def test_doctor_checks_the_runner_only_when_teams_exist(new_home, monkeypatch):
    new_home.mkdir()
    paths.CONFIG.write_text('[teams.app]\ntitle = "App"\n', encoding="utf-8")
    monkeypatch.setattr(setup.shutil, "which", lambda name: None)
    found = levels(setup.doctor())
    assert any("`claude` not found" in t for t in found["fail"])
    assert any("agents_daily" in t for t in found["fail"])
    paths.CONFIG.write_text("", encoding="utf-8")
    assert not any("Runner" in f.text for f in setup.doctor())


def test_the_template_ships_with_the_package():
    assert setup.TEMPLATE.exists()
    assert json.dumps(str(setup.TEMPLATE))  # a real path inside the package
    assert setup.TEMPLATE.is_relative_to(paths.PKG)
