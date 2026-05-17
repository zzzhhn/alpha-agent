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
# A5 (kernel layering): the numeric pipeline lives in `kernel.py` so it can be
# unit-tested with synthetic panels and reused by /screener. We re-export the
# helpers under their old private names below for any callsite that imported
# them directly (zoo.py, screener.py, tests).
from alpha_agent.factor_engine.kernel import (
    KernelParams,
    SplitMetrics,
    run_kernel,
    sector_neutralize_factor as _sector_neutralize_factor,  # noqa: F401  # re-export consumed by api.routes.signal + api.routes.screener
    spearman_ic as _spearman_ic,
    split_metrics as _split_metrics,
)

INITIAL_CAPITAL: float = 100_000.0
LONG_PCT: float = 0.30
SHORT_PCT: float = 0.30
DEFAULT_TRAIN_RATIO: float = 0.80
BENCHMARK_TICKER: str = "SPY"  # default; alternatives are kept aside in panel.benchmark_alts
# Tickers held out of the cross-sectional universe and stored as benchmarks.
# SPY = cap-weighted SP500 (Mag-7 dominated, +75% in 3y panel).
# RSP = equal-weight SP500 (every constituent ~0.20% weight, +42% in 3y panel).
# Long-only factor strategies are far closer to RSP's regime than SPY's, so
# RSP is the more honest benchmark for any equal-weight factor basket.
BENCHMARK_TICKERS: tuple[str, ...] = ("SPY", "RSP")
CURRENCY: str = "USD"

Direction = Literal["long_short", "long_only", "short_only"]
SUPPORTED_DIRECTIONS: frozenset[str] = frozenset(
    {"long_short", "long_only", "short_only"}
)

_DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Panel auto-selection chain (highest priority first):
#   v3: Alpaca-sourced 3y SP500 panel (~556 tickers incl. delisted, D-1 fresh,
#       Compustat fundamentals via WRDS with proper RDQ filing dates) — T1.5a.
#   v2: yfinance-sourced 1y SP100 panel (~98 tickers, 16-month max lag).
#   v1: legacy 37-ticker OHLCV-only panel (no fundamentals, no sector).
PARQUET_V3_PATH = _DATA_DIR / "factor_universe_sp500_v3.parquet"
PARQUET_V2_PATH = _DATA_DIR / "factor_universe_sp100_v2.parquet"
PARQUET_V1_PATH = _DATA_DIR / "factor_universe_1y.parquet"
PARQUET_PATH = (
    PARQUET_V3_PATH if PARQUET_V3_PATH.exists()
    else PARQUET_V2_PATH if PARQUET_V2_PATH.exists()
    else PARQUET_V1_PATH
)
# T1.1 (v4): point-in-time fundamentals. When this parquet is present,
# `_load_panel()` overrides the legacy broadcast-snapshot fundamentals with
# per-row as-of joins keyed on filing_date. Missing → fallback to broadcast
# (with warning) for back-compat with pre-v4 deployments.
# v3 panel uses its own dedicated PIT parquet (Compustat-sourced).
PIT_FUNDAMENTALS_V3_PATH = _DATA_DIR / "fundamentals_pit_sp500_v3.parquet"
# Bundle C.3 (v4): Form 4 insider transactions, aggregated to ticker-day.
INSIDER_FORM4_PATH = _DATA_DIR / "insider_form4_sp500_v3.parquet"
PIT_FUNDAMENTALS_V2_PATH = _DATA_DIR / "fundamentals_pit.parquet"
PIT_FUNDAMENTALS_PATH = (
    PIT_FUNDAMENTALS_V3_PATH if PARQUET_PATH == PARQUET_V3_PATH and PIT_FUNDAMENTALS_V3_PATH.exists()
    else PIT_FUNDAMENTALS_V2_PATH
)

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
    # T1.5a (v4): Compustat shares_outstanding (cshoq) for v3 panels —
    # absent from v2 yfinance pulls, present in v3 WRDS pulls. Listed here
    # so the PIT as-of join automatically picks it up when available.
    "shares_outstanding", "total_liabilities",
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
    benchmark_close: np.ndarray   # shape (T,) — primary (SPY by default)
    # Multi-benchmark support: keys include all BENCHMARK_TICKERS that exist
    # in the loaded parquet. Default lookup (panel.benchmark_close) returns
    # SPY; run_factor_backtest can swap in RSP via benchmark_ticker arg.
    benchmark_alts: dict[str, np.ndarray] | None = None
    # ── v2 extensions (None when v1 panel is loaded) ──────────────────────
    cap: np.ndarray | None = None
    sector: np.ndarray | None = None     # (T, N) string array, broadcast snapshot
    industry: np.ndarray | None = None
    exchange: np.ndarray | None = None   # broadcast snapshot
    currency: np.ndarray | None = None
    fundamentals: dict[str, np.ndarray] | None = None  # field → (T, N)
    # Bundle C.3 (v4) — insider Form 4 alt-alpha. Dict of:
    #   "insider_net_dollars": (T, N) signed dollar net (P-S) per day
    #   "insider_n_buys":      (T, N) count of P transactions per day
    #   "insider_n_sells":     (T, N) count of S transactions per day
    # Days with no insider activity are NaN-filled; kernel exposes these
    # to factor expressions just like fundamentals.
    insider_form4: dict[str, np.ndarray] | None = None
    # T1.5b (v4): point-in-time SP500 membership mask. True iff ticker n was
    # an SP500 constituent on date t per fja05680/sp500 historical components
    # CSV. None when membership CSV is absent (caller falls back to "all
    # members", i.e. legacy survivorship-biased behavior with a warning).
    is_member: np.ndarray | None = None  # shape (T, N) bool


