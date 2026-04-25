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
from typing import Literal

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

Direction = Literal["long_short", "long_only", "short_only"]
SUPPORTED_DIRECTIONS: frozenset[str] = frozenset(
    {"long_short", "long_only", "short_only"}
)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Prefer the v2 panel (SP100 + fundamentals + sector) when present. Fall back
# to the legacy v1 (37 tickers, OHLCV only) so existing backtests keep working
# during the data migration.
PARQUET_V2_PATH = _DATA_DIR / "factor_universe_sp100_v2.parquet"
PARQUET_V1_PATH = _DATA_DIR / "factor_universe_1y.parquet"
PARQUET_PATH = PARQUET_V2_PATH if PARQUET_V2_PATH.exists() else PARQUET_V1_PATH

# v2 schema additions — None on v1 panels.
# Names match the WorldQuant fundamentals catalog (see
# alpha_agent/data/wq_catalog/fields_raw.json::fundamental).
_V2_FUNDAMENTAL_FIELDS: tuple[str, ...] = (
    # initial 8 (T2)
    "revenue", "net_income_adjusted", "ebitda", "eps",
    "equity", "assets", "free_cash_flow", "gross_profit",
    # +12 expanded (T3-promoted, same yfinance pull)
    "operating_income", "cost_of_goods_sold", "ebit",
    "current_assets", "current_liabilities",
    "long_term_debt", "short_term_debt",
    "cash_and_equivalents", "retained_earnings", "goodwill",
    "operating_cash_flow", "investing_cash_flow",
)
# Multi-window dollar-volume averages computed inline at backtest time so
# they always reflect the active panel rather than a baked snapshot.
_ADV_WINDOWS: tuple[int, ...] = (5, 10, 20, 60, 120, 180)


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
    # ── v2 extensions (None when v1 panel is loaded) ──────────────────────
    cap: np.ndarray | None = None
    sector: np.ndarray | None = None     # (T, N) string array, broadcast snapshot
    industry: np.ndarray | None = None
    exchange: np.ndarray | None = None   # broadcast snapshot
    currency: np.ndarray | None = None
    fundamentals: dict[str, np.ndarray] | None = None  # field → (T, N)


