"""Tests for the build-card CLI orchestrator (Task 24)."""
from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from alpha_agent.core.types import RatingCard
from alpha_agent.signals.base import SignalScore


def _make_score(name: str, z: float = 1.0, confidence: float = 0.8) -> SignalScore:
    return SignalScore(
        ticker="AAPL",
        z=z,
        raw=f"mock:{name}",
        confidence=confidence,
        as_of=datetime(2026, 5, 10),
        source="mock",
        error=None,
    )


_ALL_SIGNAL_NAMES = [
    "factor", "technicals", "analyst", "earnings", "news",
    "insider", "options", "premarket", "macro", "calendar",
]


class TestBuildCardOrchestrator:
    def test_all_positive_signals_return_valid_rating_card(self):
        """Patch all 10 signals to non-zero scores; assert valid RatingCard returned."""
        from alpha_agent.cli.build_card import build_card, _SIGNAL_NAMES

        patch_targets = {
            name: _make_score(name, z=1.2, confidence=0.9)
            for name in _SIGNAL_NAMES
        }
        # calendar has zero weight but confidence=0 in fixture; use real signal names
        patches = {}
        for name in _SIGNAL_NAMES:
            mod_path = f"alpha_agent.signals.{name}.fetch_signal"
            patches[mod_path] = patch_targets[name]

        # Apply all patches at module attribute level
        patcher_list = []
        for mod_path, score in patches.items():
            p = patch(mod_path, return_value=score)
            patcher_list.append(p)
            p.start()

        try:
            card = build_card("AAPL", datetime(2026, 5, 10), use_fixtures=False)
        finally:
            for p in patcher_list:
                p.stop()

        assert isinstance(card, RatingCard)
        assert card.ticker == "AAPL"
        assert card.tier in ("BUY", "OW", "HOLD", "UW", "SELL")
        assert 0.0 <= card.confidence <= 1.0
        assert len(card.breakdown) == len(_SIGNAL_NAMES)

    def test_fixture_mode_returns_valid_rating_card(self):
        """--use-fixtures path: no mocking needed, deterministic result."""
        from alpha_agent.cli.build_card import build_card

        card = build_card("TSLA", datetime(2026, 5, 10), use_fixtures=True)

        assert isinstance(card, RatingCard)
        assert card.ticker == "TSLA"
        assert card.tier in ("BUY", "OW", "HOLD", "UW", "SELL")
        assert 0.0 <= card.confidence <= 1.0

    def test_module_names_for_fixtures_returns_10_names(self):
        from alpha_agent.cli.build_card import _module_names_for_fixtures

        names = _module_names_for_fixtures()
        assert len(names) == 10
        assert "factor" in names
        assert "calendar" in names
