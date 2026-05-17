"""T1.2 — Operand look-ahead tamper test.

The contract: for any factor expression and any time index `t`, the value of
`factor[i]` for `i ≤ t` must NOT depend on input data at rows `> t`.

Implementation: build a small synthetic panel; pick a split index `t`; run
each candidate expression on (a) the clean panel and (b) a panel where rows
`(t+1):` are replaced with random different data. The first `t+1` rows of
the resulting factor must be bit-identical (NaN-aware).

Coverage strategy:
  * One probe expression per OPS entry (see PROBES below) — catches per-op
    leakage.
  * A handful of nested / composite expressions — catches dispatch-layer
    bugs that don't surface when ops run alone.
  * Fundamentals access (e.g. `eps`, `revenue`) — catches the
    publish-lag broadcast scenario from Lane B audit. These probes intentionally
    skip the +45d publish-lag fix that's coming in T1.1; for now they only
    verify the time-direction property: changing future fundamental values
    must not change past factor values. (T1.1 will add a separate test
    asserting the publish-lag is honored.)

Fail mode: if any probe fails, the operator (or expression dispatch) reads
forward in time. That is a Critical bug — every backtest using that op is
inflated.
"""
from __future__ import annotations


import numpy as np
import pytest

from alpha_agent.scan.vectorized import OPS, evaluate as eval_factor

# ── Synthetic panel ─────────────────────────────────────────────────────────

T = 15  # sessions
N = 4   # tickers
SPLIT = 10  # rows 0..10 are "past", rows 11..14 are "future" we tamper with
SEED = 42


def _make_panel(seed: int = SEED) -> dict[str, np.ndarray]:
    """Synthetic data dict that matches kernel.build_data_dict's keys.

    Values are deterministic (seeded) but nonzero / non-constant so that
    operators don't accidentally hit short-circuits (e.g. ts_std on constant
    column = 0 would mask leakage bugs).
    """
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0, 1, (T, N)), axis=0)
    open_ = close + rng.normal(0, 0.5, (T, N))
    high = np.maximum(close, open_) + rng.uniform(0, 1, (T, N))
    low = np.minimum(close, open_) - rng.uniform(0, 1, (T, N))
    volume = rng.uniform(1e6, 1e7, (T, N))
    returns = np.full_like(close, np.nan)
    returns[1:] = close[1:] / close[:-1] - 1.0
    vwap = (high + low + close) / 3.0
    cap = rng.uniform(1e10, 1e12, (T, N))
    dollar_volume = close * volume
    sector = np.array([["Tech", "Health", "Tech", "Energy"]] * T)
    industry = np.array([["Software", "Pharma", "Hardware", "Oil"]] * T)
    return {
        "close": close,
        "open": open_,
        "high": high,
        "low": low,
        "volume": volume,
        "returns": returns,
        "vwap": vwap,
        "cap": cap,
        "dollar_volume": dollar_volume,
        "adv5": dollar_volume,  # placeholder; tests below don't depend on rolling correctness here
        "adv10": dollar_volume,
        "adv20": dollar_volume,
        "adv60": dollar_volume,
        "adv120": dollar_volume,
        "adv180": dollar_volume,
        "sector": sector,
        "industry": industry,
        "subindustry": industry,
        "exchange": np.array([["NASDAQ"] * N] * T),
        "currency": np.array([["USD"] * N] * T),
        "revenue": rng.uniform(1e8, 1e10, (T, N)),
        "net_income_adjusted": rng.uniform(-1e8, 1e9, (T, N)),
        "ebitda": rng.uniform(1e7, 1e9, (T, N)),
        "eps": rng.uniform(-2.0, 10.0, (T, N)),
        "equity": rng.uniform(1e9, 1e11, (T, N)),
        "assets": rng.uniform(1e9, 1e12, (T, N)),
        "free_cash_flow": rng.uniform(-1e8, 1e9, (T, N)),
        "gross_profit": rng.uniform(1e7, 1e9, (T, N)),
    }


