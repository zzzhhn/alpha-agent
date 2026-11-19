"""10-day smoke test for a validated FactorSpec.

Purpose: before a freshly-translated FactorSpec reaches the real backtest
(weeks of OHLCV), prove it is numerically executable and produces a non-trivial
signal on synthetic data. Catches shape bugs, divide-by-zero, and broken
operator composition in under 200ms.

Design (REFACTOR_PLAN.md §3.1 step 3):
  - Synthetic panel: N=20 tickers, T = lookback + 11 days of GBM returns
  - Evaluate the factor over the full panel
  - Compute per-day cross-sectional Spearman IC vs 1-day forward return
  - Average the last 10 days' IC -> SmokeResult.ic_spearman
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from alpha_agent.core.statistics import spearman_corr
from alpha_agent.factor_engine.portfolio import quantile_weights
from alpha_agent.scan.vectorized import evaluate


@dataclass(frozen=True)
class SmokeResult:
    rows_valid: int
    ic_spearman: float
    runtime_ms: float
    # Cross-sectional std of the evaluated factor on the IC tail window. A
    # near-zero value means the expression collapsed to a (near-)constant
    # (e.g. multiply(0, x), or a self-cancelling combination the AST guard
    # didn't structurally catch). Surfaced so the API can flag degenerate
    # factors before they reach Zoo / backtest.
    factor_std: float = 0.0
    # Estimated per-period rebalance turnover (L1 weight change of a top/bottom
    # quantile long-short book, averaged over days) on the synthetic panel. A
    # LEVEL factor (value/quality rank) churns slowly (<~0.5); a CHANGE factor
    # like ts_delta(rank(X), 1) churns its whole book (>~1.0) and is destroyed
    # by transaction costs. Synthetic fundamentals are per-ticker constants so
    # this understates real turnover, but it cleanly separates the two classes —
    # surfaced so the API can warn before the user spends a real backtest.
    turnover: float = 0.0
    # Perturbation-robustness score in [-1, 1] (AlphaEval dimension 3): the mean
    # Spearman rank correlation between the clean factor ranking and the ranking
    # after a small multiplicative noise jitter on the input operands (Gaussian +
    # Student-t). ~1.0 = the ranking is stable under noise (genuine signal);
    # toward 0 = the factor is dominated by noise / curve-fit to exact numbers and
    # will not hold out-of-sample. Surfaced so the API can flag fragile factors.
    robustness: float = 0.0
    # Temporal-stability score in [-1, 1] (AlphaEval dimension 2): the mean
    # adjacent-day Spearman rank autocorrelation of the factor over the IC-tail
    # window. ~1.0 = the cross-sectional ranking is preserved day to day (stable,
    # low-churn); ~0 = it reshuffles each day; negative = day-over-day reversal.
    # The full-cross-section temporal-stability measure (turnover only sees the
    # top/bottom quantile book); the project's principled stand-in for AlphaEval's
    # Relative Rank Entropy. Costs nothing extra — ranks the clean factor only.
    rank_stability: float = 0.0


def _synthetic_panel(lookback: int, n_tickers: int, seed: int) -> dict[str, np.ndarray]:
    """Synthetic panel populating ALL operands the AST validator accepts.

    Smoke only verifies syntactic + shape correctness (non-all-NaN factor on
    a (T, N) array), so the values themselves don't need to be realistic.
    What matters is that every key in core/factor_ast._ALLOWED_OPERANDS
    has a (T, N) array under it — otherwise an LLM-generated expression
    using a T2 fundamental (e.g. `operating_income`) crashes at
    evaluator's `data[node.id]` lookup with KeyError, surfaced to the
    user as "HTTP 500: Smoke test crashed".
    """
    rng = np.random.default_rng(seed)
    T = lookback + 11

    # ── Core OHLCV (geometric Brownian motion) ──────────────────────
    daily_ret = rng.normal(0.0, 0.02, size=(T, n_tickers))
    close = 100.0 * np.exp(np.cumsum(daily_ret, axis=0))
    high = close * (1.0 + np.abs(rng.normal(0, 0.01, size=(T, n_tickers))))
    low = close * (1.0 - np.abs(rng.normal(0, 0.01, size=(T, n_tickers))))
    open_ = close * (1.0 + rng.normal(0, 0.005, size=(T, n_tickers)))
    volume = rng.lognormal(10.0, 0.5, size=(T, n_tickers))
    returns = np.vstack(
        [np.full((1, n_tickers), np.nan), np.diff(np.log(close), axis=0)]
    )
    vwap = (high + low + close) / 3.0

    data: dict[str, np.ndarray] = {
        "close": close, "open": open_, "high": high, "low": low,
        "volume": volume, "returns": returns, "vwap": vwap,
    }

    # ── Price/volume metadata (broadcast snapshots) ─────────────────
    cap_per_ticker = rng.lognormal(24.0, 1.5, size=(n_tickers,))   # ~$10B-$1T
    data["cap"] = np.broadcast_to(cap_per_ticker, (T, n_tickers)).copy()
    dollar_vol = close * volume
    data["dollar_volume"] = dollar_vol
    # Multi-window ADV — start with raw dollar_volume; smoke doesn't need
    # accurate rolling means, just non-NaN columns the LLM can reference.
    for window in (5, 10, 20, 60, 120, 180):
        data[f"adv{window}"] = dollar_vol.copy()

    # ── Categorical (broadcast string labels) ───────────────────────
    SECTORS = ["Tech", "Healthcare", "Financial", "Industrials", "Energy"]
    INDUSTRIES = ["Software", "Pharma", "Banking", "Aerospace", "Oil&Gas"]
    EXCHANGES = ["NMS", "NYQ"]
    sector_row = np.array([SECTORS[i % len(SECTORS)] for i in range(n_tickers)])
    industry_row = np.array([INDUSTRIES[i % len(INDUSTRIES)] for i in range(n_tickers)])
    exchange_row = np.array([EXCHANGES[i % len(EXCHANGES)] for i in range(n_tickers)])
    currency_row = np.full(n_tickers, "USD")
    data["sector"] = np.broadcast_to(sector_row, (T, n_tickers)).copy()
    data["industry"] = np.broadcast_to(industry_row, (T, n_tickers)).copy()
    data["subindustry"] = data["industry"]
    data["exchange"] = np.broadcast_to(exchange_row, (T, n_tickers)).copy()
    data["currency"] = np.broadcast_to(currency_row, (T, n_tickers)).copy()

    # ── Fundamentals (per-ticker constants, broadcast across T) ─────
    # Random but stable per ticker — quarterly fundamentals don't move
    # day-to-day, and smoke only needs cross-sectional variation.
    def _fund(scale: float, low: float | None = None) -> np.ndarray:
        sigma = abs(scale) * 0.5
        per_ticker = rng.normal(scale, sigma, size=(n_tickers,))
        if low is not None:
            per_ticker = np.maximum(per_ticker, low)
        return np.broadcast_to(per_ticker, (T, n_tickers)).copy()

    data["revenue"] = _fund(1e10, 1e8)
    data["net_income_adjusted"] = _fund(1e9)
    data["ebitda"] = _fund(2e9)
    data["eps"] = _fund(5.0, 0.1)
    data["gross_profit"] = _fund(4e9, 1e8)
    data["operating_income"] = _fund(2e9)
    data["cost_of_goods_sold"] = _fund(5e9, 1e8)
    data["ebit"] = _fund(2e9)
    data["equity"] = _fund(2e10, 1e8)
    data["assets"] = _fund(5e10, 1e9)
    data["current_assets"] = _fund(1e10, 1e8)
    data["current_liabilities"] = _fund(8e9, 1e8)
    data["long_term_debt"] = _fund(1e10)
    data["short_term_debt"] = _fund(2e9)
    data["cash_and_equivalents"] = _fund(5e9, 1e8)
    data["retained_earnings"] = _fund(1e10)
    data["goodwill"] = _fund(2e9)
    data["free_cash_flow"] = _fund(3e9)
    data["operating_cash_flow"] = _fund(4e9)
    data["investing_cash_flow"] = _fund(-2e9)

    # ── T1.5a (v4) Compustat additions ──────────────────────────────
    # shares_outstanding lets value factors express market cap dynamically as
    # multiply(close, shares_outstanding); with close ~100 this yields ~$200B
    # caps that vary per ticker, so E/P = ni / (close * shares) is non-constant.
    # total_liabilities feeds debt ratios without summing long/short-term debt.
    data["shares_outstanding"] = _fund(2e9, 1e7)
    data["total_liabilities"] = _fund(3e10, 1e8)

    # ── Bundle C.3 (v4) insider Form-4 alt-alpha ────────────────────
    # insider_net_dollars is a SIGNED per-day net (buys minus sells), so it may
    # be negative — no floor. The two counts are non-negative.
    data["insider_net_dollars"] = _fund(1e6)
    data["insider_n_buys"] = _fund(5.0, 0.0)
    data["insider_n_sells"] = _fund(5.0, 0.0)

    return data


def _estimate_turnover(
    factor: np.ndarray, top_pct: float = 0.30, bottom_pct: float = 0.30
) -> float:
    """Estimate per-period rebalance turnover of a long-short quantile book.

    Mirrors the production engine exactly so the number is comparable to the
    backtest's reported turnover:
      - weights: long the top `top_pct`, short the bottom `bottom_pct`,
        equal-weight within each leg;
      - turnover: mean over days of the L1 weight change, Σ_n |w_t - w_{t-1}|.

    Returns 0.0 for a single-row panel (no day-over-day delta to measure).
    """
    factor = np.asarray(factor, dtype=np.float64)
    if factor.ndim == 1:
        factor = factor.reshape(-1, 1)
    if factor.shape[0] < 2:
        return 0.0

    weights = quantile_weights(factor, top_pct, bottom_pct)

    delta = np.abs(weights[1:] - weights[:-1])
    turnover = float(delta.sum(axis=1).mean())
    return turnover if np.isfinite(turnover) else 0.0


# Multiplicative noise scale for the robustness probe: data * (1 + eps), eps ~
# N(0, _NOISE_SIGMA). 3% matches AlphaEval's var=0.001 (sigma ~ 0.0316) "small
# perturbation" — large enough to reshuffle a noise-dominated factor, small
# enough to leave a genuine cross-sectional signal's ranking intact.
_NOISE_SIGMA: float = 0.03
_ROBUSTNESS_TAIL: int = 10


def _row_rank_consistency(values_a: np.ndarray, values_b: np.ndarray) -> float | None:
    """Mean per-row Spearman correlation, excluding undefined samples."""
    corrs: list[float] = []
    for x, y in zip(values_a, values_b):
        c = spearman_corr(x, y, min_count=3)
        if np.isfinite(c):
            corrs.append(c)
    return float(np.mean(corrs)) if corrs else None


def _estimate_robustness(
    expression: str,
    data: dict[str, np.ndarray],
    clean_factor: np.ndarray,
    *,
    seed: int,
    n_trials: int = 3,
) -> float:
    """Perturbation-robustness score (AlphaEval dim 3): re-evaluate the factor on
    noise-jittered inputs and average the rank consistency vs the clean ranking.

    Two noise families per AlphaEval: Gaussian (normal vol) and Student-t df=3
    (fat-tail shock). Only numeric operands are perturbed (categorical strings
    like sector/industry are passed through untouched). Deterministic given
    `seed`. Returns the mean Spearman rank correlation over all trials, or NaN if
    the factor can't be ranked (all-NaN / constant — already caught by
    factor_std, so this stays NaN rather than masquerading as fragile).
    """
    clean = np.asarray(clean_factor, dtype=np.float64)
    if clean.ndim == 1:
        clean = clean.reshape(-1, 1)
    if clean.shape[0] < _ROBUSTNESS_TAIL + 1:
        return float("nan")
    clean_tail = clean[-(_ROBUSTNESS_TAIL + 1) : -1]

    numeric_keys = [k for k, v in data.items() if v.dtype.kind in "fiu"]
    rng = np.random.default_rng(seed + 1)  # distinct stream from the panel's
    scores: list[float] = []
    for noise_kind in ("gaussian", "student_t"):
        for _ in range(n_trials):
            noisy = dict(data)
            for k in numeric_keys:
                arr = data[k]
                if noise_kind == "gaussian":
                    eps = rng.normal(0.0, _NOISE_SIGMA, size=arr.shape)
                else:
                    eps = rng.standard_t(3, size=arr.shape) * _NOISE_SIGMA
                noisy[k] = arr * (1.0 + eps)
            try:
                noisy_factor = np.asarray(evaluate(expression, noisy), dtype=np.float64)
            except Exception:  # noqa: BLE001 — a noisy eval blow-up = fragile, score it 0
                scores.append(0.0)
                continue
            if noisy_factor.ndim == 1:
                noisy_factor = noisy_factor.reshape(-1, 1)
            if noisy_factor.shape[0] < _ROBUSTNESS_TAIL + 1:
                continue
            noisy_tail = noisy_factor[-(_ROBUSTNESS_TAIL + 1) : -1]
            consistency = _row_rank_consistency(clean_tail, noisy_tail)
            if consistency is not None:
                scores.append(consistency)
    return float(np.mean(scores)) if scores else float("nan")


def _estimate_rank_stability(clean_factor: np.ndarray) -> float:
    """Temporal-stability score (AlphaEval dim 2): mean Spearman rank correlation
    between consecutive days' rankings over the IC-tail window.

    1.0 = the cross-sectional ranking is preserved day to day; ~0 = it reshuffles
    each day; negative = reversal. Operates on the already-evaluated factor, so
    no re-evaluation. Returns NaN if the factor can't be ranked (all-NaN /
    constant — already covered by factor_std).
    """
    clean = np.asarray(clean_factor, dtype=np.float64)
    if clean.ndim == 1:
        clean = clean.reshape(-1, 1)
    if clean.shape[0] < _ROBUSTNESS_TAIL + 1:
        return float("nan")
    tail = clean[-(_ROBUSTNESS_TAIL + 1) :]  # tail+1 days -> tail pairs
    consistency = _row_rank_consistency(tail[:-1], tail[1:])
    return consistency if consistency is not None else float("nan")


def smoke_test(expression: str, lookback: int, seed: int = 42) -> SmokeResult:
    """Run the 10-day Spearman-IC smoke check for an AST-validated expression."""
    n_tickers = 20
    data = _synthetic_panel(lookback, n_tickers, seed)
    close = data["close"]

    start = time.perf_counter()
    factor = evaluate(expression, data)
    runtime_ms = (time.perf_counter() - start) * 1000.0

    factor = np.asarray(factor, dtype=np.float64)
    if factor.ndim == 1:
        factor = factor.reshape(-1, 1)

    # Degeneracy gauge: std over the whole evaluated factor. nanstd of an
    # all-NaN or constant array is 0 (or NaN, normalized to 0) — both signal
    # "no cross-sectional information".
    with np.errstate(all="ignore"):
        factor_std = float(np.nanstd(factor))
    if not np.isfinite(factor_std):
        factor_std = 0.0

    # Rebalance-turnover gauge: high turnover flags a change/reversal signal
    # (e.g. an LLM emitting ts_delta(rank(X), 1) for a level hypothesis) that
    # passes the degeneracy check but gets destroyed by transaction costs.
    turnover = _estimate_turnover(factor)

    # Perturbation-robustness gauge: low score flags a factor whose ranking
    # collapses under small input noise — overfit to exact numbers, won't hold
    # out-of-sample. (AlphaEval dimension 3.)
    robustness = _estimate_robustness(expression, data, factor, seed=seed)

    # Temporal-stability gauge: low score flags a factor whose ranking reshuffles
    # day to day — the full-cross-section measure behind turnover. (AlphaEval
    # dimension 2.)
    rank_stability = _estimate_rank_stability(factor)

    fwd_ret = np.vstack(
        [np.diff(np.log(close), axis=0), np.full((1, close.shape[1]), np.nan)]
    )

    tail = 10
    if factor.shape[0] < tail + 1:
        return SmokeResult(
            rows_valid=0,
            ic_spearman=float("nan"),
            runtime_ms=runtime_ms,
            factor_std=factor_std,
            turnover=turnover,
            robustness=robustness,
            rank_stability=rank_stability,
        )

    factor_tail = factor[-(tail + 1) : -1]
    fwd_tail = fwd_ret[-(tail + 1) : -1]
    valid = np.isfinite(factor_tail) & np.isfinite(fwd_tail)
    ic = _row_rank_consistency(factor_tail, fwd_tail)
    return SmokeResult(
        rows_valid=int(valid.sum()),
        ic_spearman=ic if ic is not None else float("nan"),
        runtime_ms=float(runtime_ms),
        factor_std=factor_std,
        turnover=turnover,
        robustness=robustness,
        rank_stability=rank_stability,
    )
