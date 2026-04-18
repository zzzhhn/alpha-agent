"""Factor long-short backtest engine for interactive UI.

Given a validated FactorSpec, evaluates the factor on a pre-cached 37-ticker
US equity panel (1y daily OHLCV, committed as parquet), runs a cross-sectional
long-short strategy, and reports train/test metrics alongside an SPY benchmark.

Design:
- Universe is **fixed to the 37-ticker pre-cached set**, regardless of
  `spec.universe`. This is deliberate: on Vercel serverless we cannot
  reach yfinance inside a request timeout, so the panel is built at
  deploy-time (see `scripts/fetch_factor_universe.py`).
- Portfolio: top 30% long / bottom 30% short, equal-weighted, daily rebalance.
- Train/test split: index-based, 80/20 by default. Returns `train_end_index`
  so the frontend can draw the divider without re-computing.
- Benchmark: SPY buy-and-hold, rescaled to the same starting capital.

The engine re-uses `alpha_agent.scan.vectorized.evaluate` (safe AST walker)
so every operator it accepts is the same set the smoke test accepts.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from alpha_agent.core.types import FactorSpec
from alpha_agent.scan.vectorized import evaluate as eval_factor

INITIAL_CAPITAL: float = 100_000.0
LONG_PCT: float = 0.30
SHORT_PCT: float = 0.30
DEFAULT_TRAIN_RATIO: float = 0.80
BENCHMARK_TICKER: str = "SPY"
CURRENCY: str = "USD"

PARQUET_PATH = (
    Path(__file__).resolve().parent.parent / "data" / "factor_universe_1y.parquet"
)


@dataclass(frozen=True)
class _Panel:
    dates: np.ndarray          # shape (T,), strings "YYYY-MM-DD"
    tickers: tuple[str, ...]   # length N (universe only, no benchmark)
    close: np.ndarray          # shape (T, N)
    open_: np.ndarray
    high: np.ndarray
    low: np.ndarray
    volume: np.ndarray
    benchmark_close: np.ndarray   # shape (T,)


@dataclass(frozen=True)
class SplitMetrics:
    sharpe: float
    total_return: float
    ic_spearman: float
    n_days: int


@dataclass(frozen=True)
class FactorBacktestResult:
    equity_curve: list[dict]      # [{"date", "value"}]
    benchmark_curve: list[dict]
    train_end_index: int
    train_metrics: SplitMetrics
    test_metrics: SplitMetrics
    currency: str
    factor_name: str
    benchmark_ticker: str


# ── Panel loader (lazy, cached per-process) ─────────────────────────────────


@lru_cache(maxsize=1)
def _load_panel() -> _Panel:
    if not PARQUET_PATH.exists():
        raise FileNotFoundError(
            f"factor universe parquet missing at {PARQUET_PATH}; "
            f"run scripts/fetch_factor_universe.py to generate"
        )
    df = pd.read_parquet(PARQUET_PATH)
    # Pivot long -> wide per field, with SPY held aside
    all_tickers = sorted(df["ticker"].unique())
    if BENCHMARK_TICKER not in all_tickers:
        raise ValueError(f"benchmark {BENCHMARK_TICKER!r} missing from parquet")

    universe = tuple(t for t in all_tickers if t != BENCHMARK_TICKER)
    dates_series = (
        df[df["ticker"] == BENCHMARK_TICKER].sort_values("date")["date"].to_numpy()
    )

    def pivot(field: str) -> np.ndarray:
        wide = (
            df.pivot(index="date", columns="ticker", values=field)
            .sort_index()
            .reindex(columns=list(universe))
        )
        return wide.to_numpy(dtype=np.float64)

    bench = (
        df[df["ticker"] == BENCHMARK_TICKER]
        .sort_values("date")["close"]
        .to_numpy(dtype=np.float64)
    )

    return _Panel(
        dates=dates_series,
        tickers=universe,
        close=pivot("close"),
        open_=pivot("open"),
        high=pivot("high"),
        low=pivot("low"),
        volume=pivot("volume"),
        benchmark_close=bench,
    )


# ── Core backtest ───────────────────────────────────────────────────────────


def _spearman_ic(factor_row: np.ndarray, fwd_ret_row: np.ndarray) -> float:
    """Single-day cross-sectional Spearman IC (NaN-safe)."""
    mask = ~(np.isnan(factor_row) | np.isnan(fwd_ret_row))
    if mask.sum() < 3:
        return 0.0
    f = factor_row[mask]
    r = fwd_ret_row[mask]
    f_rank = f.argsort().argsort().astype(np.float64)
    r_rank = r.argsort().argsort().astype(np.float64)
    f_centered = f_rank - f_rank.mean()
    r_centered = r_rank - r_rank.mean()
    denom = float(np.sqrt((f_centered**2).sum() * (r_centered**2).sum()))
    if denom == 0.0:
        return 0.0
    return float((f_centered * r_centered).sum() / denom)


def _split_metrics(
    daily_returns: np.ndarray,
    factor: np.ndarray,
    fwd_returns: np.ndarray,
    start: int,
    end: int,
) -> SplitMetrics:
    slice_ret = daily_returns[start:end]
    # Drop NaN days (early lookback window, no-signal days)
    clean = slice_ret[~np.isnan(slice_ret)]
    if clean.size < 2:
        return SplitMetrics(sharpe=0.0, total_return=0.0, ic_spearman=0.0, n_days=int(clean.size))

    total_return = float(np.prod(1.0 + clean) - 1.0)
    mean = float(clean.mean())
    std = float(clean.std(ddof=1))
    sharpe = float(mean / std * np.sqrt(252)) if std > 0 else 0.0

    ic_samples: list[float] = []
    for t in range(start, end):
        if t >= factor.shape[0] or t >= fwd_returns.shape[0]:
            break
        ic = _spearman_ic(factor[t], fwd_returns[t])
        if not np.isnan(ic):
            ic_samples.append(ic)
    ic_mean = float(np.mean(ic_samples)) if ic_samples else 0.0

    return SplitMetrics(
        sharpe=sharpe, total_return=total_return, ic_spearman=ic_mean, n_days=int(clean.size)
    )


def run_factor_backtest(
    spec: FactorSpec,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
) -> FactorBacktestResult:
    """Run a cross-sectional long-short backtest for the given FactorSpec.

    Raises:
        FileNotFoundError: parquet panel missing at import/first-call time
        ValueError: factor expression evaluates to wrong shape or all-NaN
        Any exception from `eval_factor`: propagated with original type
    """
    if not 0.1 <= train_ratio <= 0.95:
        raise ValueError(f"train_ratio {train_ratio!r} must be in [0.1, 0.95]")

    panel = _load_panel()
    T, N = panel.close.shape

    # Evaluate factor on the full panel
    data = {
        "close": panel.close,
        "open": panel.open_,
        "high": panel.high,
        "low": panel.low,
        "volume": panel.volume,
    }
    factor = np.asarray(eval_factor(spec.expression, data), dtype=np.float64)
    if factor.shape != (T, N):
        raise ValueError(
            f"factor expression produced shape {factor.shape}, expected ({T}, {N})"
        )

    # 1-day forward returns (close-to-close)
    fwd_returns = np.full_like(panel.close, np.nan)
    fwd_returns[:-1] = panel.close[1:] / panel.close[:-1] - 1.0

    # Daily long-short weights from factor rank
    weights = np.zeros((T, N), dtype=np.float64)
    for t in range(T):
        row = factor[t]
        mask = ~np.isnan(row)
        valid = mask.sum()
        if valid < 10:
            continue
        ranks = np.full_like(row, np.nan)
        ranks[mask] = (row[mask].argsort().argsort() + 1.0) / valid
        long_mask = ranks >= (1.0 - LONG_PCT)
        short_mask = ranks <= SHORT_PCT
        n_long = int(long_mask.sum())
        n_short = int(short_mask.sum())
        if n_long > 0:
            weights[t, long_mask] = 1.0 / n_long
        if n_short > 0:
            weights[t, short_mask] = -1.0 / n_short

    # Portfolio daily return = weight[t-1] dot fwd_return[t-1] (i.e. realized at t)
    # fwd_returns[t] is close[t]→close[t+1], so strategy return at t+1 = sum(weights[t] * fwd_returns[t])
    daily_ret = np.full(T, np.nan)
    for t in range(T - 1):
        row_w = weights[t]
        row_r = fwd_returns[t]
        mask = ~np.isnan(row_r)
        if not mask.any():
            continue
        daily_ret[t + 1] = float((row_w[mask] * row_r[mask]).sum())

    # Equity curve (compound, fillna=0 for early days)
    daily_ret_clean = np.nan_to_num(daily_ret, nan=0.0)
    equity = INITIAL_CAPITAL * np.cumprod(1.0 + daily_ret_clean)

    # Benchmark: SPY buy-and-hold rescaled to INITIAL_CAPITAL
    bench = panel.benchmark_close / panel.benchmark_close[0] * INITIAL_CAPITAL

    train_end = int(T * train_ratio)
    train_m = _split_metrics(daily_ret, factor, fwd_returns, start=0, end=train_end)
    test_m = _split_metrics(daily_ret, factor, fwd_returns, start=train_end, end=T)

    equity_curve = [
        {"date": str(panel.dates[i]), "value": float(equity[i])} for i in range(T)
    ]
    benchmark_curve = [
        {"date": str(panel.dates[i]), "value": float(bench[i])} for i in range(T)
    ]

    return FactorBacktestResult(
        equity_curve=equity_curve,
        benchmark_curve=benchmark_curve,
        train_end_index=train_end,
        train_metrics=train_m,
        test_metrics=test_m,
        currency=CURRENCY,
        factor_name=spec.name,
        benchmark_ticker=BENCHMARK_TICKER,
    )
