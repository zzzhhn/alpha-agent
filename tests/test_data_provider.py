"""Tests for the data layer: cache, universe, and provider."""

from __future__ import annotations

import pandas as pd
import pytest

from alpha_agent.data.cache import ParquetCache
from alpha_agent.data.provider import AKShareProvider, OHLCV_COLUMNS
from alpha_agent.data.universe import CSI300Universe


# ------------------------------------------------------------------
# ParquetCache
# ------------------------------------------------------------------

class TestParquetCache:
    """Round-trip write/read through ParquetCache."""

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

    def test_roundtrip(self, tmp_path: object) -> None:
        cache = ParquetCache(cache_dir=tmp_path)  # type: ignore[arg-type]
        original = self._sample_df()

        cache.put("600519", original)
        result = cache.get("600519", "20250101", "20250131")

        assert result is not None
        pd.testing.assert_frame_equal(result, original)

    def test_get_returns_none_when_missing(self, tmp_path: object) -> None:
        cache = ParquetCache(cache_dir=tmp_path)  # type: ignore[arg-type]
        assert cache.get("999999", "20250101", "20250131") is None

    def test_date_slicing(self, tmp_path: object) -> None:
        cache = ParquetCache(cache_dir=tmp_path)  # type: ignore[arg-type]
        original = self._sample_df()
        cache.put("600519", original)

        # Request only the first day
        result = cache.get("600519", "20250102", "20250102")
        assert result is not None
        assert len(result) == 1

    def test_put_does_not_mutate_input(self, tmp_path: object) -> None:
        cache = ParquetCache(cache_dir=tmp_path)  # type: ignore[arg-type]
        original = self._sample_df()
        original_copy = original.copy()

        cache.put("600519", original)
        pd.testing.assert_frame_equal(original, original_copy)


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

        # We don't want to wait through 5 exponential backoff sleeps in the test
        # (would take 30+ seconds). Monkey-patch tenacity's wait to be instant.
        from unittest.mock import patch
        with patch("alpha_agent.data.us_provider.wait_random_exponential",
                   return_value=lambda *a, **kw: 0):
            # The decorator captured wait at definition time, so just call
            # and accept the wait. Accept up to ~30s (4 retries × ~max-cap).
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

        # Same wait-bypass concern; accept the small wait
        result = _flaky_then_ok()
        assert result == "ok"
        assert call_count["n"] == 2
