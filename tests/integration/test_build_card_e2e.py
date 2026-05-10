"""End-to-end integration tests for the build-card pipeline (Task 25).

All signals are patched at module-attribute level so no external APIs are hit.
Three acceptance tests:
  1. All-positive signals yield BUY or OW tier.
  2. RatingCard Pydantic round-trip (JSON serialise → deserialise) is lossless.
  3. One-signal-fails graceful degradation: confidence drops to 0, pipeline
     continues and produces a valid card with composite based on remaining signals.
"""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

from alpha_agent.core.types import RatingCard
from alpha_agent.signals.base import SignalScore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SIGNAL_MODULES = [
    "factor", "technicals", "analyst", "earnings", "news",
    "insider", "options", "premarket", "macro", "calendar",
]

_AS_OF = datetime(2026, 5, 10)
_TICKER = "AAPL"


def _score(name: str, z: float = 1.8, confidence: float = 0.9) -> SignalScore:
    return SignalScore(
        ticker=_TICKER,
        z=z,
        raw=f"e2e:{name}",
        confidence=confidence,
        as_of=_AS_OF,
        source="mock",
        error=None,
    )


def _zero_score(name: str) -> SignalScore:
    """Confidence=0 simulates a gracefully-failed signal."""
    return SignalScore(
        ticker=_TICKER,
        z=0.0,
        raw=None,
        confidence=0.0,
        as_of=_AS_OF,
        source="mock",
        error="simulated failure",
    )


def _patch_all_signals(scores: dict[str, SignalScore]):
    """Return a list of context managers patching each signal's fetch_signal."""
    patchers = []
    for name in _SIGNAL_MODULES:
        score = scores.get(name, _score(name))
        patchers.append(
            patch(f"alpha_agent.signals.{name}.fetch_signal", return_value=score)
        )
    return patchers


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildCardE2E:
    def test_all_positive_signals_yield_buy_or_ow(self):
        """When every signal is strongly positive, tier must be BUY or OW."""
        from alpha_agent.cli.build_card import build_card

        # Strong positive z=1.8 for all signals
        scores = {name: _score(name, z=1.8) for name in _SIGNAL_MODULES}
        # calendar keeps z but confidence=0 matches its fixture convention
        scores["calendar"] = _score("calendar", z=0.0, confidence=0.0)

        patchers = _patch_all_signals(scores)
        for p in patchers:
            p.start()
        try:
            card = build_card(_TICKER, _AS_OF, use_fixtures=False)
        finally:
            for p in patchers:
                p.stop()

        assert card.tier in ("BUY", "OW"), (
            f"Expected BUY or OW with strong positive signals, got {card.tier}"
        )
        assert card.composite > 0.5, (
            f"Composite should be > 0.5 with all positive signals, got {card.composite}"
        )

    def test_pydantic_round_trip_is_lossless(self):
        """RatingCard -> JSON -> RatingCard should be identical."""
        from alpha_agent.cli.build_card import build_card

        card = build_card(_TICKER, _AS_OF, use_fixtures=True)

        json_str = card.model_dump_json()
        card2 = RatingCard.model_validate_json(json_str)

        assert card2.ticker == card.ticker
        assert card2.tier == card.tier
        assert abs(card2.composite - card.composite) < 1e-9
        assert abs(card2.confidence - card.confidence) < 1e-9
        assert len(card2.breakdown) == len(card.breakdown)
        for b1, b2 in zip(card.breakdown, card2.breakdown):
            assert b1.signal == b2.signal
            assert abs(b1.z - b2.z) < 1e-9

    def test_one_signal_fails_graceful_degradation(self):
        """One signal returning confidence=0 should not crash the pipeline.

        The failing signal's contribution is zeroed and weights re-normalise
        across the remaining signals; final card must still be a valid RatingCard.
        """
        from alpha_agent.cli.build_card import build_card

        # All signals positive except 'macro' which gracefully fails
        scores = {name: _score(name, z=1.0) for name in _SIGNAL_MODULES}
        scores["macro"] = _zero_score("macro")
        scores["calendar"] = _score("calendar", z=0.0, confidence=0.0)

        patchers = _patch_all_signals(scores)
        for p in patchers:
            p.start()
        try:
            card = build_card(_TICKER, _AS_OF, use_fixtures=False)
        finally:
            for p in patchers:
                p.stop()

        # Card is valid
        assert isinstance(card, RatingCard)
        assert card.tier in ("BUY", "OW", "HOLD", "UW", "SELL")
        assert 0.0 <= card.confidence <= 1.0

        # Macro breakdown entry exists but its contribution is 0
        macro_row = next(b for b in card.breakdown if b.signal == "macro")
        assert macro_row.contribution == pytest.approx(0.0), (
            f"Gracefully failed signal should have zero contribution, got {macro_row.contribution}"
        )
