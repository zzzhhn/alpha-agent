"""Tests for the backtest engine and metrics module.

Covers:
- Perfect-foresight factor (IC ~ 1.0)
- Random factor (IC ~ 0.0)
- BacktestResult field sanity checks
- Alpha decay monotonicity for a good factor
- Max drawdown bounds
- Input validation errors
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from alpha_agent.backtest.engine import BacktestEngine
from alpha_agent.backtest.metrics import BacktestResult

# ---------------------------------------------------------------------------
# Fixtures — synthetic data generators
# ---------------------------------------------------------------------------

NUM_STOCKS = 10
NUM_DATES = 100
STOCK_CODES = [f"SZ{str(i).zfill(6)}" for i in range(NUM_STOCKS)]


def _make_dates(n: int = NUM_DATES) -> pd.DatetimeIndex:
    return pd.bdate_range("2024-01-01", periods=n, freq="B")


def _make_price_data(
    dates: pd.DatetimeIndex | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Generate synthetic close prices via geometric Brownian motion."""
    rng = np.random.default_rng(seed)
    if dates is None:
        dates = _make_dates()

    rows: list[tuple] = []
    for stock in STOCK_CODES:
        price = 100.0
        for dt in dates:
            rows.append((dt, stock, price))
            price *= 1 + rng.normal(0.0005, 0.02)

    idx = pd.MultiIndex.from_tuples(
        [(r[0], r[1]) for r in rows], names=["date", "stock_code"],
    )
    return pd.DataFrame({"close": [r[2] for r in rows]}, index=idx)


def _make_perfect_factor(price_data: pd.DataFrame, lag: int = 1) -> pd.DataFrame:
    """Factor = actual forward return (perfect foresight)."""
    close = price_data["close"]
    fwd = close.groupby(level="stock_code").shift(-lag) / close - 1.0
    factor_df = pd.DataFrame({"factor": fwd}, index=price_data.index)
    return factor_df.dropna()


def _make_random_factor(
    price_data: pd.DataFrame,
    seed: int = 123,
) -> pd.DataFrame:
    """Factor = pure noise, no predictive power."""
    rng = np.random.default_rng(seed)
    values = rng.standard_normal(len(price_data))
    return pd.DataFrame(
        {"factor": values},
        index=price_data.index,
    )


# ---------------------------------------------------------------------------
# Fixtures via pytest
# ---------------------------------------------------------------------------


@pytest.fixture()
def price_data() -> pd.DataFrame:
    return _make_price_data()


@pytest.fixture()
def perfect_factor(price_data: pd.DataFrame) -> pd.DataFrame:
    return _make_perfect_factor(price_data)


@pytest.fixture()
def random_factor(price_data: pd.DataFrame) -> pd.DataFrame:
    return _make_random_factor(price_data)


@pytest.fixture()
def engine() -> BacktestEngine:
    return BacktestEngine(forward_periods=(1, 2, 3, 5, 10, 20))


# ---------------------------------------------------------------------------
# Tests — Perfect-foresight factor
# ---------------------------------------------------------------------------


class TestPerfectFactor:
    """A perfect-foresight factor should yield IC very close to 1.0."""

    def test_ic_near_one(
        self, engine: BacktestEngine, perfect_factor: pd.DataFrame, price_data: pd.DataFrame,
    ) -> None:
        result = engine.run(perfect_factor, price_data)
        assert result.ic_mean > 0.90, f"Expected IC > 0.90, got {result.ic_mean}"

    def test_rank_ic_near_one(
        self, engine: BacktestEngine, perfect_factor: pd.DataFrame, price_data: pd.DataFrame,
    ) -> None:
        result = engine.run(perfect_factor, price_data)
        assert result.rank_ic_mean > 0.85, f"Expected Rank IC > 0.85, got {result.rank_ic_mean}"

    def test_positive_sharpe(
        self, engine: BacktestEngine, perfect_factor: pd.DataFrame, price_data: pd.DataFrame,
    ) -> None:
        result = engine.run(perfect_factor, price_data)
        assert result.sharpe_ratio > 0, f"Expected positive Sharpe, got {result.sharpe_ratio}"

    def test_alpha_decay_monotonic(
        self, engine: BacktestEngine, perfect_factor: pd.DataFrame, price_data: pd.DataFrame,
    ) -> None:
        """For a perfect 1-day factor, IC should decay as the horizon grows."""
        result = engine.run(perfect_factor, price_data)
        decay = result.alpha_decay
        # First element (lag=1) should be the highest
        assert decay[0] > decay[-1], (
            f"Alpha decay not decreasing: first={decay[0]:.4f}, last={decay[-1]:.4f}"
        )
        # Check pairwise non-increasing trend (allow small violations from noise)
        violations = sum(
            1 for i in range(len(decay) - 1) if decay[i] < decay[i + 1] - 0.05
        )
        assert violations <= 1, f"Too many decay violations: {decay}"


# ---------------------------------------------------------------------------
# Tests — Random factor
# ---------------------------------------------------------------------------


