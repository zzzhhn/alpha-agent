"""Phase A audit tests — A3 + A4 verification.

A3 (`_assert_trading_days`): a panel containing a non-NYSE date (e.g. a
Saturday) must raise DataIntegrityError BEFORE any IC / Sharpe computation
sees it. The legacy mode (silently NaN out and pollute per-day metrics)
is the bug class A3 exists to prevent.

A4 (`DataFetcherManager`): when the highest-priority fetcher misses, the
manager must transparently fall through to the next priority and surface
which sources were attempted. Tests below mock two fake fetchers so the
failover behavior is observable without live network access.
"""
from __future__ import annotations

import threading

import numpy as np
import pandas as pd
import pytest

from alpha_agent.core.exceptions import DataIntegrityError
from alpha_agent.data.manager import BaseFetcher, DataFetcherManager
from alpha_agent.factor_engine.factor_backtest import _assert_trading_days


# ── A3 ──────────────────────────────────────────────────────────────────────


class TestExchangeCalendarAssertion:
    """A3: panel.dates ⊆ NYSE.sessions(start, end), or hard-error."""

    def test_clean_nyse_dates_pass(self) -> None:
        # First 10 NYSE sessions of 2024 (Jan 2 = first session, MLK day skipped).
        dates = pd.bdate_range("2024-01-02", periods=20).strftime("%Y-%m-%d").to_numpy()
        # Filter out MLK day (2024-01-15) since bdate_range only excludes weekends.
        dates = np.array([d for d in dates if d != "2024-01-15"])
        # Should not raise.
        _assert_trading_days(dates, calendar_name="XNYS")

    def test_saturday_in_panel_raises(self) -> None:
        # Insert a Saturday — must blow up before IC machinery sees it.
        dates = np.array(
            ["2024-01-02", "2024-01-03", "2024-01-06"],  # Tue, Wed, *SATURDAY*
            dtype=object,
        )
        with pytest.raises(DataIntegrityError, match="non-XNYS"):
            _assert_trading_days(dates, calendar_name="XNYS")

    def test_us_holiday_raises(self) -> None:
        # 2024-01-15 (MLK Day) is not a NYSE session.
        dates = np.array(
            ["2024-01-12", "2024-01-15", "2024-01-16"],
            dtype=object,
        )
        with pytest.raises(DataIntegrityError):
            _assert_trading_days(dates, calendar_name="XNYS")


# ── A4 ──────────────────────────────────────────────────────────────────────


class _FakeFetcher:
    """Test double satisfying BaseFetcher Protocol."""

    def __init__(
        self,
        name: str,
        priority: int,
        result: pd.DataFrame | None,
        raises: BaseException | None = None,
    ) -> None:
        self.name = name
        self.priority = priority
        self._result = result
        self._raises = raises
        self.call_count = 0

    def fetch_ohlcv(
        self, ticker: str, start: str, end: str,
    ) -> pd.DataFrame | None:
        self.call_count += 1
        if self._raises is not None:
            raise self._raises
        return self._result


def _ohlcv(rows: int = 3) -> pd.DataFrame:
    return pd.DataFrame({
        "open": [100.0] * rows, "high": [101.0] * rows, "low": [99.0] * rows,
        "close": [100.5] * rows, "volume": [1000] * rows,
    })