# SplitMetrics is now defined in alpha_agent.factor_engine.kernel and re-exported
# at the top of this module for back-compat with any direct import. See A5.


@dataclass(frozen=True)
class RegimeMetrics:
    """Bundle A.1: sub-period metrics partitioned by macro regime.

    Regime classification is on the BENCHMARK's 60-day rolling return:
        bull:     SPY 60d return > +5%
        bear:     SPY 60d return < -5%
        sideways: −5% ≤ SPY 60d return ≤ +5%

    A factor is "regime-robust" if its Sharpe / α-t are positive across all
    three regimes. A factor that only delivers in one regime is a regime bet
    masquerading as alpha — exactly what walk-forward and per-regime
    diagnostics surface.
    """
    regime: str               # "bull" | "bear" | "sideways"
    n_days: int               # days in this regime within the test slice
    sharpe: float
    ic_spearman: float
    ic_pvalue: float
    alpha_annualized: float   # OLS alpha in this regime's days only
    alpha_t_stat: float
    alpha_pvalue: float


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
    # T3.B (v4) — market α/β decomposition: regress strategy daily return on
    # benchmark (SPY). High R² + significant β = factor is mostly market exposure;
    # near-zero β + significant α = real factor signal.
    alpha_annualized: float = 0.0
    beta_market: float = 0.0
    alpha_t_stat: float = 0.0
    alpha_pvalue: float = 1.0
    r_squared: float = 0.0
    # T1.5b (v4): True iff the panel was filtered through a point-in-time
    # SP500 membership mask. Frontend KPI strip surfaces this as a small
    # "✓ SP500-as-of-date" badge so users know whether the result is
    # survivorship-corrected vs legacy lookahead.
    survivorship_corrected: bool = False
    membership_as_of: str | None = None  # "YYYY-MM-DD" of the latest CSV snapshot
    # Bundle A.1 (v4): per-regime Sharpe / IC / alpha breakdown. Surfaces
    # which sub-periods carry the factor's edge. Length is 1-3 entries
    # depending on which regimes appear in the test slice.
    regime_breakdown: list[RegimeMetrics] | None = None
    # Bundle A.2 (v4): "none" or "sector" — sector-neutral re-ranks within
    # each GICS sector, decoupling factor signal from sector beta.
    neutralize: str = "none"