def _tamper_future(data: dict[str, np.ndarray], split: int) -> dict[str, np.ndarray]:
    """Return a copy of `data` with rows (split+1):] replaced by different values.

    Replacement: for numeric arrays, add a deterministic perturbation that's
    guaranteed non-zero everywhere; for object/string arrays (sector, industry),
    leave alone (they aren't part of the lookahead surface — they're constants
    over time anyway). Same shape preserved.
    """
    rng = np.random.default_rng(SEED + 1)  # different seed than clean panel
    out: dict[str, np.ndarray] = {}
    for k, arr in data.items():
        if arr.dtype.kind in ("U", "O"):
            out[k] = arr.copy()
            continue
        new = arr.copy().astype(np.float64)
        # Replace future rows with a clearly different distribution
        new[split + 1:] = rng.normal(loc=10.0, scale=5.0, size=arr[split + 1:].shape)
        out[k] = new
    return out


def _arrays_equal_past(clean: np.ndarray, tampered: np.ndarray, split: int) -> bool:
    """NaN-aware equality on rows [0..split]."""
    a = np.asarray(clean)[: split + 1]
    b = np.asarray(tampered)[: split + 1]
    if a.shape != b.shape:
        return False
    # Both NaN at same positions → ok; both finite & equal → ok
    nan_a = np.isnan(a)
    nan_b = np.isnan(b)
    if not np.array_equal(nan_a, nan_b):
        return False
    finite_mask = ~nan_a
    return bool(np.allclose(a[finite_mask], b[finite_mask], atol=1e-12, rtol=0))


# ── Probe expressions: at least one per OP ──────────────────────────────────

# Each entry: probe expression that exercises the named operator. The probe
# is constructed to actually depend on TIME (uses close / returns / volume)
# so leakage in the operator would show up in the past.
PROBES: dict[str, str] = {
    # arithmetic
    "abs": "abs(returns)",
    "add": "add(close, volume)",
    "subtract": "subtract(close, open)",
    "sub": "sub(close, open)",
    "multiply": "multiply(close, volume)",
    "mul": "mul(close, volume)",
    "divide": "divide(close, volume)",
    "div": "div(close, volume)",
    "inverse": "inverse(close)",
    "log": "log(volume)",
    "sqrt": "sqrt(volume)",
    "power": "power(returns, 2)",
    "pow": "pow(returns, 2)",
    "sign": "sign(returns)",
    "signed_power": "signed_power(returns, 2)",
    "max": "max(close, open)",
    "min": "min(close, open)",
    "reverse": "reverse(close)",
    "densify": "densify(close)",
    # logical
    "if_else": "if_else(greater(close, open), high, low)",
    "and_": "and_(greater(close, open), greater(volume, open))",
    "or_": "or_(greater(close, open), greater(volume, open))",
    "not_": "not_(greater(close, open))",
    "is_nan": "is_nan(returns)",
    "equal": "equal(close, open)",
    "not_equal": "not_equal(close, open)",
    "less": "less(close, open)",
    "greater": "greater(close, open)",
    "less_equal": "less_equal(close, open)",
    "greater_equal": "greater_equal(close, open)",
    # time-series
    "ts_delay": "ts_delay(close, 2)",
    "ts_delta": "ts_delta(close, 2)",
    "ts_mean": "ts_mean(close, 5)",
    "ts_std": "ts_std(returns, 5)",
    "ts_std_dev": "ts_std_dev(returns, 5)",
    "ts_sum": "ts_sum(volume, 5)",
    "ts_product": "ts_product(returns, 3)",
    "ts_min": "ts_min(low, 5)",
    "ts_max": "ts_max(high, 5)",
    "ts_rank": "ts_rank(close, 5)",
    "ts_zscore": "ts_zscore(close, 5)",
    "ts_arg_min": "ts_arg_min(low, 5)",
    "ts_arg_max": "ts_arg_max(high, 5)",
    "ts_corr": "ts_corr(close, volume, 5)",
    "ts_covariance": "ts_covariance(close, volume, 5)",
    "ts_quantile": "ts_quantile(close, 5)",
    "ts_decay_linear": "ts_decay_linear(returns, 5)",
    "ts_decay_exp": "ts_decay_exp(returns, 5)",
    "ts_count_nans": "ts_count_nans(returns, 5)",
    "ts_regression": "ts_regression(close, volume, 5)",
    "ts_backfill": "ts_backfill(returns, 5)",
    "last_diff_value": "last_diff_value(close)",
    # cross-section
    "rank": "rank(close)",
    "zscore": "zscore(close)",
    "scale": "scale(close)",
    "normalize": "normalize(close)",
    "quantile": "quantile(close)",
    "winsorize": "winsorize(returns)",
    # transformational
    "trade_when": "trade_when(greater(close, open), close, ts_delay(close, 1))",
    "hump": "hump(close, 0.05)",
    # group
    "group_rank": "group_rank(close, sector)",
    "group_zscore": "group_zscore(close, sector)",
    "group_mean": "group_mean(close, sector)",
    "group_scale": "group_scale(close, sector)",
    "group_neutralize": "group_neutralize(close, sector)",
    "group_backfill": "group_backfill(returns, sector)",
}

