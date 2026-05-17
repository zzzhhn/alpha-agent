"""build_card orchestrator: 10 signals → fusion → RatingCard.

Called by ``main.py`` ``build-card`` subcommand and used in integration tests.
Spec §3.2: build_card(ticker, as_of) -> RatingCard.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from alpha_agent.core.types import BreakdownEntry, RatingCard
from alpha_agent.fusion.attribution import top_drivers, top_drags
from alpha_agent.fusion.combine import combine
from alpha_agent.fusion.rating import compute_confidence, map_to_tier
from alpha_agent.fusion.weights import DEFAULT_WEIGHTS
from alpha_agent.signals.base import safe_fetch


# Ordered list of all signal module names (matches DEFAULT_WEIGHTS keys).
_SIGNAL_NAMES: list[str] = [
    "factor",
    "technicals",
    "analyst",
    "earnings",
    "news",
    "insider",
    "options",
    "premarket",
    "macro",
    "calendar",
    "political_impact",
]


def _module_names_for_fixtures() -> list[str]:
    """Return the canonical 10 signal names. Used by --use-fixtures path."""
    return list(_SIGNAL_NAMES)


def _import_signal(name: str):
    """Lazily import a signal module by name."""
    import importlib
    return importlib.import_module(f"alpha_agent.signals.{name}")


def _fixture_signal(name: str, ticker: str, as_of: datetime):
    """Return a deterministic non-zero SignalScore without hitting any API."""
    from alpha_agent.signals.base import SignalScore

    # Deterministic but varied per signal so fusion tests are meaningful.
    _z_map = {
        "factor": 1.5,
        "technicals": 0.8,
        "analyst": 1.2,
        "earnings": 0.6,
        "news": 0.3,
        "insider": 0.9,
        "options": 0.4,
        "premarket": 0.7,
        "macro": 0.2,
        "calendar": 0.0,
        "political_impact": 0.0,
    }
    z = _z_map.get(name, 0.5)
    confidence = 0.0 if name in ("calendar", "political_impact") else 0.80
    return SignalScore(
        ticker=ticker,
        z=z,
        raw=f"fixture:{name}",
        confidence=confidence,
        as_of=as_of,
        source="fixture",
        error=None,
    )


def build_card(
    ticker: str,
    as_of: datetime,
    *,
    use_fixtures: bool = False,
) -> RatingCard:
    """Orchestrate 10-signal fetch → fusion combine → 5-tier rating → RatingCard.

    Parameters
    ----------
    ticker:
        Equity symbol (e.g., ``"AAPL"``).
    as_of:
        Snapshot date for all signal fetches.
    use_fixtures:
        If True, bypass all external APIs and use deterministic fixture values.
        Intended for smoke tests and CI.
    """
    signals: dict[str, Any] = {}
    for name in _SIGNAL_NAMES:
        if use_fixtures:
            sc = _fixture_signal(name, ticker, as_of)
        else:
            mod = _import_signal(name)
            sc = safe_fetch(mod.fetch_signal, ticker, as_of, source=name)
        signals[name] = sc

    result = combine(signals, DEFAULT_WEIGHTS)
    tier = map_to_tier(result.composite)
    zs = [signals[n]["z"] for n in _SIGNAL_NAMES if signals[n]["confidence"] > 0]
    confidence = compute_confidence(zs)
    drivers = top_drivers(result.breakdown)
    drags = top_drags(result.breakdown)

    breakdown = [
        BreakdownEntry(
            signal=row["signal"],
            z=max(min(row["z"], 3.0), -3.0),
            weight=row["weight"],
            weight_effective=row["weight_effective"],
            contribution=row["contribution"],
            raw=row["raw"],
            source=row["source"],
            timestamp=row["timestamp"],
            error=row["error"],
        )
        for row in result.breakdown
    ]

    return RatingCard(
        ticker=ticker,
        as_of=as_of.date().isoformat(),
        tier=tier,
        composite=result.composite,
        confidence=confidence,
        drivers=drivers,
        drags=drags,
        breakdown=breakdown,
    )


def run_build_card_cli(ticker: str, as_of_str: str, use_fixtures: bool) -> None:
    """Parse args and print RatingCard as JSON to stdout."""
    try:
        as_of = datetime.strptime(as_of_str, "%Y-%m-%d")
    except ValueError:
        as_of = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)

    card = build_card(ticker, as_of, use_fixtures=use_fixtures)
    print(json.dumps(card.model_dump(), indent=2))