# ── Panel loader (lazy, cached per-process) ─────────────────────────────────


@lru_cache(maxsize=1)
def _membership_csv_as_of() -> str | None:
    """Return the date of the latest snapshot in the membership CSV, or None
    if absent. Used to surface "✓ SP500 as of YYYY-MM-DD" in result payloads."""
    try:
        from alpha_agent.data.membership import load_membership_history
        history = load_membership_history()
        return history[-1][0].strftime("%Y-%m-%d") if history else None
    except Exception:
        return None


def _load_earnings_mask(
    panel_dates: np.ndarray,
    universe: tuple[str, ...],
    window_days: int = 1,
) -> np.ndarray | None:
    """Build a (T, N) boolean mask flagging earnings-window days (T3.C of v4).

    For each ticker n, looks up its filing_dates from `fundamentals_pit.parquet`
    and marks cells where `|panel_dates[t] - filing_date|` ≤ `window_days` as
    True. Used to zero out factor weights around earnings announcements,
    reducing PEAD (post-earnings-announcement-drift) noise that contaminates
    momentum and reversal factors.

    Returns None when `fundamentals_pit.parquet` is absent — caller treats
    that as "no mask" (back-compat: window=0 effectively).
    """
    if not PIT_FUNDAMENTALS_PATH.exists():
        return None

    pit = pd.read_parquet(PIT_FUNDAMENTALS_PATH)
    if pit.empty or "filing_date" not in pit.columns:
        return None

    panel_dt = pd.to_datetime(panel_dates).values  # (T,) datetime64[ns]
    T = len(panel_dates)
    N = len(universe)
    mask = np.zeros((T, N), dtype=bool)

    pit_by_ticker = dict(tuple(pit.groupby("ticker", sort=False)))
    window_ns = pd.Timedelta(days=window_days).asm8.astype("timedelta64[ns]")

    for n, tk in enumerate(universe):
        sub = pit_by_ticker.get(tk)
        if sub is None or sub.empty:
            continue
        filings = pd.to_datetime(sub["filing_date"]).values  # (Q,)
        for fd in filings:
            within = np.abs(panel_dt - fd) <= window_ns
            mask[within, n] = True
    return mask


