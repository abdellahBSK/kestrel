from __future__ import annotations

import datetime as dt

from conftest import team_project_dir, usage_record, write_transcript
from controlroom import meter


def now_iso(delta_minutes: int = 0) -> str:
    t = dt.datetime.now(dt.UTC) + dt.timedelta(minutes=delta_minutes)
    return t.isoformat().replace("+00:00", "Z")


def test_sanitize_matches_claude_code_folder_naming():
    assert meter.sanitize(r"C:\Users\me\cr\teams\x") == "C--Users-me-cr-teams-x"
    assert meter.sanitize("/home/me/.cr/teams/x") == "-home-me--cr-teams-x"


def test_owner_of_tells_team_sessions_from_personal_ones(fake_claude_projects):
    team_dir = team_project_dir(fake_claude_projects, "sandbox")
    assert meter.owner_of(team_dir.name) == "team:sandbox"
    assert meter.owner_of(team_dir.name.upper()) == "team:sandbox"
    assert meter.owner_of("C--Users-me-code-myapp") == "personal"
    # another install's teams folder is not ours
    assert meter.owner_of("C--elsewhere-teams-sandbox") == "personal"


def test_model_factor_prefers_specific_versions():
    assert meter.model_factor("claude-opus-5-5") == 1.0
    assert meter.model_factor("claude-opus-4-1") == 1.25
    assert meter.model_factor("claude-sonnet-5-5") == 0.5
    assert meter.model_factor("claude-haiku-5-5") == 0.025
    assert meter.model_factor("some-other-model") == 1.0
    assert meter.model_factor("") == 1.0


def test_team_usage_is_weighted_and_deduplicated(fake_claude_projects):
    cfg = meter.load_config()
    since = dt.datetime.now().astimezone() - dt.timedelta(hours=1)
    rec = usage_record(now_iso(), "m1", inp=100, out=50, cw=10, cr=1000)
    write_transcript(
        team_project_dir(fake_claude_projects, "sandbox") / "s1.jsonl",
        [
            rec,
            rec,  # Claude Code repeats a message once per content block: count it once
            usage_record(now_iso(), "m2", model="claude-sonnet-5-5", inp=200),
            usage_record(now_iso(-120), "old", inp=10_000),  # before `since`
        ],
    )
    # opus: 100 + 50 + 10 (cache reads weigh 0) ; sonnet: 200 * 0.5
    assert meter.team_used_since("sandbox", since, cfg) == 160 + 100
    assert meter.team_used_since("todo-api", since, cfg) == 0


def test_summary_splits_personal_and_agent_usage(fake_claude_projects):
    cfg = meter.load_config()
    write_transcript(
        team_project_dir(fake_claude_projects, "sandbox") / "a.jsonl", [usage_record(now_iso(), "t1", inp=300)]
    )
    write_transcript(fake_claude_projects / "C--me-myapp" / "b.jsonl", [usage_record(now_iso(), "p1", out=40)])
    s = meter.summary(cfg)
    assert s["today"]["team:sandbox"] == 300
    assert s["today"]["agents"] == 300
    assert s["today"]["personal"] == 40
    assert s["week"]["agents"] == 300


def test_summary_has_a_daily_series_ending_today(fake_claude_projects):
    cfg = meter.load_config()
    write_transcript(
        team_project_dir(fake_claude_projects, "sandbox") / "a.jsonl", [usage_record(now_iso(), "t1", inp=70)]
    )
    daily = meter.summary(cfg)["daily"]
    assert len(daily) == 7
    assert daily[-1]["date"] == meter.start_of_today().date().isoformat()
    assert daily[-1]["agents"] == 70 and daily[0]["agents"] == 0