@dataclass(frozen=True)
class SplitMetrics:
    sharpe: float
    total_return: float
    ic_spearman: float
    n_days: int
    max_drawdown: float = 0.0   # P4.1: largest peak-to-trough drop in this slice
    turnover: float = 0.0       # P4.1: avg daily L1 weight delta on this slice
    hit_rate: float = 0.0       # P4.1: pct of days with ic > 0


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
    direction: str                # "long_short" | "long_only" | "short_only"


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

    # ── v2 schema extras (cap / sector / industry / exchange / currency / fundamentals) ──
    cap = sector = industry = exchange = currency = None
    fundamentals: dict[str, np.ndarray] | None = None

    if "sector" in df.columns:
        # Snapshot fields broadcast to (T, N) so cross-sectional ops work.
        T = len(dates_series)
        snap = (
            df.sort_values("date")
            .drop_duplicates("ticker", keep="last")
            .set_index("ticker")
        )
        def _bcast(col: str) -> np.ndarray:
            row = snap.reindex(list(universe))[col].astype(str).to_numpy()
            return np.broadcast_to(row, (T, len(universe))).copy()
        sector = _bcast("sector")
        industry = _bcast("industry")
        if "exchange" in df.columns:
            exchange = _bcast("exchange")
        if "currency" in df.columns:
            currency = _bcast("currency")

    if "cap" in df.columns:
        cap = pivot("cap")

    if any(f in df.columns for f in _V2_FUNDAMENTAL_FIELDS):
        fundamentals = {
            f: pivot(f) for f in _V2_FUNDAMENTAL_FIELDS if f in df.columns
        }

    return _Panel(
        dates=dates_series,
        tickers=universe,
        close=pivot("close"),
        open_=pivot("open"),
        high=pivot("high"),
        low=pivot("low"),
        volume=pivot("volume"),
        benchmark_close=bench,
        cap=cap,
        sector=sector,
        industry=industry,
        exchange=exchange,
        currency=currency,
        fundamentals=fundamentals,
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


def _max_drawdown(returns: np.ndarray) -> float:
    """Largest peak-to-trough percent drop on a daily-return series."""
    if returns.size == 0:
        return 0.0
    eq = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    return float(dd.min()) if dd.size else 0.0


def _split_metrics(
    daily_returns: np.ndarray,
    factor: np.ndarray,
    fwd_returns: np.ndarray,
    weights: np.ndarray,
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
    mdd = _max_drawdown(clean)

    ic_samples: list[float] = []
    for t in range(start, end):
        if t >= factor.shape[0] or t >= fwd_returns.shape[0]:
            break
        ic = _spearman_ic(factor[t], fwd_returns[t])
        if not np.isnan(ic):
            ic_samples.append(ic)
    ic_mean = float(np.mean(ic_samples)) if ic_samples else 0.0
    hit_rate = (
        float(sum(1 for ic in ic_samples if ic > 0)) / len(ic_samples)
        if ic_samples else 0.0
    )

    # Turnover = avg L1 distance between consecutive weight rows on the slice.
    # Each rebalance moves at most 2.0 in L1 (close one position, open another),
    # so this is naturally bounded in [0, 2].
    turnover = 0.0
    sl_w = weights[start:end]
    if sl_w.shape[0] > 1:
        delta = np.abs(sl_w[1:] - sl_w[:-1])
        turnover = float(delta.sum(axis=1).mean())

    return SplitMetrics(
        sharpe=sharpe,
        total_return=total_return,
        ic_spearman=ic_mean,
        n_days=int(clean.size),
        max_drawdown=mdd,
        turnover=turnover,
        hit_rate=hit_rate,
    )


def run_factor_backtest(
    spec: FactorSpec,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    direction: Direction = "long_short",
    top_pct: float = LONG_PCT,
    bottom_pct: float = SHORT_PCT,
    transaction_cost_bps: float = 0.0,
) -> FactorBacktestResult:
    """Run a cross-sectional backtest for the given FactorSpec.

    `direction` controls portfolio construction:
      - "long_short": top `top_pct` long + bottom `bottom_pct` short, equal-weight
        within each leg. Gross exposure ~ top_pct + bottom_pct (default 0.6).
      - "long_only":  top `top_pct` equal-weight long, 0% short (gross = top_pct).
      - "short_only": bottom `bottom_pct` equal-weight short (gross = bottom_pct).

    `transaction_cost_bps` is applied as a daily drag proportional to L1 weight
    turnover: cost_bps × L1_delta / 10000. With default top/bottom 0.30 and a
    high-turnover factor at L1≈1.0, 10 bps round-trip cost shaves ~25% annual
    return — significant for any meaningful comparison.

    Raises:
        FileNotFoundError: parquet panel missing at import/first-call time
        ValueError: factor expression evaluates to wrong shape, unsupported
                    direction, or out-of-range top/bottom_pct / cost_bps.
        Any exception from `eval_factor`: propagated with original type.
    """
    if not 0.1 <= train_ratio <= 0.95:
        raise ValueError(f"train_ratio {train_ratio!r} must be in [0.1, 0.95]")
    if direction not in SUPPORTED_DIRECTIONS:
        raise ValueError(
            f"direction {direction!r} must be one of {sorted(SUPPORTED_DIRECTIONS)}"
        )
    if not 0.01 <= top_pct <= 0.5:
        raise ValueError(f"top_pct {top_pct!r} must be in [0.01, 0.5]")
    if not 0.01 <= bottom_pct <= 0.5:
        raise ValueError(f"bottom_pct {bottom_pct!r} must be in [0.01, 0.5]")
    if not 0.0 <= transaction_cost_bps <= 200.0:
        raise ValueError(f"transaction_cost_bps {transaction_cost_bps!r} must be in [0, 200]")

    panel = _load_panel()
    T, N = panel.close.shape

    # Trailing 1-day returns: returns[t] = close[t]/close[t-1] - 1. Row 0 is NaN.
    trailing_returns = np.full_like(panel.close, np.nan)
    trailing_returns[1:] = panel.close[1:] / panel.close[:-1] - 1.0

    # VWAP proxy for daily bars: typical price (H+L+C)/3. True VWAP needs
    # intraday data we don't have at this tier.
    vwap_proxy = (panel.high + panel.low + panel.close) / 3.0

    # Evaluate factor on the full panel. Operand names must match the
    # translate-prompt contract in api/routes/interactive.py.
    data: dict[str, np.ndarray] = {
        "close": panel.close,
        "open": panel.open_,
        "high": panel.high,
        "low": panel.low,
        "volume": panel.volume,
        "returns": trailing_returns,
        "vwap": vwap_proxy,
    }
    # T2 operands — present iff the v2 panel is active.
    if panel.cap is not None:
        data["cap"] = panel.cap
        # Derived multi-window dollar-volume averages and raw dollar_volume.
        # Computed inline so they always reflect the loaded panel, not a
        # baked snapshot.
        from alpha_agent.scan.vectorized import ts_mean as _ts_mean
        dollar_vol = panel.close * panel.volume
        data["dollar_volume"] = dollar_vol
        for w in _ADV_WINDOWS:
            data[f"adv{w}"] = _ts_mean(dollar_vol, w)
    if panel.sector is not None:
        data["sector"] = panel.sector
    if panel.industry is not None:
        data["industry"] = panel.industry
        data.setdefault("subindustry", panel.industry)
    if panel.exchange is not None:
        data["exchange"] = panel.exchange
    if panel.currency is not None:
        data["currency"] = panel.currency
    if panel.fundamentals:
        for fname, farr in panel.fundamentals.items():
            data[fname] = farr
    factor = np.asarray(eval_factor(spec.expression, data), dtype=np.float64)
    if factor.shape != (T, N):
        raise ValueError(
            f"factor expression produced shape {factor.shape}, expected ({T}, {N})"
        )

    # 1-day forward returns (close-to-close)
    fwd_returns = np.full_like(panel.close, np.nan)
    fwd_returns[:-1] = panel.close[1:] / panel.close[:-1] - 1.0

    # Daily portfolio weights from factor rank. The `direction` flag decides
    # which legs get populated; IC/Sharpe metrics are always computed on the
    # realized portfolio return regardless of direction.
    use_long = direction in ("long_short", "long_only")
    use_short = direction in ("long_short", "short_only")
    weights = np.zeros((T, N), dtype=np.float64)
    for t in range(T):
        row = factor[t]
        mask = ~np.isnan(row)
        valid = mask.sum()
        if valid < 10:
            continue
        ranks = np.full_like(row, np.nan)
        ranks[mask] = (row[mask].argsort().argsort() + 1.0) / valid
        if use_long:
            long_mask = ranks >= (1.0 - top_pct)
            n_long = int(long_mask.sum())
            if n_long > 0:
                weights[t, long_mask] = 1.0 / n_long
        if use_short:
            short_mask = ranks <= bottom_pct
            n_short = int(short_mask.sum())
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

    # Apply transaction cost: cost = L1 weight delta × bps / 10000.
    # Charged on the day the rebalance happens (i.e. day t+1 inherits the
    # cost of moving from weights[t-1] to weights[t]).
    if transaction_cost_bps > 0.0:
        cost_per_unit = transaction_cost_bps / 10_000.0
        for t in range(1, T):
            l1_delta = float(np.abs(weights[t] - weights[t - 1]).sum())
            if not np.isnan(daily_ret[t]):
                daily_ret[t] -= l1_delta * cost_per_unit

    # Equity curve (compound, fillna=0 for early days)
    daily_ret_clean = np.nan_to_num(daily_ret, nan=0.0)
    equity = INITIAL_CAPITAL * np.cumprod(1.0 + daily_ret_clean)

    # Benchmark: SPY buy-and-hold rescaled to INITIAL_CAPITAL
    bench = panel.benchmark_close / panel.benchmark_close[0] * INITIAL_CAPITAL

    train_end = int(T * train_ratio)
    train_m = _split_metrics(daily_ret, factor, fwd_returns, weights, start=0, end=train_end)
    test_m = _split_metrics(daily_ret, factor, fwd_returns, weights, start=train_end, end=T)

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
        direction=direction,
    )