def _load_insider_form4(
    panel_dates: np.ndarray,
    universe: tuple[str, ...],
) -> dict[str, np.ndarray] | None:
    """Pivot the Form 4 ticker-day aggregation parquet into 3 (T, N) arrays
    aligned to the panel. Returns None if the parquet is missing — the
    kernel's fundamental-fallback NaN-fill then keeps factor expressions
    using `insider_*` operands evaluable (just to all-NaN values).

    Schema produced by scripts/fetch_insider_form4.py:
        ticker, transaction_date, net_dollars, n_buys, n_sells

    Days with no insider activity are absent from the parquet and stay
    NaN here — calling code should treat NaN as "no signal" not zero.
    """
    if not INSIDER_FORM4_PATH.exists():
        return None
    df = pd.read_parquet(INSIDER_FORM4_PATH)
    if df.empty:
        return None

    panel_dates_str = pd.to_datetime(panel_dates).strftime("%Y-%m-%d").to_numpy()
    date_to_idx = {d: i for i, d in enumerate(panel_dates_str)}
    ticker_to_idx = {t: i for i, t in enumerate(universe)}
    T, N = len(panel_dates), len(universe)

    out = {
        "insider_net_dollars": np.full((T, N), np.nan, dtype=np.float64),
        "insider_n_buys": np.full((T, N), np.nan, dtype=np.float64),
        "insider_n_sells": np.full((T, N), np.nan, dtype=np.float64),
    }
    matched = 0
    for row in df.itertuples(index=False):
        t = date_to_idx.get(getattr(row, "transaction_date", None))
        n = ticker_to_idx.get(getattr(row, "ticker", None))
        if t is None or n is None:
            continue
        out["insider_net_dollars"][t, n] = float(getattr(row, "net_dollars", 0.0))
        out["insider_n_buys"][t, n] = float(getattr(row, "n_buys", 0))
        out["insider_n_sells"][t, n] = float(getattr(row, "n_sells", 0))
        matched += 1
    if matched == 0:
        return None
    return out


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
    # Pivot long -> wide per field, with all BENCHMARK_TICKERS held aside.
    all_tickers = sorted(df["ticker"].unique())
    if BENCHMARK_TICKER not in all_tickers:
        raise ValueError(f"primary benchmark {BENCHMARK_TICKER!r} missing from parquet")
    available_benchmarks = tuple(t for t in BENCHMARK_TICKERS if t in all_tickers)

    universe = tuple(t for t in all_tickers if t not in available_benchmarks)
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
    # Store every benchmark close-series (including primary) keyed by ticker.
    # Lets run_factor_backtest swap in RSP via benchmark_ticker arg without
    # re-pivoting the parquet.
    benchmark_alts = {
        bt: df[df["ticker"] == bt].sort_values("date")["close"].to_numpy(dtype=np.float64)
        for bt in available_benchmarks
    }

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

    # Two paths to fundamentals:
    #   (a) v2 panel: OHLCV parquet has fundamental columns AND a PIT parquet
    #       optionally exists for as-of join (with broadcast fallback).
    #   (b) v3 panel: OHLCV parquet has NO fundamental columns; the PIT
    #       parquet alone supplies them. Common case post-T1.5a.
    has_inline_funds = any(f in df.columns for f in _V2_FUNDAMENTAL_FIELDS)
    has_pit_parquet = PIT_FUNDAMENTALS_PATH.exists()
    if has_inline_funds or has_pit_parquet:
        # T1.1 (v4): PIT-aligned fundamentals (filing_date as-of join) take
        # precedence over the legacy broadcast snapshot. The broadcast
        # pattern attached each quarter's value to its fiscal end date,
        # leaking ~30-45 days of unannounced earnings into past panel rows.
        pit_fund = _load_pit_fundamentals(dates_series, universe)
        if pit_fund is not None and pit_fund:
            fundamentals = pit_fund
        elif has_inline_funds:
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

    # Bundle C.3 (v4): insider Form 4 alt-alpha. Optional — parquet is
    # generated by scripts/fetch_insider_form4.py. If absent, factor
    # expressions referencing insider_* operands get NaN-filled by the
    # kernel's fundamental-fallback path (no error, just zero signal).
    insider_form4 = _load_insider_form4(dates_series, universe)

    # T1.5b (v4): build point-in-time SP500 membership mask. Falls back to
    # None (no mask, legacy lookahead behavior) if the CSV is missing — with
    # a warning so the regression isn't silent.
    from alpha_agent.data.membership import build_is_member_mask
    is_member = build_is_member_mask(dates_series, universe)
    if is_member is None:
        import warnings
        warnings.warn(
            "SP500 membership CSV missing — backtests run without "
            "survivorship correction (LOOKAHEAD-BIASED for any ticker that "
            "joined/left SP500 inside the panel window). Refresh from "
            "https://github.com/fja05680/sp500.",
            stacklevel=2,
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
        benchmark_alts=benchmark_alts,
        cap=cap,
        sector=sector,
        industry=industry,
        exchange=exchange,
        currency=currency,
        fundamentals=fundamentals,
        insider_form4=insider_form4,
        is_member=is_member,
    )


# ── Core backtest ───────────────────────────────────────────────────────────


# `_spearman_ic`, `_max_drawdown`, `_split_metrics` now live in
# `alpha_agent.factor_engine.kernel` (A5). Re-exported under the original
# private names at the top of this module for any callsite that imported them.


Mode = Literal["static", "walk_forward"]
SUPPORTED_MODES: frozenset[str] = frozenset({"static", "walk_forward"})


