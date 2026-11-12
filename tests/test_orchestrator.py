from __future__ import annotations

import json

import pytest

from kestrel import paths
from kestrel.runner import orchestrator as orch


@pytest.fixture
def cfg():
    return orch.meter.load_config()


def test_gh_slug():
    assert orch.gh_slug({"repo": "https://github.com/acme/app.git"}) == "acme/app"
    assert orch.gh_slug({"repo": "git@github.com:acme/app.git"}) == "acme/app"
    assert orch.gh_slug({"repo": ""}) == ""


def test_owner_comes_from_config(cfg):
    assert orch.owner(cfg) == ""
    assert orch.owner({"owner": {"github": " acme "}}) == "acme"


def test_pr_flags_label_only_the_owners_repos(cfg):
    mine = {"repo": "https://github.com/acme/app.git", "pr_mode": "ready"}
    theirs = {"repo": "https://github.com/someone/app.git", "pr_mode": "draft"}
    acme = {"owner": {"github": "Acme"}}
    assert orch.pr_flags(mine, acme) == "--label agent"
    assert orch.pr_flags(theirs, acme) == "--draft"
    assert orch.pr_flags(mine, cfg) == "(no extra flags)"  # no owner configured: no labels
    assert "never push" in orch.pr_flags({"pr_mode": "none"}, cfg)


@pytest.mark.parametrize(
    "branch, ok",
    [
        ("feat/TEL-014-lock-screen", True),
        ("security/ABC-001-x", True),
        ("main", False),
        ("feature/TEL-014-x", False),
        ("feat/TE-014-x", False),
    ],
)
def test_task_branch_pattern(branch, ok):
    assert bool(orch.TASK_BRANCH_RE.match(branch)) is ok


def test_charter_points_at_packaged_tools(cfg):
    text = orch.charter("sandbox", cfg["teams"]["sandbox"], cfg)
    assert f"python {paths.RUNNER.as_posix()}/shoot.py" in text
    assert "hq/" not in text
    assert "Rules" in text  # the rules are embedded


def test_settings_hook_passes_the_home_folder():
    hooks = orch.settings_json()["hooks"]
    cmd = hooks["PreToolUse"][0]["hooks"][0]["command"]
    assert cmd.endswith(f'--home "{orch.HQ.as_posix()}"')
    assert paths.RUNNER.joinpath("guard.py").as_posix() in cmd
    assert hooks["PostToolUse"] == hooks["PreToolUse"]


def test_agents_json_reads_role_frontmatter(tmp_path):
    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "tester.md").write_text(
        "---\nname: tester\ndescription: Runs tests\ntools: Read, Bash\nmodel: haiku\n---\nYou test.\n",
        encoding="utf-8",
    )
    (agents / "broken.md").write_text("no frontmatter", encoding="utf-8")
    assert json.loads(orch.agents_json(tmp_path)) == {
        "tester": {"description": "Runs tests", "prompt": "You test.", "tools": ["Read", "Bash"], "model": "haiku"}
    }


def test_every_role_prompt_ships_with_frontmatter():
    for role in orch.ROLES:
        text = (paths.RUNNER / "roles" / f"{role}.md").read_text(encoding="utf-8")
        assert text.startswith("---\n") and f"name: {role}\n" in text and "model: {MODEL}" in text


def test_refuses_to_run_inside_a_git_repository(tmp_path, monkeypatch):
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(orch, "HQ", tmp_path / "home")
    assert orch.parent_git_repo() == tmp_path.resolve()
    monkeypatch.setattr(orch, "HQ", tmp_path)
    assert orch.parent_git_repo() == tmp_path.resolve()
