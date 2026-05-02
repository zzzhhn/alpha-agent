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

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from alpha_agent.core.exceptions import DataIntegrityError
from alpha_agent.core.types import FactorSpec

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
# T1.1 (v4): point-in-time fundamentals. When this parquet is present,
# `_load_panel()` overrides the legacy broadcast-snapshot fundamentals with
# per-row as-of joins keyed on filing_date. Missing → fallback to broadcast
# (with warning) for back-compat with pre-v4 deployments.
PIT_FUNDAMENTALS_PATH = _DATA_DIR / "fundamentals_pit.parquet"

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
# Multi-window dollar-volume averages live in kernel.py (single source of
# truth shared with the screener endpoint).


def _assert_trading_days(dates: np.ndarray, calendar_name: str = "XNYS") -> None:
    """Verify every date in `dates` is a session of the named exchange calendar.

    The benchmark is SPY → NYSE (XNYS). Non-NYSE panels (e.g. CSI300) should
    pass a different calendar name. Mismatch raises DataIntegrityError so a
    silently corrupt panel never reaches the IC computation, where a Saturday
    row would just NaN-out and pollute the per-day metrics.
    """
    import exchange_calendars as xcals

    cal = xcals.get_calendar(calendar_name)
    panel_idx = pd.DatetimeIndex(pd.to_datetime(dates))
    sessions = cal.sessions_in_range(panel_idx[0], panel_idx[-1])
    sessions_naive = sessions.tz_localize(None) if sessions.tz is not None else sessions
    panel_naive = panel_idx.tz_localize(None) if panel_idx.tz is not None else panel_idx
    bad = panel_naive.difference(sessions_naive)
    if len(bad) > 0:
        sample = ", ".join(str(d.date()) for d in bad[:5])
        raise DataIntegrityError(
            f"panel contains {len(bad)} non-{calendar_name} session(s) "
            f"(e.g. {sample}); regenerate parquet via "
            f"scripts/fetch_factor_universe.py or pass the correct calendar."
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
    # T1.4 (v4): IC distribution stats. Without these, an IC mean of 0.02
    # could be a clean 0.02 ± 0.01 (real signal, ICIR ~ 30) or 0.02 ± 0.15
    # (pure noise, ICIR ~ 2 but not statistically distinguishable from zero).
    ic_std: float = 0.0          # std of per-day Spearman IC samples in this slice
    icir: float = 0.0            # ic_mean / ic_std × sqrt(252), annualized info ratio of IC
    ic_t_stat: float = 0.0       # t = ic_mean / (ic_std / sqrt(n)); two-sided test that IC ≠ 0
    ic_pvalue: float = 1.0       # two-sided p-value via normal approximation (n>30 typically)
    # T2.1 (v4) — Bailey-LdP deflated Sharpe. PSR is the probability the true SR
    # beats the multiple-testing-corrected null benchmark. lucky_max_sr is what
    # one would expect the realized SR to be, just by luck, given n_trials
    # variants tried under SR=0. PSR>0.95 means SR convincingly clears the bar.
    psr: float = 0.5             # probability(true SR > lucky_max_sr); 0.5 = at the bar
    lucky_max_sr: float = 0.0    # multiple-testing-corrected benchmark, annualized SR units
    # T3.A (v4) — stationary block bootstrap 95% CIs. Wide CI = noisy realized
    # estimate; narrow CI = stable. Often more honest than a single SR / IC
    # number when the panel is short.
    sharpe_ci_low: float = 0.0
    sharpe_ci_high: float = 0.0
    ic_ci_low: float = 0.0
    ic_ci_high: float = 0.0


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
    # P4.2: calendar-month compounded strategy returns. Each entry is one
    # bucket {year, month (1-12), return} computed by prod(1+r)-1 over the
    # month's daily strategy returns (already includes transaction cost).
    monthly_returns: list[dict] | None = None
    # A7 (v3 walk-forward): per-window SplitMetrics over rolling slices of
    # `wf_window_days` length advancing `wf_step_days` at a time. Populated
    # only when mode="walk_forward"; None for static mode (default).
    walk_forward: list[dict] | None = None
    # B4 (v3): per-day {long_basket, short_basket, daily_return, daily_ic}.
    # Heavy payload (~30 entries × T days), only built when include_breakdown=True.
    daily_breakdown: list[dict] | None = None
    # T2.4 (v4): IS-OOS Sharpe degradation. Classic overfit signature when
    # the train Sharpe is high but test Sharpe collapses.
    # oos_decay = (train_sharpe - test_sharpe) / max(train_sharpe, eps)
    # overfit_flag = oos_decay > 0.5 (lost more than half the train edge OOS)
    oos_decay: float = 0.0
    overfit_flag: bool = False


# ── Panel loader (lazy, cached per-process) ─────────────────────────────────


def _load_pit_fundamentals(
    panel_dates: np.ndarray,
    universe: tuple[str, ...],
) -> dict[str, np.ndarray] | None:
    """As-of join PIT fundamentals onto the panel timeline (T1.1 of v4).

    For each `(t, n)`: value = the most recent row in `fundamentals_pit.parquet`
    where `ticker == universe[n]` and `filing_date <= panel_dates[t]`. Cells
    are NaN where no statement has been filed yet at `t`. This is the
    canonical PIT join — replaces the legacy broadcast-snapshot pattern that
    leaked future earnings ~30-45 days into the past.

    Returns None if the PIT parquet is missing — caller falls back to legacy
    broadcast (with explicit warning logged). When present, the returned dict
    has `(T, N)` arrays for every fundamental field in the parquet (typically
    20 fields ≡ `_V2_FUNDAMENTAL_FIELDS`).
    """
    if not PIT_FUNDAMENTALS_PATH.exists():
        return None

    pit = pd.read_parquet(PIT_FUNDAMENTALS_PATH)
    if pit.empty:
        return None

    panel_dates_dt = pd.to_datetime(panel_dates).values  # numpy datetime64
    T = len(panel_dates)
    N = len(universe)

    fundamental_fields = [
        c for c in pit.columns
        if c not in ("ticker", "report_period", "filing_date")
    ]
    out: dict[str, np.ndarray] = {
        f: np.full((T, N), np.nan, dtype=np.float64) for f in fundamental_fields
    }

    pit_by_ticker = dict(tuple(pit.groupby("ticker", sort=False)))

    for n, tk in enumerate(universe):
        sub = pit_by_ticker.get(tk)
        if sub is None or sub.empty:
            continue
        sub = sub.sort_values("filing_date").reset_index(drop=True)
        filing_dates = pd.to_datetime(sub["filing_date"]).values
        # searchsorted with side='right' returns the insertion index that
        # keeps `panel_dates_dt[t]` strictly before equal `filing_dates`
        # entries — but we want filings whose date IS <= panel_date to count
        # as "known". Subtract 1 to land on the last such row.
        idx = np.searchsorted(filing_dates, panel_dates_dt, side="right") - 1
        valid = idx >= 0
        if not valid.any():
            continue
        for f in fundamental_fields:
            field_vals = sub[f].to_numpy(dtype=np.float64)
            row = np.full(T, np.nan, dtype=np.float64)
            row[valid] = field_vals[idx[valid]]
            out[f][:, n] = row

    return out


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

    # Guard against silently malformed parquets: every date must be a real
    # NYSE session, otherwise per-day IC and turnover would NaN-out without
    # any visible error. This protects against weekend/holiday rows leaking
    # in from yfinance edge cases.
    _assert_trading_days(dates_series, calendar_name="XNYS")

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
        # T1.1 (v4): PIT-aligned fundamentals (filing_date as-of join) take
        # precedence over the legacy broadcast snapshot. The broadcast
        # pattern attached each quarter's value to its fiscal end date,
        # leaking ~30-45 days of unannounced earnings into past panel rows.
        pit_fund = _load_pit_fundamentals(dates_series, universe)
        if pit_fund is not None and pit_fund:
            fundamentals = pit_fund
        else:
            import warnings
            warnings.warn(
                f"PIT fundamentals not found at {PIT_FUNDAMENTALS_PATH}; "
                "falling back to legacy broadcast (LOOKAHEAD-BIASED). "
                "Run scripts/build_pit_fundamentals.py to generate.",
                stacklevel=2,
            )
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
    n_trials: int = 1,
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

    # T1.4 (v4): IC distribution + significance. Computed on the same per-day
    # IC sample list. Use ddof=1 for sample std (we have N daily ICs, not the
    # population). t-stat = mean / SE; p-value via normal CDF (panel sizes ≥ 30
    # make the t-distribution → normal approximation accurate within 1%).
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
            # Two-sided p-value via normal CDF: p = 2 * (1 - Φ(|t|))
            ic_pvalue = float(math.erfc(abs(ic_t_stat) / np.sqrt(2.0)))

    # T2.1 (v4) — Deflated Sharpe / PSR. n_trials > 1 penalizes selection
    # bias (user's "winner" is the maximum of N noisy estimates).
    from alpha_agent.scan.significance import (
        deflated_sharpe as _deflated_sharpe,
        expected_max_sharpe_annual as _exp_max_sr,
        stationary_block_bootstrap_ci as _block_bootstrap_ci,
    )
    lucky_max_sr = _exp_max_sr(n_trials=n_trials, n_samples=int(clean.size))
    psr, _ = _deflated_sharpe(
        clean, n_trials=n_trials, benchmark_sr_annual=lucky_max_sr,
    )

    # T3.A (v4) — stationary block bootstrap 95% CIs.
    # Sharpe: bootstrap the daily-return series and re-annualize on each draw.
    # IC mean: bootstrap the per-day IC sample list (already a 1D array of ICs).
    # Block length 20 ≈ one trading month — captures momentum autocorrelation.
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


Mode = Literal["static", "walk_forward"]
SUPPORTED_MODES: frozenset[str] = frozenset({"static", "walk_forward"})


def run_factor_backtest(
    spec: FactorSpec,
    train_ratio: float = DEFAULT_TRAIN_RATIO,
    direction: Direction = "long_short",
    top_pct: float = LONG_PCT,
    bottom_pct: float = SHORT_PCT,
    transaction_cost_bps: float = 0.0,
    mode: Mode = "static",
    wf_window_days: int = 60,
    wf_step_days: int = 20,
    include_breakdown: bool = False,
    purge_days: int = 0,
    embargo_days: int = 0,
    n_trials: int = 1,
    slippage_bps_per_sqrt_pct: float = 0.0,
    short_borrow_bps: float = 0.0,
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

    `mode="walk_forward"` adds a rolling per-window SplitMetrics list on top
    of the static train/test split (which is always populated for back-compat).
    Each window covers `wf_window_days` consecutive sessions, shifted by
    `wf_step_days`. On a 251-day panel with the default 60/20 settings this
    yields ~10 windows — enough to see if a factor's edge decays through time
    without overpartitioning a small sample.

    `purge_days` drops the last N rows of the train slice before scoring (and
    the last N rows of each walk-forward window). Used because train's last
    row's forward return is computed from close[t+1] which lives in the test
    set — that's a literal label-leak across the boundary. Conservative
    default 0; set 1-5 for any factor whose forward horizon overlaps the
    split.

    `embargo_days` drops the first N rows of the test slice (and the first
    N rows of each walk-forward window) so factors with rolling lookback
    don't get scored on their boundary settling period. Default 0; set
    `lookback / 2` for moderate factors.

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
    if not 0 <= purge_days <= 30:
        raise ValueError(f"purge_days {purge_days!r} must be in [0, 30]")
    if not 0 <= embargo_days <= 30:
        raise ValueError(f"embargo_days {embargo_days!r} must be in [0, 30]")
    if not 1 <= n_trials <= 1000:
        raise ValueError(f"n_trials {n_trials!r} must be in [1, 1000]")
    if not 0.0 <= slippage_bps_per_sqrt_pct <= 100.0:
        raise ValueError(
            f"slippage_bps_per_sqrt_pct {slippage_bps_per_sqrt_pct!r} must be in [0, 100]"
        )
    if not 0.0 <= short_borrow_bps <= 1000.0:
        raise ValueError(
            f"short_borrow_bps {short_borrow_bps!r} must be in [0, 1000]"
        )
    if mode not in SUPPORTED_MODES:
        raise ValueError(f"mode {mode!r} must be one of {sorted(SUPPORTED_MODES)}")
    if not 20 <= wf_window_days <= 252:
        raise ValueError(f"wf_window_days {wf_window_days!r} must be in [20, 252]")
    if not 5 <= wf_step_days <= wf_window_days:
        raise ValueError(
            f"wf_step_days {wf_step_days!r} must be in [5, wf_window_days]"
        )

    panel = _load_panel()
    T, N = panel.close.shape

    # Operand dict construction lives in kernel.build_data_dict so the screener
    # endpoint (D1) shares the exact same schema. Anything added to the
    # translate-prompt contract must be mirrored there, not here.
    from alpha_agent.factor_engine.kernel import evaluate_factor_full

    factor = evaluate_factor_full(panel, spec)

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

    # Apply transaction cost: per-name cost on the day a rebalance happens.
    # Three components:
    #   1. Flat bps × L1 weight delta — fixed per-trade fee proxy.
    #   2. T2.2 (v4) sqrt(participation) slippage — Almgren-Chriss-style.
    #      participation = |Δw_n × portfolio$| / dollar_volume[t, n]
    #      cost_n_bps = slippage_k × sqrt(participation_pct)
    #      where participation_pct = participation × 100 so the units of
    #      slippage_k are "bps per sqrt(% of ADV)". Default 0 = no slippage.
    #   3. T2.3 (v4) short-leg borrow accrual — daily on |Σ w_short|.
    flat_cost_per_unit = transaction_cost_bps / 10_000.0
    slip_k = float(slippage_bps_per_sqrt_pct)
    daily_borrow = float(short_borrow_bps) / (10_000.0 * 252.0)
    # Use $-volume from build_data_dict if available (T2 panel only).
    dollar_volume = panel.close * panel.volume  # shape (T, N)
    portfolio_value = float(INITIAL_CAPITAL)  # static — doesn't compound through cost
    for t in range(1, T):
        if np.isnan(daily_ret[t]):
            continue
        delta = weights[t] - weights[t - 1]
        l1_delta = float(np.abs(delta).sum())

        # 1. Flat bps cost
        cost = l1_delta * flat_cost_per_unit if transaction_cost_bps > 0 else 0.0

        # 2. sqrt(participation) slippage (only when both factor knobs set)
        if slip_k > 0.0:
            with np.errstate(divide="ignore", invalid="ignore"):
                dollar_traded = np.abs(delta) * portfolio_value
                # Avoid /0 — names with 0 ADV contribute zero (defensive)
                participation_pct = np.where(
                    dollar_volume[t] > 0,
                    100.0 * dollar_traded / dollar_volume[t],
                    0.0,
                )
            # cost_n_bps = slip_k × sqrt(participation_pct), per trade
            slip_bps = slip_k * np.sqrt(np.maximum(participation_pct, 0.0))
            slip_cost = float((np.abs(delta) * slip_bps / 10_000.0).sum())
            cost += slip_cost

        # 3. Short borrow accrual on the prior day's short book (paid daily)
        if short_borrow_bps > 0:
            prior_short = float(np.abs(np.minimum(weights[t - 1], 0.0)).sum())
            cost += prior_short * daily_borrow

        daily_ret[t] -= cost

    # Equity curve (compound, fillna=0 for early days)
    daily_ret_clean = np.nan_to_num(daily_ret, nan=0.0)
    equity = INITIAL_CAPITAL * np.cumprod(1.0 + daily_ret_clean)

    # Benchmark: SPY buy-and-hold rescaled to INITIAL_CAPITAL
    bench = panel.benchmark_close / panel.benchmark_close[0] * INITIAL_CAPITAL

    train_end = int(T * train_ratio)
    # T1.3 (v4): purge tail of train (its fwd_return spans into test) and
    # embargo head of test (rolling lookback in factor still re-settling
    # right after the boundary). Validate the resulting slices stay non-empty.
    train_score_end = max(1, train_end - purge_days)
    test_score_start = min(T - 1, train_end + embargo_days)
    train_m = _split_metrics(
        daily_ret, factor, fwd_returns, weights,
        start=0, end=train_score_end, n_trials=n_trials,
    )
    test_m = _split_metrics(
        daily_ret, factor, fwd_returns, weights,
        start=test_score_start, end=T, n_trials=n_trials,
    )

    equity_curve = [
        {"date": str(panel.dates[i]), "value": float(equity[i])} for i in range(T)
    ]
    benchmark_curve = [
        {"date": str(panel.dates[i]), "value": float(bench[i])} for i in range(T)
    ]

    # ── P4.2: monthly returns bucket. Skip days where daily_ret is NaN
    # (insufficient lookback rows at panel head). Order chronologically by
    # (year, month) so the heatmap renders left-to-right naturally.
    monthly_returns = _compute_monthly_returns(panel.dates, daily_ret)

    # B4 (v3): per-day long/short basket + daily return + daily IC for the
    # "what did the strategy actually trade" drill-down. Heavy payload, opt-in.
    daily_breakdown: list[dict] | None = None
    if include_breakdown:
        daily_breakdown = []
        for ti in range(T):
            row_w = weights[ti]
            longs = [
                {"ticker": panel.tickers[i], "weight": float(row_w[i])}
                for i in range(N) if row_w[i] > 0
            ]
            shorts = [
                {"ticker": panel.tickers[i], "weight": float(row_w[i])}
                for i in range(N) if row_w[i] < 0
            ]
            longs.sort(key=lambda r: -r["weight"])
            shorts.sort(key=lambda r: r["weight"])
            d_ic = _spearman_ic(factor[ti], fwd_returns[ti]) if ti < T else 0.0
            daily_breakdown.append({
                "date": str(panel.dates[ti]),
                "long_basket": longs,
                "short_basket": shorts,
                "daily_return": float(daily_ret[ti]) if not np.isnan(daily_ret[ti]) else 0.0,
                "daily_ic": float(d_ic) if not np.isnan(d_ic) else 0.0,
            })

    # A7 (v3): rolling per-window metrics. Static mode skips this so payload
    # stays small for users who don't care about IS/OOS decay analysis.
    # T1.3 (v4): each window's effective scoring slice is shrunk by embargo
    # at the head and purge at the tail to avoid the boundary leakage modes.
    walk_forward: list[dict] | None = None
    if mode == "walk_forward":
        walk_forward = []
        for start in range(0, T - wf_window_days + 1, wf_step_days):
            end = start + wf_window_days
            score_start = min(end - 1, start + embargo_days)
            score_end = max(score_start + 1, end - purge_days)
            wm = _split_metrics(
                daily_ret, factor, fwd_returns, weights,
                start=score_start, end=score_end, n_trials=n_trials,
            )
            walk_forward.append({
                "window_start": str(panel.dates[start]),
                "window_end": str(panel.dates[end - 1]),
                "sharpe": wm.sharpe,
                "total_return": wm.total_return,
                "ic_spearman": wm.ic_spearman,
                "n_days": wm.n_days,
                "max_drawdown": wm.max_drawdown,
                "turnover": wm.turnover,
                "hit_rate": wm.hit_rate,
            })

    # T2.4 (v4) — IS-OOS Sharpe drop. Conventional definition of "overfit":
    # had a real positive edge in train and lost over half of it OOS. Both
    # conditions matter — without the train > 0.5 guard, "consistently bad"
    # factors (negative train) would flag as overfit, which is the wrong
    # diagnosis for them.
    if train_m.sharpe > 0.5:
        oos_decay = float((train_m.sharpe - test_m.sharpe) / train_m.sharpe)
    else:
        oos_decay = 0.0  # no train edge to lose → no overfit verdict
    overfit_flag = bool(train_m.sharpe > 0.5 and oos_decay > 0.5)

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
        monthly_returns=monthly_returns,
        walk_forward=walk_forward,
        daily_breakdown=daily_breakdown,
        oos_decay=oos_decay,
        overfit_flag=overfit_flag,
    )


def _compute_monthly_returns(
    dates: np.ndarray, daily_ret: np.ndarray,
) -> list[dict]:
    """Bucket daily strategy returns by calendar month, compound each bucket."""
    buckets: dict[tuple[int, int], list[float]] = {}
    for i, d in enumerate(dates):
        if i >= daily_ret.shape[0] or np.isnan(daily_ret[i]):
            continue
        s = str(d)
        # Date format is "YYYY-MM-DD" from yfinance
        try:
            year = int(s[:4])
            month = int(s[5:7])
        except (ValueError, IndexError):
            continue
        buckets.setdefault((year, month), []).append(float(daily_ret[i]))

    out: list[dict] = []
    for (year, month), rets in sorted(buckets.items()):
        compounded = float(np.prod(1.0 + np.asarray(rets)) - 1.0)
        out.append({
            "year": year,
            "month": month,
            "return": compounded,
            "n_days": len(rets),
        })
    return out