Neutralize = Literal["none", "sector"]


# `_sector_neutralize_factor` now lives in kernel.py (A5). Re-exported at the
# top of this module for back-compat with any direct importer.


def _classify_regimes(
    benchmark_close: np.ndarray, lookback: int = 60, threshold: float = 0.05
) -> np.ndarray:
    """Bundle A.1: regime label per date based on benchmark trailing return.

    Returns a (T,) array of strings: "bull" | "bear" | "sideways" | "warmup".
    First `lookback` days are "warmup" (insufficient history to classify).
    """
    T = len(benchmark_close)
    regimes = np.full(T, "warmup", dtype=object)
    for t in range(lookback, T):
        ret = benchmark_close[t] / benchmark_close[t - lookback] - 1.0
        if ret > threshold:
            regimes[t] = "bull"
        elif ret < -threshold:
            regimes[t] = "bear"
        else:
            regimes[t] = "sideways"
    return regimes


def _compute_regime_metrics(
    daily_ret: np.ndarray,
    factor: np.ndarray,
    fwd_returns: np.ndarray,
    benchmark_daily_ret: np.ndarray,
    regimes: np.ndarray,
    test_slice: slice,
) -> list[RegimeMetrics]:
    """Bundle A.1: split test slice by regime, compute SR/IC/alpha per regime."""
    out: list[RegimeMetrics] = []
    test_regimes = regimes[test_slice]
    test_daily_ret = daily_ret[test_slice]
    test_fwd_returns = fwd_returns[test_slice]
    test_factor = factor[test_slice]
    test_bench = benchmark_daily_ret[test_slice]

    for regime in ("bull", "sideways", "bear"):
        mask = (test_regimes == regime)
        n = int(mask.sum())
        if n < 20:  # too few obs for stable stats
            continue

        rets = test_daily_ret[mask]
        rets = rets[~np.isnan(rets)]
        if len(rets) < 20:
            continue
        sr = float(np.mean(rets) / (np.std(rets, ddof=1) + 1e-12) * np.sqrt(252))

        # Mean Spearman IC across the days in this regime
        ic_samples = []
        for i in np.where(mask)[0]:
            ic = _spearman_ic(test_factor[i], test_fwd_returns[i])
            if not np.isnan(ic):
                ic_samples.append(ic)
        if len(ic_samples) < 10:
            continue
        ic_mean = float(np.mean(ic_samples))
        ic_std = float(np.std(ic_samples, ddof=1) + 1e-12)
        ic_t = ic_mean / (ic_std / np.sqrt(len(ic_samples)))
        ic_p = float(math.erfc(abs(ic_t) / np.sqrt(2.0)))

        # Per-regime alpha via OLS on the regime's days only
        bench_in = test_bench[mask]
        valid = ~(np.isnan(rets) | np.isnan(bench_in[:len(rets)]))
        if valid.sum() < 20:
            alpha_a = alpha_t = 0.0
            alpha_p = 1.0
        else:
            r = rets[valid]
            b = bench_in[:len(rets)][valid]
            n_obs = len(r)
            b_mean = b.mean()
            r_mean = r.mean()
            cov = ((b - b_mean) * (r - r_mean)).sum() / (n_obs - 1)
            var = ((b - b_mean) ** 2).sum() / (n_obs - 1)
            beta = cov / (var + 1e-12)
            alpha_daily = r_mean - beta * b_mean
            resid = r - alpha_daily - beta * b
            sigma2 = (resid ** 2).sum() / max(n_obs - 2, 1)
            se_alpha = float(np.sqrt(sigma2 * (1 / n_obs + b_mean ** 2 / (var * (n_obs - 1) + 1e-12))))
            alpha_t = float(alpha_daily / (se_alpha + 1e-12))
            alpha_a = float(alpha_daily * 252)
            alpha_p = float(math.erfc(abs(alpha_t) / np.sqrt(2.0)))

        out.append(RegimeMetrics(
            regime=regime, n_days=n, sharpe=sr,
            ic_spearman=ic_mean, ic_pvalue=ic_p,
            alpha_annualized=alpha_a, alpha_t_stat=alpha_t, alpha_pvalue=alpha_p,
        ))
    return out


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
    mask_earnings_window: bool = False,
    earnings_window_days: int = 1,
    neutralize: Neutralize = "none",
    benchmark_ticker: str = BENCHMARK_TICKER,
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
    if not 0 <= earnings_window_days <= 5:
        raise ValueError(
            f"earnings_window_days {earnings_window_days!r} must be in [0, 5]"
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

    # Resolve benchmark close series. Default = panel.benchmark_close (SPY);
    # alternative = panel.benchmark_alts[ticker] when caller swaps in RSP, etc.
    # Equity curve, regime classification, and α/β decomposition all use this.
    if benchmark_ticker != BENCHMARK_TICKER:
        if not panel.benchmark_alts or benchmark_ticker not in panel.benchmark_alts:
            avail = list(panel.benchmark_alts.keys()) if panel.benchmark_alts else [BENCHMARK_TICKER]
            raise ValueError(
                f"benchmark_ticker={benchmark_ticker!r} not in panel; "
                f"available: {avail}"
            )
        bench_close = panel.benchmark_alts[benchmark_ticker]
    else:
        bench_close = panel.benchmark_close

    # T3.C (v4): earnings-window mask is loaded here (IO) and passed to the
    # pure kernel. Kernel zeroes weights on masked cells without knowing where
    # the dates came from.
    earnings_mask: np.ndarray | None = None
    if mask_earnings_window:
        earnings_mask = _load_earnings_mask(
            panel.dates, panel.tickers, window_days=earnings_window_days,
        )

    # A5: pure pipeline. Everything from factor evaluation through transaction
    # cost, equity-curve compound, and train/test SplitMetrics happens here.
    # Walk-forward, regime breakdown, and α/β regression are wrapper-side
    # because they want either rolling slices (WF) or external arrays (bench).
    kernel_result = run_kernel(
        panel,
        spec,
        KernelParams(
            direction=direction,
            top_pct=top_pct,
            bottom_pct=bottom_pct,
            train_ratio=train_ratio,
            transaction_cost_bps=transaction_cost_bps,
            slippage_bps_per_sqrt_pct=slippage_bps_per_sqrt_pct,
            short_borrow_bps=short_borrow_bps,
            purge_days=purge_days,
            embargo_days=embargo_days,
            n_trials=n_trials,
            neutralize=neutralize,
        ),
        earnings_mask=earnings_mask,
    )
    factor = kernel_result.factor
    weights = kernel_result.weights
    daily_ret = kernel_result.daily_ret
    equity = kernel_result.equity
    fwd_returns = kernel_result.fwd_returns
    train_end = kernel_result.train_end
    train_m = kernel_result.train_metrics
    test_m = kernel_result.test_metrics

    # Benchmark: SPY buy-and-hold rescaled to INITIAL_CAPITAL — wrapper-side
    # because the benchmark series is independent of the factor pipeline.
    bench = bench_close / bench_close[0] * INITIAL_CAPITAL

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

    # T3.B (v4) — market α/β decomposition. Regress full-period daily strategy
    # return on SPY's daily return. Surfaces whether realized Sharpe traces to
    # excess alpha or to leveraged market exposure.
    from alpha_agent.factor_engine.risk_attribution import decompose_alpha_beta
    bench_daily = np.full_like(bench, np.nan)
    bench_daily[1:] = bench[1:] / bench[:-1] - 1.0
    market_decomp = decompose_alpha_beta(daily_ret, bench_daily)

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

    # Bundle A.1 (v4) — per-regime SR/IC/alpha breakdown. Classify each test
    # day by SPY 60d return (bull > +5%, bear < -5%, sideways otherwise),
    # then compute the same metrics restricted to each regime's days. Lets
    # users see if a +1.5 SR factor is regime-robust or just rode 2024 AI
    # bull market.
    regimes = _classify_regimes(bench_close, lookback=60, threshold=0.05)
    regime_breakdown = _compute_regime_metrics(
        daily_ret=daily_ret,
        factor=factor,
        fwd_returns=fwd_returns,
        benchmark_daily_ret=bench_daily,
        regimes=regimes,
        test_slice=slice(train_end, T),
    )

    # Bundle B (T4.1) — persist the result to the Factor DB for cross-
    # session continuity, run history, and decay alerts. Wrapped so DB
    # failures (Neon pool exhaustion, schema mismatch, etc.) NEVER break
    # the user's backtest response — they get the result, the DB just
    # silently misses the write and we log the error.
    try:
        from alpha_agent.storage import upsert_factor, record_run
        # Build per-day IC time-series for decay analysis. Computed on
        # the test slice only (the part the user sees as "future" perf).
        from alpha_agent.factor_engine.kernel import spearman_ic
        test_daily_ic: list[float] = []
        for t in range(train_end, T - 1):
            ic_t = spearman_ic(factor[t], fwd_returns[t])
            if not np.isnan(ic_t):
                test_daily_ic.append(float(ic_t))

        factor_id = upsert_factor(
            name=spec.name,
            expression=spec.expression,
            operators_used=list(spec.operators_used),
            hypothesis=getattr(spec, "hypothesis", None),
            last_run_summary={
                "direction": direction,
                "neutralize": neutralize,
                "benchmark": benchmark_ticker,
                "test_sharpe": test_m.sharpe,
                "test_ic": test_m.ic_spearman,
                "alpha_t": market_decomp.alpha_t_stat,
                "alpha_p": market_decomp.alpha_pvalue,
                "psr": test_m.psr,
                "overfit_flag": overfit_flag,
            },
        )
        record_run(
            factor_id=factor_id,
            panel_version="sp500_v3" if PARQUET_PATH == PARQUET_V3_PATH else "sp100_v2",
            direction=direction,
            neutralize=neutralize,
            benchmark_ticker=benchmark_ticker,
            top_pct=top_pct,
            bottom_pct=bottom_pct,
            transaction_cost_bps=transaction_cost_bps,
            test_sharpe=test_m.sharpe,
            test_ic=test_m.ic_spearman,
            test_psr=test_m.psr,
            alpha_annualized=market_decomp.alpha_annualized,
            alpha_t=market_decomp.alpha_t_stat,
            alpha_p=market_decomp.alpha_pvalue,
            beta=market_decomp.beta_market,
            r_squared=market_decomp.r_squared,
            overfit_flag=overfit_flag,
            daily_ic=test_daily_ic,
        )
    except Exception as exc:  # noqa: BLE001 — DB persistence is best-effort
        import logging
        logging.getLogger(__name__).warning(
            "factor DB persist failed: %s: %s", type(exc).__name__, exc,
        )

    return FactorBacktestResult(
        equity_curve=equity_curve,
        benchmark_curve=benchmark_curve,
        train_end_index=train_end,
        train_metrics=train_m,
        test_metrics=test_m,
        currency=CURRENCY,
        factor_name=spec.name,
        benchmark_ticker=benchmark_ticker,
        direction=direction,
        monthly_returns=monthly_returns,
        walk_forward=walk_forward,
        daily_breakdown=daily_breakdown,
        oos_decay=oos_decay,
        overfit_flag=overfit_flag,
        alpha_annualized=market_decomp.alpha_annualized,
        beta_market=market_decomp.beta_market,
        alpha_t_stat=market_decomp.alpha_t_stat,
        alpha_pvalue=market_decomp.alpha_pvalue,
        r_squared=market_decomp.r_squared,
        survivorship_corrected=panel.is_member is not None,
        membership_as_of=_membership_csv_as_of(),
        regime_breakdown=regime_breakdown if regime_breakdown else None,
        neutralize=neutralize,
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
