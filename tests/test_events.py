"""The v1 event format: validation, normalization and secret scrubbing."""

from __future__ import annotations

import pytest

from controlroom.events import EventError, normalize, scrub

NOW = 1_794_473_380.0  # 2026-11-12T08:49:40Z


def ev(**kw):
    base = {"type": "agent.action", "project": "shop", "run": "r1", "agent": "dev-1", "data": {"tool": "Bash"}}
    return normalize({**base, **kw}, now=NOW)


def test_a_minimal_event_is_normalized():
    e = ev(ts="2026-11-12T08:49:43Z")
    assert e["ts"] == NOW + 3 and e["type"] == "agent.action" and e["project"] == "shop"
    assert e["data"]["status"] == "ok" and len(e["id"]) == 32


def test_timestamps_must_carry_a_timezone():
    assert ev(ts="2026-11-12T09:49:43+01:00")["ts"] == NOW + 3
    assert ev(ts=NOW - 10)["ts"] == NOW - 10
    assert ev(ts=None)["ts"] == NOW
    with pytest.raises(EventError, match="timezone"):
        ev(ts="2026-11-12T08:49:43")
    with pytest.raises(EventError, match="milliseconds"):
        ev(ts=1_794)
    assert ev(ts=NOW + 3600)["ts"] == NOW  # a clock far ahead is clamped to now


@pytest.mark.parametrize(
    "raw, message",
    [
        ({"type": "nope"}, "unknown event type"),
        ({"v": 2}, "unsupported event version"),
        ({"project": ""}, "project is required"),
        ({"project": "has space"}, "project must be"),
        ({"agent": None}, "agent is required"),
        ({"data": "text"}, "data must be a JSON object"),
        ({"data": {}}, "data.tool is required"),
        ({"data": {"tool": "Bash", "status": "done"}}, "data.status must be one of"),
        ({"type": "agent.tokens", "data": {"input": -1}}, "data.input"),
        ({"type": "agent.message", "data": {}}, "data.text is required"),
        ({"type": "pr.opened", "data": {"number": 3, "url": "javascript:alert(1)"}}, "http"),
        ({"type": "run.finished", "agent": None, "data": {"status": "great"}}, "data.status"),
    ],
)
def test_malformed_events_are_rejected_with_a_clear_message(raw, message):
    with pytest.raises(EventError, match=message):
        ev(**raw)


def test_run_and_pr_events():
    assert ev(type="run.started", agent=None, data={"title": "Fix login", "budget": 5000})["data"]["budget"] == 5000
    assert ev(type="run.finished", agent=None, data={})["data"]["status"] == "ok"
    pr = ev(type="pr.opened", run=None, agent=None, data={"number": 7, "url": "https://github.com/a/b/pull/7"})
    assert pr["run"] is None and pr["data"]["draft"] is False
    assert ev(type="agent.started", data={"role": "Tester"})["data"]["role"] == "tester"


def test_an_action_update_needs_only_its_call_id():
    assert ev(data={"call": "c1", "status": "error", "result": "boom"})["data"]["status"] == "error"


def test_unknown_fields_are_kept_and_long_text_truncated():
    e = ev(data={"tool": "Bash", "detail": "x" * 20_000, "future_field": 1})
    assert e["data"]["future_field"] == 1 and len(e["data"]["detail"]) == 8000


@pytest.mark.parametrize(
    "secret",
    [
        "ghp_" + "a" * 36,
        "github_pat_" + "B" * 40,
        "sk-ant-api03-" + "c" * 30,
        "sk-proj-" + "d" * 40,
        "AKIA" + "E" * 16,
        "xoxb-1234567890-abcdefghij",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----",
    ],
)
def test_secrets_are_scrubbed_from_every_string(secret):
    e = ev(data={"tool": "Bash", "detail": f"echo {secret}", "result": f"got {secret}", "extra": [secret]})
    assert secret not in str(e) and "[redacted]" in e["data"]["detail"]


def test_scrub_keeps_the_key_and_spares_ordinary_text():
    assert scrub("export API_KEY=abc123xyz789") == "export API_KEY=[redacted]"
    assert scrub('AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG"') == 'AWS_SECRET_ACCESS_KEY="[redacted]"'
    assert scrub("curl -H 'Authorization: Bearer abcdefghijklmnop'") == "curl -H 'Authorization: Bearer [redacted]'"
    assert scrub("git clone https://bob:hunter22@github.com/x") == "git clone https://[redacted]@github.com/x"
    for fine in ("tokens: 400000", "npm test", "password reset screen", "the secret sauce"):
        assert scrub(fine) == fine