class TestDataFetcherManagerFailover:
    """A4: priority-failover + per-source RLock + transparent miss logging."""

    def test_primary_hit_stops_chain(self) -> None:
        primary = _FakeFetcher("primary", priority=1, result=_ohlcv())
        fallback = _FakeFetcher("fallback", priority=2, result=_ohlcv())
        mgr = DataFetcherManager()
        mgr.register(primary)
        mgr.register(fallback)

        df = mgr.fetch_ohlcv("AAPL", "2024-01-01", "2024-01-10")
        assert df is not None and not df.empty
        assert primary.call_count == 1
        assert fallback.call_count == 0, "fallback called when primary succeeded"

    def test_primary_miss_falls_through(self) -> None:
        primary = _FakeFetcher("primary", priority=1, result=None)
        fallback = _FakeFetcher("fallback", priority=2, result=_ohlcv())
        mgr = DataFetcherManager()
        mgr.register(primary)
        mgr.register(fallback)

        df = mgr.fetch_ohlcv("AAPL", "2024-01-01", "2024-01-10")
        assert df is not None and not df.empty
        assert primary.call_count == 1
        assert fallback.call_count == 1

    def test_primary_raises_falls_through(self) -> None:
        """Per docstring: 'Per-source exceptions are caught and logged so
        one bad source doesn't kill the chain.' Verify the catch."""
        primary = _FakeFetcher(
            "primary", priority=1, result=None,
            raises=ConnectionError("upstream down"),
        )
        fallback = _FakeFetcher("fallback", priority=2, result=_ohlcv())
        mgr = DataFetcherManager()
        mgr.register(primary)
        mgr.register(fallback)

        df = mgr.fetch_ohlcv("AAPL", "2024-01-01", "2024-01-10")
        assert df is not None and not df.empty
        assert primary.call_count == 1
        assert fallback.call_count == 1

    def test_all_miss_returns_none(self) -> None:
        f1 = _FakeFetcher("a", priority=1, result=None)
        f2 = _FakeFetcher("b", priority=2, result=None)
        mgr = DataFetcherManager()
        mgr.register(f1)
        mgr.register(f2)
        assert mgr.fetch_ohlcv("AAPL", "2024-01-01", "2024-01-10") is None

    def test_priority_order_independent_of_register_order(self) -> None:
        """Register priority=2 first, then priority=1; manager must still
        try priority=1 first."""
        low = _FakeFetcher("low_priority", priority=2, result=_ohlcv())
        high = _FakeFetcher("high_priority", priority=1, result=_ohlcv())
        mgr = DataFetcherManager()
        mgr.register(low)   # registered first
        mgr.register(high)  # higher priority but registered second

        assert mgr.names() == ["high_priority", "low_priority"]
        mgr.fetch_ohlcv("AAPL", "2024-01-01", "2024-01-10")
        assert high.call_count == 1
        assert low.call_count == 0

    def test_register_rejects_duplicate_name(self) -> None:
        mgr = DataFetcherManager()
        mgr.register(_FakeFetcher("dup", priority=1, result=None))
        with pytest.raises(ValueError, match="already registered"):
            mgr.register(_FakeFetcher("dup", priority=2, result=None))

    def test_empty_manager_returns_none_safely(self) -> None:
        mgr = DataFetcherManager()
        assert mgr.fetch_ohlcv("AAPL", "2024-01-01", "2024-01-10") is None

    def test_per_source_lock_serializes_same_source(self) -> None:
        """Two threads hammering the same fetcher must serialize through the
        per-source RLock. Concurrent threads on DIFFERENT fetchers are not
        tested here (Python GIL + the simple counter pattern is too noisy)."""
        in_flight = {"count": 0, "max": 0}
        in_flight_lock = threading.Lock()

        class _SerializingFetcher:
            name = "shared"
            priority = 1

            def fetch_ohlcv(self, ticker, start, end):
                with in_flight_lock:
                    in_flight["count"] += 1
                    in_flight["max"] = max(in_flight["max"], in_flight["count"])
                # tiny sleep to make the serialization observable
                threading.Event().wait(0.005)
                with in_flight_lock:
                    in_flight["count"] -= 1
                return _ohlcv()

        mgr = DataFetcherManager()
        mgr.register(_SerializingFetcher())

        threads = [
            threading.Thread(
                target=mgr.fetch_ohlcv, args=(f"T{i}", "2024-01-01", "2024-01-10")
            )
            for i in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # If the per-source lock is working, max concurrent in-flight must be 1.
        assert in_flight["max"] == 1, (
            f"per-source RLock did not serialize: max in-flight = {in_flight['max']}"
        )
