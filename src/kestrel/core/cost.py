"""Estimated cost of tokens, in US dollars (spec 008).

Prices are first-party Claude API list prices per million tokens, as of PRICES_AS_OF. They are
estimates: subscription plans, partner platforms (Bedrock, Vertex AI), batch discounts and long
prompt surcharges price differently. `[prices."<model name part>"]` in the config adds or
overrides entries, for other providers too. Tokens of a model no entry matches have no cost:
Kestrel shows them as unknown rather than guess.
"""

from __future__ import annotations

PRICES_AS_OF = "2026-11-03"

# (part of the model id, input, output, cache write, cache read) in USD per million tokens.
# The first entry contained in a model id wins, so specific versions come before shorter names.
# Cache writes are 1.25x input; cache reads use the model's listed rate, else 0.1x input.
DEFAULT_PRICES: list[tuple[str, float, float, float, float]] = [
    ("fable-5-2", 8.00, 40.00, 10.00, 0.20),
    ("mythos-5-2", 8.00, 40.00, 10.00, 0.20),
    ("fable-5-1", 10.00, 50.00, 12.50, 1.00),
    ("mythos-5-1", 10.00, 50.00, 12.50, 1.00),
    ("fable-5", 10.00, 50.00, 12.50, 1.00),
    ("mythos-5", 10.00, 50.00, 12.50, 1.00),
    ("opus-5-5", 4.00, 20.00, 5.00, 0.20),
    ("opus-5", 5.00, 25.00, 6.25, 0.50),
    ("opus-4-8", 5.00, 25.00, 6.25, 0.50),
    ("opus-4-7", 5.00, 25.00, 6.25, 0.50),
    ("opus-4-6", 5.00, 25.00, 6.25, 0.50),
    ("sonnet-5-5", 2.00, 10.00, 2.50, 0.10),
    ("sonnet-5", 2.00, 10.00, 2.50, 0.20),
    ("sonnet-4-6", 3.00, 15.00, 3.75, 0.30),
    ("haiku-5-5", 0.10, 0.50, 0.125, 0.01),
    ("haiku-4-5", 1.00, 5.00, 1.25, 0.10),
]

FIELDS = ("input", "output", "cache_write", "cache_read")


def price_table(cfg: dict | None = None) -> list[tuple[str, dict]]:
    """[(model name part, {input, output, cache_write, cache_read})], the config's entries first."""
    table: list[tuple[str, dict]] = []
    for name, p in ((cfg or {}).get("prices") or {}).items():
        if isinstance(p, dict):
            inp = float(p.get("input", 0))
            table.append(
                (
                    str(name).lower(),
                    {
                        "input": inp,
                        "output": float(p.get("output", 0)),
                        "cache_write": float(p.get("cache_write", inp * 1.25)),
                        "cache_read": float(p.get("cache_read", inp * 0.1)),
                    },
                )
            )
    table += [(n, dict(zip(FIELDS, v, strict=True))) for n, *v in DEFAULT_PRICES]
    return table


def price_of(model: str, table: list[tuple[str, dict]]) -> dict | None:
    m = (model or "").lower()
    if not m:
        return None
    for name, prices in table:
        if name in m:
            return prices
    return None


def cost(model: str, tokens: dict, table: list[tuple[str, dict]]) -> float | None:
    """USD for one agent.tokens event's counts, or None when the model has no price.
    An event's own cost_usd always wins."""
    if tokens.get("cost_usd") is not None:
        return float(tokens["cost_usd"])
    p = price_of(model, table)
    if p is None:
        return None if any(tokens.get(f) for f in FIELDS) else 0.0
    return sum(tokens.get(f, 0) * p[f] for f in FIELDS) / 1_000_000