class TestRandomFactor:
    """A random factor should have IC near zero with no significant Sharpe."""

    def test_ic_near_zero(
        self, engine: BacktestEngine, random_factor: pd.DataFrame, price_data: pd.DataFrame,
    ) -> None:
        result = engine.run(random_factor, price_data)
        assert abs(result.ic_mean) < 0.15, f"Expected |IC| < 0.15, got {result.ic_mean}"

    def test_rank_ic_near_zero(
        self, engine: BacktestEngine, random_factor: pd.DataFrame, price_data: pd.DataFrame,
    ) -> None:
        result = engine.run(random_factor, price_data)
        assert abs(result.rank_ic_mean) < 0.15, (
            f"Expected |Rank IC| < 0.15, got {result.rank_ic_mean}"
        )

    def test_sharpe_near_zero(
        self, engine: BacktestEngine, random_factor: pd.DataFrame, price_data: pd.DataFrame,
    ) -> None:
        result = engine.run(random_factor, price_data)
        assert abs(result.sharpe_ratio) < 3.0, (
            f"Expected |Sharpe| < 3.0, got {result.sharpe_ratio}"
        )


# ---------------------------------------------------------------------------
# Tests — BacktestResult sanity
# ---------------------------------------------------------------------------


class TestBacktestResultFields:
    """Verify BacktestResult fields have sensible values and types."""

    def test_max_drawdown_bounds(
        self, engine: BacktestEngine, perfect_factor: pd.DataFrame, price_data: pd.DataFrame,
    ) -> None:
        result = engine.run(perfect_factor, price_data)
        assert -1.0 <= result.max_drawdown <= 0.0, (
            f"Max drawdown out of range: {result.max_drawdown}"
        )

    def test_max_drawdown_random(
        self, engine: BacktestEngine, random_factor: pd.DataFrame, price_data: pd.DataFrame,
    ) -> None:
        result = engine.run(random_factor, price_data)
        assert -1.0 <= result.max_drawdown <= 0.0, (
            f"Max drawdown out of range: {result.max_drawdown}"
        )

    def test_alpha_decay_length(
        self, engine: BacktestEngine, perfect_factor: pd.DataFrame, price_data: pd.DataFrame,
    ) -> None:
        result = engine.run(perfect_factor, price_data)
        assert len(result.alpha_decay) == 6, (
            f"Expected 6 decay values, got {len(result.alpha_decay)}"
        )

    def test_turnover_non_negative(
        self, engine: BacktestEngine, perfect_factor: pd.DataFrame, price_data: pd.DataFrame,
    ) -> None:
        result = engine.run(perfect_factor, price_data)
        assert result.turnover >= 0.0, f"Turnover should be >= 0, got {result.turnover}"

    def test_frozen_dataclass(
        self, engine: BacktestEngine, perfect_factor: pd.DataFrame, price_data: pd.DataFrame,
    ) -> None:
        result = engine.run(perfect_factor, price_data)
        with pytest.raises(AttributeError):
            result.ic_mean = 999.0  # type: ignore[misc]

    def test_summary_dict(
        self, engine: BacktestEngine, perfect_factor: pd.DataFrame, price_data: pd.DataFrame,
    ) -> None:
        result = engine.run(perfect_factor, price_data)
        d = result.summary_dict()
        assert set(d.keys()) == {
            "ic_mean", "ic_std", "icir", "rank_ic_mean", "rank_icir",
            "sharpe_ratio", "annual_return", "max_drawdown", "turnover", "alpha_decay",
        }

    def test_str_representation(
        self, engine: BacktestEngine, perfect_factor: pd.DataFrame, price_data: pd.DataFrame,
    ) -> None:
        result = engine.run(perfect_factor, price_data)
        s = str(result)
        assert "IC" in s
        assert "Sharpe" in s


# ---------------------------------------------------------------------------
# Tests — Input validation
# ---------------------------------------------------------------------------


class TestInputValidation:
    """Engine.run should raise ValueError on bad inputs."""

    def test_missing_factor_column(self, engine: BacktestEngine, price_data: pd.DataFrame) -> None:
        bad_factor = pd.DataFrame(
            {"wrong_name": [1.0]},
            index=pd.MultiIndex.from_tuples([("2024-01-01", "SZ000000")]),
        )
        with pytest.raises(ValueError, match="factor"):
            engine.run(bad_factor, price_data)

    def test_missing_close_column(self, engine: BacktestEngine, price_data: pd.DataFrame) -> None:
        factor = pd.DataFrame(
            {"factor": [1.0]},
            index=pd.MultiIndex.from_tuples([("2024-01-01", "SZ000000")]),
        )
        bad_price = price_data.rename(columns={"close": "adj_close"})
        with pytest.raises(ValueError, match="close"):
            engine.run(factor, bad_price)

    def test_empty_dataframe(self, engine: BacktestEngine) -> None:
        empty = pd.DataFrame(
            {"factor": pd.Series(dtype=float)},
            index=pd.MultiIndex.from_tuples([], names=["date", "stock_code"]),
        )
        price = pd.DataFrame(
            {"close": pd.Series(dtype=float)},
            index=pd.MultiIndex.from_tuples([], names=["date", "stock_code"]),
        )
        with pytest.raises(ValueError, match="empty"):
            engine.run(empty, price)

    def test_non_multiindex(self, engine: BacktestEngine) -> None:
        factor = pd.DataFrame({"factor": [1.0, 2.0]}, index=[0, 1])
        price = pd.DataFrame({"close": [100.0, 101.0]}, index=[0, 1])
        with pytest.raises(ValueError, match="MultiIndex"):
            engine.run(factor, price)
