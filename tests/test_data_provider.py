"""Tests for the data layer: cache, universe, and provider."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
import sys
import threading
import types

import pandas as pd
import pytest

from alpha_agent.data.cache import ParquetCache
from alpha_agent.data.manager import DataFetcherManager
from alpha_agent.data.provider import AKShareProvider, OHLCV_COLUMNS, _empty_ohlcv_frame
from alpha_agent.data.universe import CSI300Universe
import alpha_agent.data.us_provider as us_provider_mod
from alpha_agent.data.us_provider import YFinanceFetcher, YFinanceProvider


def _build_ohlcv_panel(
    stock_code: str,
    dates: list[str] | pd.DatetimeIndex,
    *,
    base_price: float = 100.0,
) -> pd.DataFrame:
    ts_list = [pd.Timestamp(d) for d in dates]
    idx = pd.MultiIndex.from_arrays(
        [pd.DatetimeIndex(ts_list, name="date"), [stock_code] * len(ts_list)],
        names=["date", "stock_code"],
    )
    n = len(ts_list)
    closes = [base_price + i for i in range(n)]
    return pd.DataFrame(
        {
            "open": [c - 0.5 for c in closes],
            "close": closes,
            "high": [c + 1.0 for c in closes],
            "low": [c - 1.0 for c in closes],
            "volume": [10_000 + i * 100 for i in range(n)],
            "amount": [(10_000 + i * 100) * closes[i] for i in range(n)],
        },
        index=idx,
    )


class _SyntheticUSFetcher:
    """Offline deterministic US fetcher slicing a synthetic panel."""

    name = "synthetic_us"
    priority = 1

    def __init__(self, panels: dict[str, pd.DataFrame]) -> None:
        self._panels = panels
        self.calls: list[tuple[str, str, str]] = []
        self._lock = threading.Lock()

    def fetch_ohlcv(self, ticker: str, start: str, end: str) -> pd.DataFrame | None:
        with self._lock:
            self.calls.append((ticker, start, end))
        panel = self._panels.get(ticker)
        if panel is None:
            return None
        if panel.empty:
            return _empty_ohlcv_frame()
        d = panel.index.get_level_values("date")
        return panel.loc[(d >= pd.Timestamp(start)) & (d <= pd.Timestamp(end))].copy()


# ------------------------------------------------------------------
# ParquetCache & Provider Coverage (R07)
# ------------------------------------------------------------------

class TestParquetCache:
    """Round-trip write/read and interval coverage guarantees through ParquetCache."""

    @staticmethod
    def _sample_df() -> pd.DataFrame:
        """Create a small canonical DataFrame for testing."""
        idx = pd.MultiIndex.from_tuples(
            [
                (pd.Timestamp("2025-01-02"), "600519"),
                (pd.Timestamp("2025-01-03"), "600519"),
            ],
            names=["date", "stock_code"],
        )
        return pd.DataFrame(
            {
                "open": [1800.0, 1810.0],
                "close": [1805.0, 1815.0],
                "high": [1820.0, 1825.0],
                "low": [1790.0, 1800.0],
                "volume": [50000, 52000],
                "amount": [9e9, 9.5e9],
            },
            index=idx,
        )

    def test_roundtrip_covered_range(self, tmp_path: Path) -> None:
        cache = ParquetCache(cache_dir=tmp_path)
        original = self._sample_df()

        cache.put(
            "600519",
            original,
            start_date="20250101",
            end_date="20250103",
            market="CN",
            price_basis="qfq",
        )
        result = cache.get(
            "600519",
            "20250101",
            "20250105",  # Jan 4-5 2025 are Sat/Sun
            market="CN",
            price_basis="qfq",
        )

        assert result is not None
        pd.testing.assert_frame_equal(result, original)

    def test_partial_cache_is_miss_not_false_hit(self, tmp_path: Path) -> None:
        """R07 core: caching Nov 10-11 must NOT satisfy a Nov 02-20 request."""
        cache = ParquetCache(cache_dir=tmp_path)
        narrow = _build_ohlcv_panel("AAPL", ["2026-11-10", "2026-11-11"])
        cache.put(
            "AAPL",
            narrow,
            start_date="20261110",
            end_date="20261111",
            market="US",
            price_basis="adjusted",
        )

        assert (
            cache.get(
                "AAPL",
                "20261102",
                "20261120",
                market="US",
                price_basis="adjusted",
            )
            is None
        )
        assert cache.stats()["hits"] == 0
        assert cache.stats()["misses"] == 1
        assert cache.missing_ranges(
            "AAPL",
            "20261102",
            "20261120",
            market="US",
            price_basis="adjusted",
        ) == [("20261102", "20261109"), ("20261112", "20261120")]

    def test_get_returns_none_when_missing(self, tmp_path: Path) -> None:
        cache = ParquetCache(cache_dir=tmp_path)
        assert cache.get("999999", "20250101", "20250131") is None

    def test_date_slicing(self, tmp_path: Path) -> None:
        cache = ParquetCache(cache_dir=tmp_path)
        original = self._sample_df()
        cache.put("600519", original)

        # Request only the first day (inside covered [2025-01-02, 2025-01-03])
        result = cache.get("600519", "20250102", "20250102")
        assert result is not None
        assert len(result) == 1

    def test_put_does_not_mutate_input(self, tmp_path: Path) -> None:
        cache = ParquetCache(cache_dir=tmp_path)
        original = self._sample_df()
        original_copy = original.copy()

        cache.put("600519", original)
        pd.testing.assert_frame_equal(original, original_copy)

    def test_market_and_price_basis_isolation(self, tmp_path: Path) -> None:
        cache = ParquetCache(cache_dir=tmp_path)
        adj = _build_ohlcv_panel("AAPL", ["2026-11-10", "2026-11-11"], base_price=100.0)
        raw = _build_ohlcv_panel("AAPL", ["2026-11-10", "2026-11-11"], base_price=200.0)

        cache.put(
            "AAPL",
            adj,
            start_date="20261110",
            end_date="20261111",
            market="US",
            price_basis="adjusted",
        )
        assert (
            cache.get(
                "AAPL",
                "20261110",
                "20261111",
                market="US",
                price_basis="raw_unadjusted",
            )
            is None
        )
        assert (
            cache.get(
                "AAPL",
                "20261110",
                "20261111",
                market="CN",
                price_basis="adjusted",
            )
            is None
        )

        # Writing a second basis stores a separate file without clobbering adjusted.
        cache.put(
            "AAPL",
            raw,
            start_date="20261110",
            end_date="20261111",
            market="US",
            price_basis="raw_unadjusted",
        )
        got_adj = cache.get(
            "AAPL", "20261110", "20261111", market="US", price_basis="adjusted"
        )
        got_raw = cache.get(
            "AAPL", "20261110", "20261111", market="US", price_basis="raw_unadjusted"
        )
        assert got_adj is not None and got_raw is not None
        pd.testing.assert_frame_equal(got_adj, adj)
        pd.testing.assert_frame_equal(got_raw, raw)

    def test_legacy_parquet_without_metadata_backfills_uncovered_bounds_and_gaps(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pre-existing Parquet files written via plain `df.to_parquet` must not
        pretend uncovered leading/trailing or internal missing sessions are cached."""
        monkeypatch.setattr(us_provider_mod, "_jittered_sleep", lambda: None)

        # Legacy file has Fri 2026-11-06, Mon 2026-11-09, and Thu 2026-11-12
        # (Tue 11-10 and Wed 11-11 are missing; weekend 11-07/11-08 is closed).
        legacy_df = _build_ohlcv_panel(
            "AAPL", ["2026-11-06", "2026-11-09", "2026-11-12"]
        )
        legacy_df.to_parquet(tmp_path / "AAPL.parquet", engine="pyarrow")

        cache = ParquetCache(cache_dir=tmp_path)
        # Fri -> Mon across weekend IS contiguous on XNYS, so [11-06, 11-09] hits.
        weekend_span = cache.get(
            "AAPL", "20261106", "20261109", market="US", price_basis="adjusted"
        )
        assert weekend_span is not None
        assert len(weekend_span) == 2

        # Requesting [11-05, 11-13] sees missing 11-05, 11-10..11-11, and 11-13.
        assert cache.missing_ranges(
            "AAPL", "20261105", "20261113", market="US", price_basis="adjusted"
        ) == [
            ("20261105", "20261105"),
            ("20261110", "20261111"),
            ("20261113", "20261113"),
        ]

        full_dates = pd.bdate_range("2026-11-05", "2026-11-13")
        fetcher = _SyntheticUSFetcher({"AAPL": _build_ohlcv_panel("AAPL", full_dates)})
        mgr = DataFetcherManager()
        mgr.register(fetcher)
        provider = YFinanceProvider(cache=cache, manager=mgr)

        merged = provider.fetch(["AAPL"], "20261105", "20261113")
        assert len(merged) == len(full_dates)
        assert fetcher.calls == [
            ("AAPL", "2026-11-05", "2026-11-05"),
            ("AAPL", "2026-11-10", "2026-11-11"),
            ("AAPL", "2026-11-13", "2026-11-13"),
        ]

    def test_concurrent_disjoint_ranges_merge_atomically(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Concurrent fetches for different sub-ranges of the same ticker must
        preserve every range's rows and intervals without lost updates or corrupt reads."""
        monkeypatch.setattr(us_provider_mod, "_jittered_sleep", lambda: None)
        cache = ParquetCache(cache_dir=tmp_path)

        all_sessions = [
            d.strftime("%Y-%m-%d")
            for d in pd.bdate_range("2026-10-01", "2026-11-20")
            if d.strftime("%Y-%m-%d") != "2026-11-26"
        ]
        full_panel = _build_ohlcv_panel("MSFT", all_sessions)
        fetcher = _SyntheticUSFetcher({"MSFT": full_panel})
        mgr = DataFetcherManager()
        mgr.register(fetcher)
        provider = YFinanceProvider(cache=cache, manager=mgr)

        windows = [
            ("20261001", "20261009"),
            ("20261012", "20261023"),
            ("20261026", "20261106"),
            ("20261109", "20261120"),
        ]
        barrier = threading.Barrier(len(windows))

        def _worker(win: tuple[str, str]) -> pd.DataFrame:
            barrier.wait(timeout=5.0)
            return provider.fetch(["MSFT"], win[0], win[1])

        with ThreadPoolExecutor(max_workers=len(windows)) as pool:
            results = list(pool.map(_worker, windows))

        for (w_start, w_end), res in zip(windows, results, strict=True):
            assert not res.empty
            assert res.index.get_level_values("date").min() >= pd.Timestamp(w_start)
            assert res.index.get_level_values("date").max() <= pd.Timestamp(w_end)

        # Because weekends between windows (Oct 10-11, Oct 24-25, Nov 7-8) are closed
        # on XNYS, the full Oct 01 -> Nov 20 span is now 100% covered with 0 misses!
        calls_before = len(fetcher.calls)
        combined = provider.fetch(["MSFT"], "20261001", "20261120")
        assert len(fetcher.calls) == calls_before
        pd.testing.assert_frame_equal(combined, full_panel)


class TestProviderCacheCoverage:
    """End-to-end R07 scenarios through YFinanceProvider and AKShareProvider."""

    def test_us_provider_narrow_then_wide_and_disjoint_merge(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Audit R07 exact reproducer: cache 11-10..11-11, then request 11-02..11-20."""
        monkeypatch.setattr(us_provider_mod, "_jittered_sleep", lambda: None)
        cache = ParquetCache(cache_dir=tmp_path)

        full_dates = pd.bdate_range("2026-11-02", "2026-11-20")
        full_panel = _build_ohlcv_panel("AAPL", full_dates)
        fetcher = _SyntheticUSFetcher({"AAPL": full_panel})
        mgr = DataFetcherManager()
        mgr.register(fetcher)
        provider = YFinanceProvider(cache=cache, manager=mgr)

        narrow = provider.fetch(["AAPL"], "20261110", "20261111")
        assert len(narrow) == 2

        wide = provider.fetch(["AAPL"], "20261102", "20261120")
        assert len(wide) == 15
        pd.testing.assert_frame_equal(wide, full_panel)
        assert fetcher.calls == [
            ("AAPL", "2026-11-10", "2026-11-11"),
            ("AAPL", "2026-11-02", "2026-11-09"),
            ("AAPL", "2026-11-12", "2026-11-20"),
        ]

        # Subsequent request padded with closed weekend boundaries (Sun 11-01 .. Sun 11-22)
        # must be served purely from cache without extra upstream calls.
        padded = provider.fetch(["AAPL"], "20261101", "20261122")
        assert len(padded) == 15
        assert len(fetcher.calls) == 3
        assert cache.stats()["hits"] == 1

    def test_us_provider_holiday_and_trading_halt_not_refetched(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Closed days (Thanksgiving 2026-11-26 + weekends) and halted trading days
        must not be mistaken for uncached missing data."""
        monkeypatch.setattr(us_provider_mod, "_jittered_sleep", lambda: None)
        cache = ParquetCache(cache_dir=tmp_path)

        # HALT traded on Mon 2026-11-23 and Fri 2026-11-27; halted Tue 11-24 & Wed 11-25;
        # Thu 2026-11-26 is Thanksgiving, Sat/Sun 11-28..11-29 are weekend.
        halted_panel = _build_ohlcv_panel("HALT", ["2026-11-23", "2026-11-27"])
        # FAIL_TICKER misses upstream (None) -> must NOT record false empty coverage.
        fetcher = _SyntheticUSFetcher({"HALT": halted_panel})
        mgr = DataFetcherManager()
        mgr.register(fetcher)
        provider = YFinanceProvider(cache=cache, manager=mgr)

        # Pure holiday/weekend window -> zero upstream calls.
        closed_only = provider.fetch(["HALT"], "20261126", "20261126")
        assert closed_only.empty
        assert fetcher.calls == []

        first = provider.fetch(["HALT"], "20261123", "20261129")
        assert len(first) == 2
        assert fetcher.calls == [("HALT", "2026-11-23", "2026-11-27")]

        # Querying the halted sub-window [11-24, 11-26] or the full week [11-23, 11-29]
        # must hit cache with 0 new upstream calls (halted sessions inside covered range).
        halted_sub = provider.fetch(["HALT"], "20261124", "20261126")
        assert halted_sub.empty
        second = provider.fetch(["HALT"], "20261123", "20261129")
        assert len(second) == 2
        assert len(fetcher.calls) == 1

        # Upstream miss (None) must NOT poison cache as an empty covered range.
        missed = provider.fetch(["FAIL_TICKER"], "20261123", "20261127")
        assert missed.empty
        assert cache.missing_ranges(
            "FAIL_TICKER", "20261123", "20261127", market="US", price_basis="adjusted"
        ) == [("20261123", "20261127")]

        # AKShareProvider CN full-window halt (empty DataFrame returned without raising)
        # records empty range coverage so repeat calls over the halted week hit cache.
        cn_calls: list[tuple[str, str, str]] = []
        fake_ak = types.ModuleType("akshare")
        fake_ak.stock_zh_a_hist = lambda symbol, period, start_date, end_date, adjust: (  # type: ignore[attr-defined]
            cn_calls.append((symbol, start_date, end_date)) or pd.DataFrame()
        )
        monkeypatch.setitem(sys.modules, "akshare", fake_ak)
        monkeypatch.setattr("alpha_agent.data.provider._REQUEST_INTERVAL", 0.0)
        cn_provider = AKShareProvider(cache=cache)
        assert cn_provider.fetch(["600000"], "20261012", "20261016").empty
        assert cn_provider.fetch(["600000"], "20261012", "20261016").empty
        assert cn_calls == [("600000", "20261012", "20261016")]

    def test_akshare_provider_narrow_then_wide_and_holiday(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AKShareProvider (CN / XSHG, qfq) must fetch missing wings and skip CN holidays."""
        monkeypatch.setattr("alpha_agent.data.provider._REQUEST_INTERVAL", 0.0)
        cache = ParquetCache(cache_dir=tmp_path)

        # XSHG sessions in Oct 1..16, 2026: Oct 1-7 is National Day holiday, Oct 10-11 weekend.
        cn_sessions = [
            "2026-10-08",
            "2026-10-09",
            "2026-10-12",
            "2026-10-13",
            "2026-10-14",
            "2026-10-15",
            "2026-10-16",
        ]
        calls: list[tuple[str, str, str, str]] = []

        def _fake_stock_zh_a_hist(
            symbol: str,
            period: str,
            start_date: str,
            end_date: str,
            adjust: str,
        ) -> pd.DataFrame:
            calls.append((symbol, start_date, end_date, adjust))
            s_ts = pd.Timestamp(start_date)
            e_ts = pd.Timestamp(end_date)
            rows = [d for d in cn_sessions if s_ts <= pd.Timestamp(d) <= e_ts]
            if not rows:
                return pd.DataFrame()
            return pd.DataFrame(
                {
                    "日期": rows,
                    "开盘": [1800.0] * len(rows),
                    "收盘": [1810.0] * len(rows),
                    "最高": [1820.0] * len(rows),
                    "最低": [1795.0] * len(rows),
                    "成交量": [50000] * len(rows),
                    "成交额": [9e8] * len(rows),
                    "股票代码": [symbol] * len(rows),
                }
            )

        fake_ak = types.ModuleType("akshare")
        fake_ak.stock_zh_a_hist = _fake_stock_zh_a_hist  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "akshare", fake_ak)

        provider = AKShareProvider(cache=cache)

        # 1. Narrow fetch: 2026-10-12..2026-10-13 (2 sessions)
        narrow = provider.fetch(["600519"], "20261012", "20261013")
        assert len(narrow) == 2

        # 2. Wide fetch starting inside CN National Day holiday: 2026-10-01..2026-10-16.
        # Oct 1..7 are closed on XSHG, so left missing wing trims to 20261008..20261009,
        # and right missing wing trims to 20261014..20261016.
        wide = provider.fetch(["600519"], "20261001", "20261016")
        assert len(wide) == len(cn_sessions)
        assert calls == [
            ("600519", "20261012", "20261013", "qfq"),
            ("600519", "20261008", "20261009", "qfq"),
            ("600519", "20261014", "20261016", "qfq"),
        ]

        # 3. Pure holiday query (Oct 1..7) -> served without upstream call.
        holiday = provider.fetch(["600519"], "20261001", "20261007")
        assert holiday.empty
        assert len(calls) == 3

    def test_yfinance_fetcher_inclusive_end_date(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """YFinanceFetcher must pass end + 1 day to `yf.download` because Yahoo's
        `end` parameter is exclusive while the provider contract is inclusive."""
        seen: dict[str, str] = {}

        def _fake_download(ticker: str, start: str, end: str, **kwargs: object) -> pd.DataFrame:
            seen["start"] = start
            seen["end"] = end
            # Simulate Yahoo exclusive-end semantics: [start, end)
            dates = pd.bdate_range(start, pd.Timestamp(end) - timedelta(days=1))
            return pd.DataFrame(
                {
                    "Date": dates,
                    "Open": [100.0] * len(dates),
                    "High": [101.0] * len(dates),
                    "Low": [99.0] * len(dates),
                    "Close": [100.5] * len(dates),
                    "Volume": [1000] * len(dates),
                }
            ).set_index("Date")

        fake_yf = types.ModuleType("yfinance")
        fake_yf.download = _fake_download  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

        fetcher = YFinanceFetcher()
        df = fetcher.fetch_ohlcv("AAPL", "2026-11-10", "2026-11-11")
        assert seen == {"start": "2026-11-10", "end": "2026-11-12"}
        assert df is not None
        assert [d.strftime("%Y-%m-%d") for d in df.index.get_level_values("date")] == [
            "2026-11-10",
            "2026-11-11",
        ]


# ------------------------------------------------------------------
# CSI300Universe
# ------------------------------------------------------------------

class TestCSI300Universe:
    def test_has_at_least_50_codes(self) -> None:
        universe = CSI300Universe()
        assert len(universe.stock_codes) >= 50

    def test_codes_are_six_digits(self) -> None:
        universe = CSI300Universe()
        for code in universe.stock_codes:
            assert len(code) == 6
            assert code.isdigit()

    def test_name_map_matches_codes(self) -> None:
        universe = CSI300Universe()
        names = universe.name_map()
        assert set(names.keys()) == set(universe.stock_codes)

    def test_name_map_returns_copy(self) -> None:
        universe = CSI300Universe()
        m1 = universe.name_map()
        m2 = universe.name_map()
        assert m1 is not m2  # each call returns a fresh dict


# ------------------------------------------------------------------
# AKShareProvider (network-dependent)
# ------------------------------------------------------------------

@pytest.mark.slow
class TestAKShareProvider:
    """Integration test — requires network access to AKShare."""

    def test_fetch_single_stock(self) -> None:
        provider = AKShareProvider()
        df = provider.fetch(["600519"], "20250101", "20250301")

        assert not df.empty
        assert df.index.names == ["date", "stock_code"]
        for col in OHLCV_COLUMNS:
            assert col in df.columns

    def test_fetch_invalid_code_skipped(self) -> None:
        provider = AKShareProvider()
        df = provider.fetch(["XXXXXX"], "20250101", "20250301")
        assert df.empty


# ------------------------------------------------------------------
# A2: retry semantics on us_provider — fail-fast on 4xx, retry on transient
# ------------------------------------------------------------------

class TestRetrySemantics:
    """A2: the @_retry_network decorator must:
      - retry on ConnectionError / TimeoutError / requests.ChunkedEncodingError
      - NOT retry on requests.HTTPError (4xx auth/schema, 5xx server failure)
      - cap at 5 attempts and re-raise the last exception
    """

    def test_retry_does_not_fire_on_http_error(self) -> None:
        """4xx-style errors must fail-fast — burning 5 round-trips on a 401
        is the exact anti-pattern A2 was designed to avoid."""
        import requests
        from alpha_agent.data.us_provider import _retry_network

        call_count = {"n": 0}

        @_retry_network
        def _401_response() -> None:
            call_count["n"] += 1
            raise requests.exceptions.HTTPError("401 Unauthorized")

        with pytest.raises(requests.exceptions.HTTPError):
            _401_response()
        assert call_count["n"] == 1, (
            f"HTTPError must fail-fast, got {call_count['n']} attempts"
        )

    def test_retry_fires_on_connection_error_and_caps_at_5(self) -> None:
        """Transient ConnectionError keeps retrying until stop_after_attempt(5)
        is hit, then re-raises (reraise=True)."""
        import requests
        from alpha_agent.data.us_provider import _retry_network

        call_count = {"n": 0}

        @_retry_network
        def _always_unreachable() -> None:
            call_count["n"] += 1
            raise requests.exceptions.ConnectionError("connection refused")

        from unittest.mock import patch
        with patch("alpha_agent.data.us_provider.wait_random_exponential",
                   return_value=lambda *a, **kw: 0):
            with pytest.raises(requests.exceptions.ConnectionError):
                _always_unreachable()
        assert call_count["n"] == 5, (
            f"ConnectionError must retry until cap; got {call_count['n']} attempts"
        )

    def test_retry_succeeds_on_first_recovery(self) -> None:
        """A successful call after one transient failure should return cleanly."""
        import requests
        from alpha_agent.data.us_provider import _retry_network

        call_count = {"n": 0}

        @_retry_network
        def _flaky_then_ok() -> str:
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise requests.exceptions.ConnectionError("first attempt")
            return "ok"

        result = _flaky_then_ok()
        assert result == "ok"
        assert call_count["n"] == 2
