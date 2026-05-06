"""Pure-function evaluation kernel reused by backtest + screener.

Why this lives separately from `factor_backtest.py`:
  * `factor_backtest.py` mixes panel I/O, parquet caching, and result
    serialization with the actual numeric pipeline. Anything that wants to
    evaluate a factor cross-sectionally (e.g. /screener — D1 in v3) had to
    drag the whole equity-curve machinery along.
  * Pure functions here take an already-loaded `_Panel`, never touch disk,
    and return raw NumPy arrays. They're cheap to unit test and trivially
    reusable.

Public surface:
  build_data_dict(panel)       -> {operand_name: (T, N) array} for eval_factor
  evaluate_factor_full(...)    -> full (T, N) factor values
  evaluate_cross_section(...)  -> {ticker: score} at a chosen row
  spearman_ic / window_ic      -> NaN-safe rank-correlation helpers
  split_metrics(...)           -> SplitMetrics over a date slice
  sector_neutralize_factor(...) -> per-date sector demean
  run_kernel(panel, spec, params, earnings_mask=None) -> KernelResult
    The full pure backtest pipeline. `run_factor_backtest` is now a thin
    wrapper that does panel I/O, walk-forward iteration, α/β regression,
    regime breakdown, and DB persist on top of this kernel result.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np

from alpha_agent.scan.vectorized import evaluate as eval_factor
from alpha_agent.scan.vectorized import ts_mean as _ts_mean

if TYPE_CHECKING:
    from alpha_agent.core.types import FactorSpec
    from alpha_agent.factor_engine.factor_backtest import _Panel

# Multi-window dollar-volume averages computed inline at evaluation time so
# they always reflect the active panel rather than a baked snapshot. Mirror
# of factor_backtest._ADV_WINDOWS (kept in sync deliberately — see also
# `feedback_smoke_panel_must_mirror_ast_whitelist.md`).
_ADV_WINDOWS: tuple[int, ...] = (5, 10, 20, 60, 120, 180)


def build_data_dict(panel: "_Panel") -> dict[str, np.ndarray]:
    """Construct the operand → array dict that `eval_factor` consumes.

    Mirrors the v2 panel schema. Keys present here MUST be a superset of
    `core.factor_ast._ALLOWED_OPERANDS` (otherwise translate would AST-pass
    but evaluate-fail). Re-runs cheap; no caching.
    """
    # Trailing 1-day returns: returns[t] = close[t]/close[t-1] - 1. Row 0 is NaN.
    trailing_returns = np.full_like(panel.close, np.nan)
    trailing_returns[1:] = panel.close[1:] / panel.close[:-1] - 1.0

    # VWAP proxy for daily bars: typical price (H+L+C)/3. True VWAP needs
    # intraday data we don't have at this tier.
    vwap_proxy = (panel.high + panel.low + panel.close) / 3.0

    data: dict[str, np.ndarray] = {
        "close": panel.close,
        "open": panel.open_,
        "high": panel.high,
        "low": panel.low,
        "volume": panel.volume,
        "returns": trailing_returns,
        "vwap": vwap_proxy,
    }
    if panel.cap is not None:
        data["cap"] = panel.cap
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
    # Bundle C.3 (v4): expose insider Form 4 operands the same way as
    # fundamentals. None means parquet missing → handled by NaN-fill below.
    if getattr(panel, "insider_form4", None):
        for fname, farr in panel.insider_form4.items():
            data[fname] = farr

    # T1.5a (v4) compat: AST whitelist (`_ALLOWED_OPERANDS`) lists ~22
    # fundamental fields, but a given panel may carry only a subset (e.g. v3
    # SP500 panel from Compustat has no quarterly cash-flow because fundq
    # only stores YTD). Backfill missing fundamentals with NaN arrays so
    # factor expressions still parse and evaluate — they just produce NaN
    # factor values, which surface as zero positions / zero PnL downstream.
    # Better than KeyError at eval time: user sees "factor produced nothing"
    # rather than a stack trace.
    from alpha_agent.core.factor_ast import _ALLOWED_OPERANDS
    _METADATA_OPERANDS = {
        "close", "open", "high", "low", "volume", "returns", "vwap",
        "cap", "sector", "industry", "subindustry", "exchange", "currency",
        "dollar_volume", "adv5", "adv10", "adv20", "adv60", "adv120", "adv180",
    }
    fundamental_operands = _ALLOWED_OPERANDS - _METADATA_OPERANDS
    nan_shape = panel.close.shape
    for op in fundamental_operands:
        if op not in data:
            data[op] = np.full(nan_shape, np.nan, dtype=np.float64)

    return data


def evaluate_factor_full(panel: "_Panel", spec: "FactorSpec") -> np.ndarray:
    """Run a FactorSpec against the panel and return the (T, N) factor values.

    T1.5b (v4): if the panel carries an `is_member` mask, non-member cells in
    the final factor array are NaN'd out so they cannot enter the long/short
    basket and cannot contaminate cross-sectional IC. The mask is applied
    AFTER operator evaluation — per-ticker time-series ops (ts_mean, ts_std,
    etc.) keep using full price history, but the trading decision only sees
    cells where the ticker was an actual SP500 constituent.

    Caveat: cross-sectional ops inside the expression (rank, group_neutralize)
    still see all 98 tickers when computing ranks. For the SP100 panel this
    distorts ranks by ~4% (4 movers out of 98); for full SP500 with delisted
    tickers this matters more and would require row-by-row re-ranking.

    Raises:
        ValueError: factor expression evaluates to an unexpected shape.
        Any exception raised by `eval_factor`: propagated with original type
        (FactorSpecValidationError, KeyError for unknown operand, etc.).
    """
    T, N = panel.close.shape
    data = build_data_dict(panel)
    factor = np.asarray(eval_factor(spec.expression, data), dtype=np.float64)
    if factor.shape != (T, N):
        raise ValueError(
            f"factor expression produced shape {factor.shape}, expected ({T}, {N})"
        )
    if panel.is_member is not None:
        factor = np.where(panel.is_member, factor, np.nan)
    return factor


def spearman_ic(factor_row: np.ndarray, fwd_ret_row: np.ndarray) -> float:
    """Single-day cross-sectional Spearman IC. NaN-safe.

    Returns 0.0 when fewer than 3 valid observations, or the rank-vector
    has zero variance. The result lives in [-1, 1].
    """
    mask = ~(np.isnan(factor_row) | np.isnan(fwd_ret_row))
    if int(mask.sum()) < 3:
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


def window_ic(
    factor: np.ndarray,
    fwd_returns: np.ndarray,
    start: int,
    end: int,
) -> float:
    """Mean Spearman IC over rows [start, end). Skips NaN-only rows.

    `factor` and `fwd_returns` are (T, N) aligned arrays. Used by the
    screener's ic-weighted combiner to estimate each factor's recent
    informativeness.
    """
    samples: list[float] = []
    T = factor.shape[0]
    end = min(end, T, fwd_returns.shape[0])
    for t in range(max(0, start), end):
        ic = spearman_ic(factor[t], fwd_returns[t])
        if not np.isnan(ic):
            samples.append(ic)
    return float(np.mean(samples)) if samples else 0.0


def evaluate_cross_section(
    panel: "_Panel",
    spec: "FactorSpec",
    as_of_index: int = -1,
) -> dict[str, float]:
    """Return {ticker: score} for the chosen row of the panel.

    Used by /screener (D1) to rank tickers by a single factor at a single
    point in time. NaN scores are dropped so downstream z-score / rank
    aggregation only sees populated entries.

    Args:
        panel: loaded panel object.
        spec:  validated FactorSpec.
        as_of_index: row to read. Defaults to -1 (most recent).
                     Negative indexing supported.

    Raises:
        IndexError: as_of_index out of range.
    """
    factor = evaluate_factor_full(panel, spec)
    T, N = factor.shape
    # Normalize negative index for clearer error messages
    idx = as_of_index if as_of_index >= 0 else T + as_of_index
    if not 0 <= idx < T:
        raise IndexError(
            f"as_of_index {as_of_index} out of range for panel of length {T}"
        )
    row = factor[idx]
    return {
        panel.tickers[i]: float(row[i])
        for i in range(N)
        if not np.isnan(row[i])
    }


# ── SplitMetrics + supporting helpers (moved from factor_backtest, A5) ──


@dataclass(frozen=True)
class SplitMetrics:
    sharpe: float
    total_return: float
    ic_spearman: float
    n_days: int
    max_drawdown: float = 0.0
    turnover: float = 0.0
    hit_rate: float = 0.0
    ic_std: float = 0.0
    icir: float = 0.0
    ic_t_stat: float = 0.0
    ic_pvalue: float = 1.0
    psr: float = 0.5
    lucky_max_sr: float = 0.0
    sharpe_ci_low: float = 0.0
    sharpe_ci_high: float = 0.0
    ic_ci_low: float = 0.0
    ic_ci_high: float = 0.0


def max_drawdown(returns: np.ndarray) -> float:
    """Largest peak-to-trough percent drop on a daily-return series."""
    if returns.size == 0:
        return 0.0
    eq = np.cumprod(1.0 + returns)
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / peak
    return float(dd.min()) if dd.size else 0.0


def split_metrics(
    daily_returns: np.ndarray,
    factor: np.ndarray,
    fwd_returns: np.ndarray,
    weights: np.ndarray,
    start: int,
    end: int,
    n_trials: int = 1,
) -> SplitMetrics:
    """SplitMetrics over rows [start, end). Pure function — no IO.

    Computes annualized Sharpe, total return, mean Spearman IC, max drawdown,
    turnover, hit rate, IC distribution stats, deflated Sharpe / PSR, and
    stationary block-bootstrap CIs for both Sharpe and IC mean.
    """
    slice_ret = daily_returns[start:end]
    clean = slice_ret[~np.isnan(slice_ret)]
    if clean.size < 2:
        return SplitMetrics(sharpe=0.0, total_return=0.0, ic_spearman=0.0, n_days=int(clean.size))

    total_return = float(np.prod(1.0 + clean) - 1.0)
    mean = float(clean.mean())
    std = float(clean.std(ddof=1))
    sharpe = float(mean / std * np.sqrt(252)) if std > 0 else 0.0
    mdd = max_drawdown(clean)

    ic_samples: list[float] = []
    for t in range(start, end):
        if t >= factor.shape[0] or t >= fwd_returns.shape[0]:
            break
        ic = spearman_ic(factor[t], fwd_returns[t])
        if not np.isnan(ic):
            ic_samples.append(ic)
    ic_mean = float(np.mean(ic_samples)) if ic_samples else 0.0
    hit_rate = (
        float(sum(1 for ic in ic_samples if ic > 0)) / len(ic_samples)
        if ic_samples else 0.0
    )

    ic_std = 0.0
    icir = 0.0
    ic_t_stat = 0.0
    ic_pvalue = 1.0
    if len(ic_samples) >= 2:
        ic_arr = np.asarray(ic_samples, dtype=np.float64)
        ic_std = float(ic_arr.std(ddof=1))
        if ic_std > 1e-12:
            icir = float(ic_mean / ic_std * np.sqrt(252.0))
            ic_t_stat = float(ic_mean / (ic_std / np.sqrt(len(ic_arr))))
            ic_pvalue = float(math.erfc(abs(ic_t_stat) / np.sqrt(2.0)))

    from alpha_agent.scan.significance import (
        deflated_sharpe as _deflated_sharpe,
        expected_max_sharpe_annual as _exp_max_sr,
        stationary_block_bootstrap_ci as _block_bootstrap_ci,
    )
    lucky_max_sr = _exp_max_sr(n_trials=n_trials, n_samples=int(clean.size))
    psr, _ = _deflated_sharpe(
        clean, n_trials=n_trials, benchmark_sr_annual=lucky_max_sr,
    )

    def _annualized_sharpe(x: np.ndarray) -> float:
        sd = float(x.std(ddof=1))
        return float(x.mean() / sd * np.sqrt(252.0)) if sd > 0 else 0.0

    sharpe_ci_low, sharpe_ci_high = _block_bootstrap_ci(
        clean, _annualized_sharpe, block_len=20, n_resamples=1000,
    )
    if ic_samples:
        ic_ci_low, ic_ci_high = _block_bootstrap_ci(
            np.asarray(ic_samples, dtype=np.float64),
            lambda x: float(x.mean()),
            block_len=20, n_resamples=1000,
        )
    else:
        ic_ci_low, ic_ci_high = 0.0, 0.0

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
        ic_std=ic_std,
        icir=icir,
        ic_t_stat=ic_t_stat,
        ic_pvalue=ic_pvalue,
        psr=psr,
        lucky_max_sr=lucky_max_sr,
        sharpe_ci_low=float(sharpe_ci_low) if not np.isnan(sharpe_ci_low) else 0.0,
        sharpe_ci_high=float(sharpe_ci_high) if not np.isnan(sharpe_ci_high) else 0.0,
        ic_ci_low=float(ic_ci_low) if not np.isnan(ic_ci_low) else 0.0,
        ic_ci_high=float(ic_ci_high) if not np.isnan(ic_ci_high) else 0.0,
    )


def sector_neutralize_factor(
    factor: np.ndarray, sector: np.ndarray
) -> np.ndarray:
    """Subtract per-sector cross-sectional mean at each date.

    After neutralization, each ticker's value is its factor exposure RELATIVE
    to its sector peers. Subsequent global rank then picks the strongest
    relative-to-sector tickers across the universe — the resulting portfolio
    has by-construction near-zero net exposure to any single sector.
    """
    out = factor.copy()
    T = factor.shape[0]
    for t in range(T):
        valid = ~np.isnan(factor[t])
        if not valid.any():
            continue
        sec_row = sector[t]
        for sec in np.unique(sec_row[valid]):
            if sec in ("Unknown", "", "nan"):
                continue
            sec_mask = valid & (sec_row == sec)
            if sec_mask.sum() < 2:
                continue
            mean = float(np.nanmean(factor[t, sec_mask]))
            out[t, sec_mask] = factor[t, sec_mask] - mean
    return out


# ── A5-Lite: pure backtest kernel ──


_KernelDirection = Literal["long_short", "long_only", "short_only"]
_KernelNeutralize = Literal["none", "sector"]
# Match factor_backtest.INITIAL_CAPITAL — kept as a private kernel constant
# so the pure-function module stays free of imports back into its caller.
_KERNEL_INITIAL_CAPITAL = 100_000.0


@dataclass(frozen=True)
class KernelParams:
    """Parameters for the pure backtest pipeline.

    Wrapper-side concerns (walk-forward, regime breakdown, α/β decomposition,
    DB persist, response-payload serialization) are NOT here — they live
    in `factor_backtest.run_factor_backtest`. Only the numeric per-day
    pipeline knobs go in.
    """
    direction: _KernelDirection = "long_short"
    top_pct: float = 0.30
    bottom_pct: float = 0.30
    train_ratio: float = 0.8
    transaction_cost_bps: float = 0.0
    slippage_bps_per_sqrt_pct: float = 0.0
    short_borrow_bps: float = 0.0
    purge_days: int = 0
    embargo_days: int = 0
    n_trials: int = 1
    neutralize: _KernelNeutralize = "none"


@dataclass(frozen=True)
class KernelResult:
    """Numeric output of the pure backtest pipeline.

    Wrapper composes `equity_curve` / `monthly_returns` / `walk_forward` /
    `α/β` / `regime_breakdown` / DB persist on top of this. Each array is
    aligned to `panel.dates` (length T).
    """
    factor: np.ndarray         # (T, N) post-neutralization, post-membership-mask
    weights: np.ndarray        # (T, N) portfolio weights (post earnings mask)
    daily_ret: np.ndarray      # (T,) net-of-cost strategy returns (NaN early days)
    equity: np.ndarray         # (T,) cumulative compound starting at INITIAL_CAPITAL
    fwd_returns: np.ndarray    # (T, N) close-to-close 1-day forward returns
    train_end: int             # row index where train slice ends
    train_metrics: SplitMetrics
    test_metrics: SplitMetrics


def run_kernel(
    panel: "_Panel",
    spec: "FactorSpec",
    params: KernelParams,
    earnings_mask: np.ndarray | None = None,
) -> KernelResult:
    """Pure backtest pipeline: factor → weights → daily ret → equity → split metrics.

    No disk IO. `panel` is already loaded; `earnings_mask`, if provided, is a
    pre-computed (T, N) bool array (True = zero-out weight that day) that the
    caller built from `_load_earnings_mask`. Walk-forward windows, α/β, regime
    classification, and DB persist all live in the wrapper — they consume
    `KernelResult.daily_ret`, `factor`, `fwd_returns`, `weights`, `train_end`.

    Numerical output is byte-equal to the pre-A5 in-line implementation in
    `run_factor_backtest`: code blocks were moved here verbatim, only the
    private helper names (`_split_metrics`, `_sector_neutralize_factor`,
    `_spearman_ic`) were swapped for the public kernel exports.
    """
    T, N = panel.close.shape

    factor = evaluate_factor_full(panel, spec)

    if params.neutralize == "sector":
        if panel.sector is not None:
            factor = sector_neutralize_factor(factor, panel.sector)
        else:
            import warnings
            warnings.warn(
                "neutralize='sector' requested but panel has no sector data "
                "(legacy v1 panel?); falling back to none.",
                stacklevel=2,
            )

    fwd_returns = np.full_like(panel.close, np.nan)
    fwd_returns[:-1] = panel.close[1:] / panel.close[:-1] - 1.0

    use_long = params.direction in ("long_short", "long_only")
    use_short = params.direction in ("long_short", "short_only")
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
            long_mask = ranks >= (1.0 - params.top_pct)
            n_long = int(long_mask.sum())
            if n_long > 0:
                weights[t, long_mask] = 1.0 / n_long
        if use_short:
            short_mask = ranks <= params.bottom_pct
            n_short = int(short_mask.sum())
            if n_short > 0:
                weights[t, short_mask] = -1.0 / n_short

    if earnings_mask is not None:
        weights[earnings_mask] = 0.0

    daily_ret = np.full(T, np.nan)
    for t in range(T - 1):
        row_w = weights[t]
        row_r = fwd_returns[t]
        mask = ~np.isnan(row_r)
        if not mask.any():
            continue
        daily_ret[t + 1] = float((row_w[mask] * row_r[mask]).sum())

    flat_cost_per_unit = params.transaction_cost_bps / 10_000.0
    slip_k = float(params.slippage_bps_per_sqrt_pct)
    daily_borrow = float(params.short_borrow_bps) / (10_000.0 * 252.0)
    dollar_volume = panel.close * panel.volume
    portfolio_value = float(_KERNEL_INITIAL_CAPITAL)
    for t in range(1, T):
        if np.isnan(daily_ret[t]):
            continue
        delta = weights[t] - weights[t - 1]
        l1_delta = float(np.abs(delta).sum())

        cost = l1_delta * flat_cost_per_unit if params.transaction_cost_bps > 0 else 0.0

        if slip_k > 0.0:
            with np.errstate(divide="ignore", invalid="ignore"):
                dollar_traded = np.abs(delta) * portfolio_value
                participation_pct = np.where(
                    dollar_volume[t] > 0,
                    100.0 * dollar_traded / dollar_volume[t],
                    0.0,
                )
            slip_bps = slip_k * np.sqrt(np.maximum(participation_pct, 0.0))
            slip_cost = float((np.abs(delta) * slip_bps / 10_000.0).sum())
            cost += slip_cost

        if params.short_borrow_bps > 0:
            prior_short = float(np.abs(np.minimum(weights[t - 1], 0.0)).sum())
            cost += prior_short * daily_borrow

        daily_ret[t] -= cost

    daily_ret_clean = np.nan_to_num(daily_ret, nan=0.0)
    equity = _KERNEL_INITIAL_CAPITAL * np.cumprod(1.0 + daily_ret_clean)

    train_end = int(T * params.train_ratio)
    train_score_end = max(1, train_end - params.purge_days)
    test_score_start = min(T - 1, train_end + params.embargo_days)
    train_m = split_metrics(
        daily_ret, factor, fwd_returns, weights,
        start=0, end=train_score_end, n_trials=params.n_trials,
    )
    test_m = split_metrics(
        daily_ret, factor, fwd_returns, weights,
        start=test_score_start, end=T, n_trials=params.n_trials,
    )

    return KernelResult(
        factor=factor,
        weights=weights,
        daily_ret=daily_ret,
        equity=equity,
        fwd_returns=fwd_returns,
        train_end=train_end,
        train_metrics=train_m,
        test_metrics=test_m,
    )