# Sanity: every key in OPS has a probe (caught early if a new op is added).
_MISSING_PROBES = sorted(set(OPS.keys()) - set(PROBES.keys()))


# ── Tests ───────────────────────────────────────────────────────────────────


def test_every_op_has_a_probe() -> None:
    """If a new operator lands without a tamper-test probe, fail loudly."""
    assert not _MISSING_PROBES, (
        f"OPS has {len(_MISSING_PROBES)} operator(s) without a no-lookahead "
        f"probe in tests/test_no_lookahead.py: {_MISSING_PROBES}. "
        "Add a probe expression to PROBES."
    )


@pytest.mark.parametrize("op_name,expr", sorted(PROBES.items()))
def test_op_does_not_peek(op_name: str, expr: str) -> None:
    """For each op, factor[i] for i ≤ SPLIT must not change when row > SPLIT changes."""
    clean = _make_panel()
    tampered = _tamper_future(clean, SPLIT)

    factor_clean = eval_factor(expr, clean)
    factor_tampered = eval_factor(expr, tampered)

    factor_clean = np.asarray(factor_clean, dtype=np.float64)
    factor_tampered = np.asarray(factor_tampered, dtype=np.float64)

    assert _arrays_equal_past(factor_clean, factor_tampered, SPLIT), (
        f"Operator {op_name!r} leaks future data: factor[:{SPLIT + 1}] "
        f"differs after tampering rows ({SPLIT + 1}:). Probe: {expr}"
    )


# Composite expressions covering common factor patterns.
COMPOSITE_PROBES: list[str] = [
    "rank(ts_mean(returns, 12))",
    "rank(divide(eps, assets))",
    "ts_zscore(divide(close, ts_mean(close, 20)), 60)",
    "group_neutralize(rank(ts_zscore(returns, 5)), sector)",
    "if_else(greater(ts_std(returns, 20), 0.02), rank(returns), rank(close))",
    "ts_decay_linear(rank(divide(volume, ts_mean(volume, 20))), 5)",
]


@pytest.mark.parametrize("expr", COMPOSITE_PROBES)
def test_composite_does_not_peek(expr: str) -> None:
    """Real-world factor expressions must also not peek."""
    clean = _make_panel()
    tampered = _tamper_future(clean, SPLIT)

    factor_clean = np.asarray(eval_factor(expr, clean), dtype=np.float64)
    factor_tampered = np.asarray(eval_factor(expr, tampered), dtype=np.float64)

    assert _arrays_equal_past(factor_clean, factor_tampered, SPLIT), (
        f"Composite expression leaks future: {expr}"
    )


def test_clean_panel_evaluates_without_error() -> None:
    """Sanity: synthetic panel matches the operand schema; nothing in the
    test setup is silently broken."""
    data = _make_panel()
    # Pick one expression per arity class to exercise dispatch.
    for expr in [
        "close",
        "rank(close)",
        "ts_mean(close, 3)",
        "add(close, volume)",
        "if_else(greater(close, open), high, low)",
        "group_rank(close, sector)",
    ]:
        result = eval_factor(expr, data)
        assert np.asarray(result).shape == (T, N), (
            f"Expression {expr!r} produced wrong shape"
        )
