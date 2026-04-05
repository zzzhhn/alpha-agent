"""Vectorised backtest engine for alpha factor evaluation.

Consumes a factor DataFrame and price DataFrame (both MultiIndex on
(date, stock_code)) and produces an immutable :class:`BacktestResult`.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from alpha_agent.backtest.metrics import BacktestResult

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TRADING_DAYS_PER_YEAR: int = 252
QUINTILE_FRACTION: float = 0.20


# ---------------------------------------------------------------------------
# Pure helper functions (stateless, no mutation)
# ---------------------------------------------------------------------------


def _compute_forward_returns(
    close: pd.Series,
    stock_index_level: int,
    periods: tuple[int, ...],
) -> pd.DataFrame:
    """Compute forward returns for each period without mutating inputs.

    Parameters
    ----------
    close : pd.Series
        Close prices with MultiIndex (date, stock_code).
    stock_index_level : int
        Index level for stock_code grouping.
    periods : tuple[int, ...]
        Forward look-ahead periods in trading days.

    Returns
    -------
    pd.DataFrame
        Columns ``fwd_ret_{n}`` for each *n* in *periods*.
    """
    frames: dict[str, pd.Series] = {}
    for n in periods:
        shifted = close.groupby(level=stock_index_level).shift(-n)
        frames[f"fwd_ret_{n}"] = shifted / close - 1.0
    return pd.DataFrame(frames, index=close.index)


def _pearson_ic_series(
    factor: pd.Series,
    forward_ret: pd.Series,
    date_level: int,
) -> pd.Series:
    """Per-date Pearson correlation between factor and forward returns."""
    combined = pd.DataFrame({"factor": factor, "ret": forward_ret}).dropna()
    if combined.empty:
        return pd.Series(dtype=float)
    return combined.groupby(level=date_level).apply(
        lambda g: g["factor"].corr(g["ret"]),
        include_groups=False,
    )


def _spearman_ic_series(
    factor: pd.Series,
    forward_ret: pd.Series,
    date_level: int,
) -> pd.Series:
    """Per-date Spearman rank correlation between factor and forward returns."""
    combined = pd.DataFrame({"factor": factor, "ret": forward_ret}).dropna()
    if combined.empty:
        return pd.Series(dtype=float)
    return combined.groupby(level=date_level).apply(
        lambda g: g["factor"].rank().corr(g["ret"].rank()),
        include_groups=False,
    )


def _ic_stats(ic_series: pd.Series) -> tuple[float, float, float]:
    """Return (mean, std, ir) from an IC series, handling edge cases."""
    clean = ic_series.dropna()
    if len(clean) < 2:
        return (0.0, 0.0, 0.0)
    mean = float(clean.mean())
    std = float(clean.std(ddof=1))
    ir = mean / std if std > 1e-12 else 0.0
    return (mean, std, ir)


def _long_short_returns(
    factor: pd.Series,
    forward_ret_1: pd.Series,
    date_level: int,
) -> pd.Series:
    """Compute daily long-short quintile portfolio returns.

    For each date, stocks are sorted by factor value.  The top quintile
    (highest 20 %) forms the long leg; the bottom quintile forms the short
    leg.  Both legs are equal-weighted.  The daily return is
    ``mean(long) - mean(short)``.
    """
    combined = pd.DataFrame({"factor": factor, "ret": forward_ret_1}).dropna()
    if combined.empty:
        return pd.Series(dtype=float)

    def _daily_ls(group: pd.DataFrame) -> float:
        n = len(group)
        if n < 5:
            return np.nan
        k = max(1, int(math.ceil(n * QUINTILE_FRACTION)))
        sorted_group = group.sort_values("factor")
        short_ret = sorted_group["ret"].iloc[:k].mean()
        long_ret = sorted_group["ret"].iloc[-k:].mean()
        return float(long_ret - short_ret)

    return combined.groupby(level=date_level).apply(
        _daily_ls, include_groups=False,
    )


def _max_drawdown(returns: pd.Series) -> float:
    """Maximum drawdown of a daily return series.  Returns value <= 0."""
    cumulative = (1.0 + returns).cumprod()
    running_max = cumulative.cummax()
    drawdowns = cumulative / running_max - 1.0
    mdd = float(drawdowns.min())
    return min(mdd, 0.0)


def _average_turnover(
    factor: pd.Series,
    date_level: int,
    stock_level: int,
) -> float:
    """Average daily factor-rank turnover.

    For each stock, compute ``|rank[t] - rank[t-1]|``, then average
    across stocks per date, then average over all dates.
    """
    combined = pd.DataFrame({"factor": factor})
    if combined.empty:
        return 0.0

    # Per-date cross-sectional rank (0-1 normalised)
    ranks = combined.groupby(level=date_level)["factor"].rank(pct=True)

    # Absolute change in rank from one date to the next, per stock
    rank_diff = ranks.groupby(level=stock_level).diff().abs()

    # Mean across stocks per date, then grand mean
    daily_turnover = rank_diff.groupby(level=date_level).mean()
    result = float(daily_turnover.mean())
    return result if not np.isnan(result) else 0.0


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------


class BacktestEngine:
    """Stateless, vectorised alpha-factor backtest engine.

    Parameters
    ----------
    forward_periods : tuple[int, ...]
        Forward look-ahead periods used for alpha-decay analysis.
        Default ``(1, 2, 3, 5, 10, 20)``.
    """

    def __init__(
        self,
        forward_periods: tuple[int, ...] = (1, 2, 3, 5, 10, 20),
    ) -> None:
        self._forward_periods = forward_periods

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        factor_values: pd.DataFrame,
        price_data: pd.DataFrame,
    ) -> BacktestResult:
        """Run the full backtest and return an immutable result.

        Parameters
        ----------
        factor_values : pd.DataFrame
            MultiIndex ``(date, stock_code)`` with a single column
            ``"factor"``.
        price_data : pd.DataFrame
            MultiIndex ``(date, stock_code)`` with at least column
            ``"close"``.

        Returns
        -------
        BacktestResult
            Frozen dataclass with all evaluation metrics.

        Raises
        ------
        ValueError
            If required columns are missing or data is empty.
        """
        self._validate_inputs(factor_values, price_data)

        # Work on copies so we never mutate caller data
        factor_ser: pd.Series = factor_values["factor"].copy()
        close_ser: pd.Series = price_data["close"].copy()

        # Determine index level positions
        date_level = 0
        stock_level = 1

        # --- Forward returns ---
        fwd_df = _compute_forward_returns(
            close_ser, stock_index_level=stock_level, periods=self._forward_periods,
        )

        # --- IC (1-day forward) ---
        fwd_1_col = f"fwd_ret_{self._forward_periods[0]}"
        pearson_ic = _pearson_ic_series(factor_ser, fwd_df[fwd_1_col], date_level)
        ic_mean, ic_std, icir = _ic_stats(pearson_ic)

        # --- Rank IC (1-day forward) ---
        spearman_ic = _spearman_ic_series(factor_ser, fwd_df[fwd_1_col], date_level)
        rank_ic_mean, rank_ic_std, rank_icir = _ic_stats(spearman_ic)

        # --- Alpha decay ---
        alpha_decay = self._compute_alpha_decay(factor_ser, fwd_df, date_level)

        # --- Long-short portfolio ---
        ls_returns = _long_short_returns(
            factor_ser, fwd_df[fwd_1_col], date_level,
        ).dropna()

        sharpe, annual_ret, mdd = self._portfolio_stats(ls_returns)

        # --- Turnover ---
        turnover = _average_turnover(factor_ser, date_level, stock_level)

        return BacktestResult(
            ic_mean=ic_mean,
            ic_std=ic_std,
            icir=icir,
            rank_ic_mean=rank_ic_mean,
            rank_icir=rank_icir,
            sharpe_ratio=sharpe,
            annual_return=annual_ret,
            max_drawdown=mdd,
            turnover=turnover,
            alpha_decay=alpha_decay,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_inputs(
        factor_values: pd.DataFrame,
        price_data: pd.DataFrame,
    ) -> None:
        if "factor" not in factor_values.columns:
            raise ValueError("factor_values must contain a 'factor' column")
        if "close" not in price_data.columns:
            raise ValueError("price_data must contain a 'close' column")
        if factor_values.empty or price_data.empty:
            raise ValueError("Input DataFrames must not be empty")
        if not isinstance(factor_values.index, pd.MultiIndex):
            raise ValueError("factor_values must have a MultiIndex (date, stock_code)")
        if not isinstance(price_data.index, pd.MultiIndex):
            raise ValueError("price_data must have a MultiIndex (date, stock_code)")

    def _compute_alpha_decay(
        self,
        factor: pd.Series,
        fwd_df: pd.DataFrame,
        date_level: int,
    ) -> tuple[float, ...]:
        decay_values: list[float] = []
        for n in self._forward_periods:
            col = f"fwd_ret_{n}"
            ic_series = _pearson_ic_series(factor, fwd_df[col], date_level)
            mean_ic = float(ic_series.dropna().mean()) if len(ic_series.dropna()) > 0 else 0.0
            decay_values.append(mean_ic)
        return tuple(decay_values)

    @staticmethod
    def _portfolio_stats(ls_returns: pd.Series) -> tuple[float, float, float]:
        """Compute Sharpe, annual return, and max drawdown."""
        if ls_returns.empty or len(ls_returns) < 2:
            return (0.0, 0.0, 0.0)

        mean_daily = float(ls_returns.mean())
        std_daily = float(ls_returns.std(ddof=1))

        sharpe = (
            mean_daily / std_daily * math.sqrt(TRADING_DAYS_PER_YEAR)
            if std_daily > 1e-12
            else 0.0
        )
        annual_ret = mean_daily * TRADING_DAYS_PER_YEAR
        mdd = _max_drawdown(ls_returns)

        return (sharpe, annual_ret, mdd)
