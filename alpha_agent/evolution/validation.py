"""Purged walk-forward + Deflated-Sharpe-lite (numpy only, no scipy/sklearn).

SLICE A: purged_fold_indices + deflated_sharpe_lite  -- pure math, no IO.
SLICE B: CandidateResult + evaluate_candidate        -- real DB + kernel.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from alpha_agent.evolution.candidates import ConfigDelta


# Minimum number of OOS folds required to consider the result meaningful.
# Fewer than 3 folds gives too little signal to trust any deflated Sharpe.
MIN_FOLDS = 3

# Minimum rows per fold for the kernel to compute a meaningful Sharpe
# (needs >1 clean day, but we want at least a few weeks of OOS data).
_MIN_ROWS_PER_FOLD = 15

# Forward horizon used by the IC engine (5 trading days). The embargo guard
# must be at least this large so OOS labels cannot bleed into training.
_EMBARGO = 5


def purged_fold_indices(n: int, n_folds: int, embargo: int) -> list[tuple[list[int], list[int]]]:
    """Contiguous-block walk-forward folds with a purge+embargo gap: each test
    block excludes `embargo` train days on both sides so a label that overlaps
    the test window cannot leak into training."""
    bounds = np.linspace(0, n, n_folds + 1).astype(int)
    folds = []
    for i in range(n_folds):
        lo, hi = bounds[i], bounds[i + 1] - 1
        test_idx = list(range(lo, hi + 1))
        train_idx = [t for t in range(n) if t < lo - embargo or t > hi + embargo]
        folds.append((train_idx, test_idx))
    return folds


def deflated_sharpe_lite(best_sharpe: float, sharpes: list[float], n_trials: int) -> float:
    """Discount the best observed Sharpe by the cross-trial spread times
    log(n_trials) (more trials -> more selection bias -> larger haircut). Lite
    proxy for the Deflated Sharpe Ratio."""
    arr = np.asarray(sharpes, dtype=float)
    spread = float(arr.std()) if len(arr) > 1 else 0.0
    haircut = spread * float(np.log1p(n_trials))
    return float(best_sharpe - haircut)


@dataclass(frozen=True)
class CandidateResult:
    delta: "ConfigDelta"    # from alpha_agent.evolution.candidates
    sharpes: list[float]    # OOS Sharpe per fold
    ic_oos: float           # mean OOS IC across folds
    n_folds: int


async def evaluate_candidate(pool, delta: "ConfigDelta") -> "CandidateResult | None":
    """Score `delta` via purged walk-forward OOS evaluation.

    Data source: `daily_prices` table (same table the IC engine uses for
    forward-return calculations). We query close history for all tickers,
    build a minimal _Panel in-memory, then call run_kernel on each fold.

    Delta application: config_store._CACHE is patched in-memory for the
    duration of the evaluation, then restored in a finally block. This
    approach was chosen because:
      (a) run_kernel does not accept config overrides as params; it
          delegates expression-selection to _resolve_default_expr() which
          reads _CACHE synchronously.
      (b) _CACHE is a simple module-level dict, making try/finally restore
          both safe and trivially auditable.
      (c) set_config touches the DB and journals the change; we must NOT
          write to engine_config during a proposal evaluation.

    Returns None when usable history yields fewer than MIN_FOLDS folds with
    _MIN_ROWS_PER_FOLD rows each (dormant-when-starved guard).
    """
    from alpha_agent import config_store
    from alpha_agent.core.types import FactorSpec
    from alpha_agent.factor_engine.factor_backtest import _Panel
    from alpha_agent.factor_engine.kernel import (
        KernelParams,
        run_kernel,
        spearman_ic,
    )

    # ------------------------------------------------------------------ #
    # 1. Load close history from daily_prices (reuse IC engine data source)
    # ------------------------------------------------------------------ #
    rows = await pool.fetch(
        "SELECT ticker, date, close FROM daily_prices ORDER BY date, ticker"
    )
    if not rows:
        return None

    # Pivot to (dates x tickers) close matrix
    tickers_set: list[str] = sorted({r["ticker"] for r in rows})
    dates_set: list[str] = sorted({str(r["date"]) for r in rows})
    N = len(tickers_set)
    T = len(dates_set)

    ticker_idx = {t: i for i, t in enumerate(tickers_set)}
    date_idx = {d: i for i, d in enumerate(dates_set)}

    close_arr = np.full((T, N), np.nan)
    for r in rows:
        ti = ticker_idx[r["ticker"]]
        di = date_idx[str(r["date"])]
        close_arr[di, ti] = float(r["close"])

    # Drop any columns (tickers) that have all-NaN close (never seeded)
    valid_cols = ~np.all(np.isnan(close_arr), axis=0)
    close_arr = close_arr[:, valid_cols]
    tickers_arr = [t for t, v in zip(tickers_set, valid_cols) if v]
    N = close_arr.shape[1]

    # Need at least 10 tickers for kernel to compute cross-sectional weights
    if N < 10:
        return None

    # ------------------------------------------------------------------ #
    # 2. Decide fold geometry; return None when history is too short
    # ------------------------------------------------------------------ #
    # Determine target n_folds such that each fold has _MIN_ROWS_PER_FOLD rows.
    # We try n_folds = MIN_FOLDS first; if T / MIN_FOLDS < _MIN_ROWS_PER_FOLD
    # the history is genuinely too short.
    n_folds = MIN_FOLDS
    if T // n_folds < _MIN_ROWS_PER_FOLD:
        return None

    folds = purged_fold_indices(n=T, n_folds=n_folds, embargo=_EMBARGO)

    # Check each fold has enough test rows and enough non-embargo train rows
    usable_folds = []
    for train_idx, test_idx in folds:
        if len(test_idx) >= _MIN_ROWS_PER_FOLD and len(train_idx) >= _MIN_ROWS_PER_FOLD:
            usable_folds.append((train_idx, test_idx))

    if len(usable_folds) < MIN_FOLDS:
        return None

    # ------------------------------------------------------------------ #
    # 3. Apply delta in-memory via _CACHE override (never calls set_config)
    # ------------------------------------------------------------------ #
    old_value = config_store._CACHE.get(delta.key, config_store._SENTINEL)
    config_store._CACHE[delta.key] = delta.new_value

    try:
        # ---------------------------------------------------------------- #
        # 4. Build the FactorSpec. Honors factor.mode delta via _CACHE patch
        #    above: _resolve_default_expr() reads _CACHE["factor.mode"].
        # ---------------------------------------------------------------- #
        from alpha_agent.signals.factor import SHORT_TERM_FACTOR_EXPR, LONG_TERM_FACTOR_EXPR
        from alpha_agent.config_store import get_config
        import os

        mode = get_config("factor.mode", os.environ.get("ALPHA_FACTOR_MODE", "short")).strip().lower()
        expression = LONG_TERM_FACTOR_EXPR if mode == "long" else SHORT_TERM_FACTOR_EXPR
        spec = FactorSpec(
            name="eval_candidate",
            hypothesis="Candidate evaluation spec",
            expression=expression,
            operators_used=["rank", "ts_mean", "ts_std", "subtract"],
            lookback=60,
            universe="SP500",
            justification="Automated candidate proposer OOS evaluation.",
        )

        params = KernelParams(direction="long_short", n_trials=1)

        # ---------------------------------------------------------------- #
        # 5. Score each fold: build sub-panel, call run_kernel, collect OOS
        #    Sharpe and IC using the test slice of the result.
        # ---------------------------------------------------------------- #
        fold_sharpes: list[float] = []
        fold_ics: list[float] = []

        rng = np.random.default_rng(seed=0)

        for train_idx, test_idx in usable_folds:
            # Stack train rows FIRST, then test rows, so the kernel's
            # train_ratio boundary lands exactly on the train/test partition.
            # A plain sorted index union would re-sort into calendar order and
            # for early folds (test block at the front) the kernel would train
            # on the OOS block and test on train data, corrupting the OOS
            # metrics. train_idx is ascending so within-train ordering (needed
            # for momentum lookbacks) is preserved; the embargo gap sits at the
            # train/test seam.
            sub_close = np.vstack([close_arr[train_idx, :], close_arr[test_idx, :]])
            sub_T = sub_close.shape[0]

            # Build a minimal _Panel. open/high/low/volume are synthetic
            # (same pattern as tests/test_kernel.py _synthetic_panel):
            # the kernel's pure Sharpe/IC only requires close for the factor
            # expression "rank(ts_mean(returns, 20))" etc. and for fwd-returns.
            sub_open = sub_close * (1.0 + rng.normal(0.0, 0.001, size=sub_close.shape))
            sub_high = np.maximum(sub_open, sub_close) * 1.001
            sub_low = np.minimum(sub_open, sub_close) * 0.999
            sub_vol = np.full(sub_close.shape, 1_000_000.0)
            # Dates are not calendar-validated in this evaluation context;
            # we pass synthetic date strings that satisfy _Panel's shape contract.
            sub_dates = np.array([f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}" for i in range(sub_T)])
            sub_tickers = tuple(tickers_arr)
            bench = np.cumprod(1.0 + rng.normal(0.0003, 0.005, size=sub_T)) * 100.0

            panel = _Panel(
                dates=sub_dates,
                tickers=sub_tickers,
                close=sub_close,
                open_=sub_open,
                high=sub_high,
                low=sub_low,
                volume=sub_vol,
                benchmark_close=bench,
            )

            # train rows occupy [0, n_train) of the stacked panel, test rows
            # occupy [n_train, n_train + n_test). train_ratio maps the kernel's
            # split exactly to that seam.
            n_train = len(train_idx)
            n_test = len(test_idx)
            train_ratio = float(n_train) / float(n_train + n_test)

            fold_params = KernelParams(
                direction=params.direction,
                top_pct=params.top_pct,
                bottom_pct=params.bottom_pct,
                train_ratio=train_ratio,
                n_trials=params.n_trials,
            )

            try:
                kr = run_kernel(panel, spec, fold_params)
            except Exception:
                # A single fold failure (e.g. degenerate close matrix) must not
                # abort the whole evaluation. Surface as zero metrics for this fold
                # so the deflated Sharpe reflects the degraded evidence.
                fold_sharpes.append(0.0)
                fold_ics.append(0.0)
                continue

            fold_sharpes.append(float(kr.test_metrics.sharpe))

            # OOS IC: mean Spearman IC over the test slice rows.
            test_start = kr.train_end
            ic_vals: list[float] = []
            for t in range(test_start, sub_T):
                ic = spearman_ic(kr.factor[t], kr.fwd_returns[t])
                if not np.isnan(ic):
                    ic_vals.append(ic)
            fold_ics.append(float(np.mean(ic_vals)) if ic_vals else 0.0)

    finally:
        # Restore _CACHE to its original state regardless of success or failure
        if old_value is config_store._SENTINEL:
            config_store._CACHE.pop(delta.key, None)
        else:
            config_store._CACHE[delta.key] = old_value

    if len(fold_sharpes) < MIN_FOLDS:
        return None

    return CandidateResult(
        delta=delta,
        sharpes=fold_sharpes,
        ic_oos=float(np.mean(fold_ics)),
        n_folds=len(fold_sharpes),
    )
