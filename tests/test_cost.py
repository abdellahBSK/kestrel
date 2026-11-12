"""Estimated cost, retries and durations (spec 008)."""

from __future__ import annotations

import pytest

from kestrel.core import cost, runs

TH = {"heartbeat_timeout": 45, "idle_after": 120, "stale_after": 600}
TABLE = cost.price_table()


def test_known_models_are_priced_per_million_tokens():
    usd = cost.cost("claude-sonnet-5-5", {"input": 1_000_000, "output": 100_000}, TABLE)
    assert usd == pytest.approx(2.00 + 1.00)


def test_the_most_specific_name_wins():
    assert cost.price_of("claude-opus-5-5", TABLE)["input"] == 4.00
    assert cost.price_of("claude-opus-5", TABLE)["input"] == 5.00
    assert cost.price_of("claude-fable-5-2", TABLE)["input"] == 8.00


def test_cache_tokens_have_their_own_prices():
    usd = cost.cost("claude-opus-5-5", {"cache_write": 1_000_000, "cache_read": 1_000_000}, TABLE)
    assert usd == pytest.approx(5.00 + 0.20)


def test_unknown_models_are_unknown_not_free():
    assert cost.cost("gpt-something", {"input": 10}, TABLE) is None
    assert cost.cost("", {"input": 10}, TABLE) is None
    assert cost.cost("gpt-something", {}, TABLE) == 0.0  # no tokens, no cost


def test_an_events_own_cost_wins():
    assert cost.cost("gpt-something", {"input": 10, "cost_usd": 0.42}, TABLE) == 0.42


def test_config_prices_add_models_and_override_defaults():
    cfg = {"prices": {"gpt-x": {"input": 1.0, "output": 4.0}, "sonnet-5-5": {"input": 9.0, "output": 9.0}}}
    table = cost.price_table(cfg)
    assert cost.cost("gpt-x-mini", {"input": 1_000_000}, table) == pytest.approx(1.0)
    assert cost.price_of("gpt-x", table)["cache_read"] == pytest.approx(0.1)  # defaults from input
    assert cost.price_of("claude-sonnet-5-5", table)["input"] == 9.0


def fold(rows):
    price = lambda model, d: cost.cost(model, d, TABLE)  # noqa: E731
    return runs.fold(rows, heartbeat=None, now=rows[-1][0] + 1, th=TH, price=price)


def test_run_and_agent_costs_add_up_and_flag_unknowns():
    f = fold(
        [
            (100.0, "agent.started", "dev", {"role": "developer"}),
            (101.0, "agent.tokens", "dev", {"input": 1_000_000, "model": "claude-haiku-5-5"}),
            (102.0, "agent.tokens", "dev", {"input": 5, "model": "mystery-model"}),
        ]
    )
    [dev] = f["agents"]
    assert dev["cost_usd"] == pytest.approx(0.10) and dev["cost_unknown"] is True
    assert f["run"]["cost_usd"] == pytest.approx(0.10) and f["run"]["cost_unknown"] is True


def test_retries_count_repeats_of_failed_actions():
    f = fold(
        [
            (100.0, "agent.action", "dev", {"tool": "Bash", "detail": "npm test", "status": "error"}),
            (101.0, "agent.action", "dev", {"tool": "Bash", "detail": "npm test", "status": "error"}),
            (102.0, "agent.action", "dev", {"tool": "Bash", "detail": "npm test", "status": "ok"}),
            (103.0, "agent.action", "dev", {"tool": "Bash", "detail": "npm run lint", "status": "ok"}),
            (104.0, "agent.action", "dev", {"tool": "Bash", "detail": "npm run lint", "status": "ok"}),
        ]
    )
    [dev] = f["agents"]
    assert dev["errors"] == 2 and dev["retries"] == 2  # repeating a success is not a retry
    assert "failed" not in dev


def test_a_call_that_fails_later_counts_for_retries():
    f = fold(
        [
            (100.0, "agent.action", "dev", {"tool": "Bash", "detail": "make", "status": "running", "call": "c1"}),
            (101.0, "agent.action", "dev", {"call": "c1", "status": "error"}),
            (102.0, "agent.action", "dev", {"tool": "Bash", "detail": "make", "status": "ok"}),
        ]
    )
    assert f["agents"][0]["retries"] == 1
