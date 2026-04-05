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
