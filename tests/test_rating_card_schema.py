"""Tests for RatingCard + BreakdownEntry Pydantic models (Task 23)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from alpha_agent.core.types import BreakdownEntry, RatingCard


def _valid_breakdown_entry(**overrides) -> dict:
    base = {
        "signal": "analyst",
        "z": 1.0,
        "weight": 0.1,
        "weight_effective": 0.12,
        "contribution": 0.12,
        "raw": {"recommendation": "buy"},
        "source": "yfinance",
        "timestamp": "2026-05-10T00:00:00",
        "error": None,
    }
    return {**base, **overrides}


def _valid_rating_card(**overrides) -> dict:
    entry = _valid_breakdown_entry()
    base = {
        "ticker": "AAPL",
        "as_of": "2026-05-10",
        "tier": "OW",
        "composite": 0.85,
        "confidence": 0.72,
        "drivers": ["analyst"],
        "drags": [],
        "breakdown": [entry],
    }
    return {**base, **overrides}


class TestRatingCardValidatesRequiredFields:
    def test_valid_card_round_trips(self):
        data = _valid_rating_card()
        card = RatingCard(**data)
        assert card.ticker == "AAPL"
        assert card.tier == "OW"
        assert card.confidence == pytest.approx(0.72)
        assert len(card.breakdown) == 1
        assert card.breakdown[0].signal == "analyst"

    def test_missing_ticker_raises(self):
        data = _valid_rating_card()
        del data["ticker"]
        with pytest.raises(ValidationError):
            RatingCard(**data)

    def test_missing_tier_raises(self):
        data = _valid_rating_card()
        del data["tier"]
        with pytest.raises(ValidationError):
            RatingCard(**data)

    def test_extra_field_forbidden(self):
        data = _valid_rating_card()
        data["unexpected_key"] = "boom"
        with pytest.raises(ValidationError):
            RatingCard(**data)


class TestRatingCardRejectsInvalidTier:
    def test_invalid_tier_string(self):
        data = _valid_rating_card(tier="STRONG_BUY")
        with pytest.raises(ValidationError):
            RatingCard(**data)

    def test_lowercase_tier_rejected(self):
        data = _valid_rating_card(tier="buy")
        with pytest.raises(ValidationError):
            RatingCard(**data)

    def test_all_valid_tiers_accepted(self):
        for tier in ("BUY", "OW", "HOLD", "UW", "SELL"):
            card = RatingCard(**_valid_rating_card(tier=tier))
            assert card.tier == tier


class TestRatingCardRejectsOutOfBoundsConfidence:
    def test_confidence_above_one(self):
        data = _valid_rating_card(confidence=1.01)
        with pytest.raises(ValidationError):
            RatingCard(**data)

    def test_confidence_below_zero(self):
        data = _valid_rating_card(confidence=-0.01)
        with pytest.raises(ValidationError):
            RatingCard(**data)

    def test_boundary_values_accepted(self):
        for val in (0.0, 1.0):
            card = RatingCard(**_valid_rating_card(confidence=val))
            assert card.confidence == pytest.approx(val)


class TestBreakdownEntry:
    def test_valid_entry(self):
        entry = BreakdownEntry(**_valid_breakdown_entry())
        assert entry.signal == "analyst"
        assert entry.z == pytest.approx(1.0)

    def test_z_out_of_bounds_rejected(self):
        with pytest.raises(ValidationError):
            BreakdownEntry(**_valid_breakdown_entry(z=3.5))

    def test_weight_out_of_bounds_rejected(self):
        with pytest.raises(ValidationError):
            BreakdownEntry(**_valid_breakdown_entry(weight=1.5))
