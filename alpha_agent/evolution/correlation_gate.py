"""Phase B1: SELF_CORRELATION gate.

A candidate that scores well but whose daily long-short PnL is ~the same as an
already-saved factor is not a new alpha — it's a re-discovery. WorldQuant BRAIN
bounces those as SELF_CORRELATION; this is the local analog: reject a survivor
whose |Pearson corr| of daily strategy returns against any saved factor exceeds
a threshold.

The daily-return correlation (not expression similarity) is the right measure —
it reflects what would actually be traded. Two expressions that look different
but produce the same PnL are redundant; two with opposite signs but identical
|PnL| read as correlated, which is what we want for de-duplication.

Everything runs on the same parquet panel path the zoo-correlation endpoint
uses (evaluate_factor_full → _factor_daily_returns), so the candidate and the
saved factors are compared apples-to-apples. Best-effort throughout: any load
or eval failure degrades to "not correlated" (0.0) so the gate can never block
a propose by erroring.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

# Daily long-short construction matches the zoo-correlation endpoint defaults.
_TOP = 0.30
_BOTTOM = 0.30

# |corr| at/above this marks a candidate as a near-duplicate of a saved factor.
# 0.7 is deliberately stricter than the zoo UI's 0.8 warning: factor MINING
# wants genuine diversity, not just "not identical".
SELF_CORR_THRESHOLD = 0.7


def _pairwise_pearson(a: np.ndarray, b: np.ndarray) -> Optional[float]:
    """Standard Pearson correlation over the overlapping tail of two daily-
    return series, pairwise-dropping NaNs. None when there are too few points
    or either side is constant. Uses population std on BOTH sides so the
    coefficient is exact (avoids the mixed-degrees-of-freedom shrink in
    scan.significance.cross_correlation_matrix)."""
    n = min(a.size, b.size)
    if n < 3:
        return None
    a = np.asarray(a[-n:], dtype=np.float64)
    b = np.asarray(b[-n:], dtype=np.float64)
    mask = ~(np.isnan(a) | np.isnan(b))
    if int(mask.sum()) < 3:
        return None
    x = a[mask]
    y = b[mask]
    sx = float(x.std())
    sy = float(y.std())
    if sx < 1e-12 or sy < 1e-12:
        return None
    return float(((x - x.mean()) * (y - y.mean())).mean() / (sx * sy))


def max_corr_against(
    candidate_ret: np.ndarray,
    existing_rets: dict[str, np.ndarray],
) -> tuple[float, Optional[str]]:
    """Max |Pearson corr| of the candidate's daily returns against each saved
    factor's daily returns. Pure (no IO). Returns (0.0, None) when there is
    nothing to compare against."""
    best = 0.0
    best_name: Optional[str] = None
    for name, ret in existing_rets.items():
        c = _pairwise_pearson(candidate_ret, ret)
        if c is not None and abs(c) > best:
            best = abs(c)
            best_name = name
    return (best, best_name)


def _daily_returns_for(panel, fwd, expression: str, name: str) -> Optional[np.ndarray]:
    """Evaluate one expression on the panel and reduce to its daily long-short
    return series. None on any evaluation failure (e.g. the candidate uses a
    sandboxed lf_ operator not available on the plain panel path)."""
    from alpha_agent.api.routes.zoo import _factor_daily_returns
    from alpha_agent.core.types import FactorSpec
    from alpha_agent.factor_engine.kernel import evaluate_factor_full

    try:
        # evaluate_factor_full uses ONLY spec.expression (eval_factor); the
        # other fields are metadata, so operators_used=[] safely sidesteps the
        # AllowedOperator Literal whitelist.
        spec = FactorSpec(
            name=(name or "f")[:40],
            hypothesis="self-correlation gate",
            expression=expression,
            operators_used=[],
            lookback=20,
            # `universe` is a required FactorSpec field; evaluate_factor_full
            # ignores it (it reads ONLY spec.expression), but omitting it made
            # pydantic raise on construction — every saved factor then failed
            # this try/except and the gate was a silent no-op. Any valid literal
            # works since the panel is fixed by _load_panel, not by this field.
            universe="SP500",
            justification="self-correlation gate",
        )
        factor = evaluate_factor_full(panel, spec)
    except Exception:  # noqa: BLE001 - gate must never raise into the propose loop
        return None
    return _factor_daily_returns(factor, fwd, _TOP, _BOTTOM)


class SelfCorrelationGate:
    """Precomputes the saved factors' daily returns once, then scores each
    candidate against them. Instantiate per propose round (saved factors don't
    change mid-round), call .check(expression) per surviving candidate."""

    def __init__(self, existing: list[tuple[str, str]], budget_s: float = 40.0):
        """existing: list of (name, expression) for the already-saved factors
        to guard against. Empty → the gate is a no-op (never loads the panel).

        budget_s caps the precompute wall-clock: evaluating many saved factors
        on the full panel is the heaviest part of a propose round, and this runs
        inside a Vercel function with a hard duration cap. If the budget is hit
        the gate simply guards against the subset computed so far (best-effort
        dedup) rather than risking the whole propose being killed mid-run."""
        import time

        self._ok = False
        self._panel = None
        self._fwd = None
        self._existing_rets: dict[str, np.ndarray] = {}
        if not existing:
            return
        try:
            from alpha_agent.factor_engine.factor_backtest import _load_panel

            self._panel = _load_panel()
        except Exception:  # noqa: BLE001 - no panel → gate is a no-op
            return
        self._fwd = np.full_like(self._panel.close, np.nan)
        self._fwd[:-1] = self._panel.close[1:] / self._panel.close[:-1] - 1.0
        deadline = time.monotonic() + budget_s
        for name, expr in existing:
            if time.monotonic() > deadline:
                break
            ret = _daily_returns_for(self._panel, self._fwd, expr, name)
            if ret is not None:
                self._existing_rets[name] = ret
        self._ok = len(self._existing_rets) > 0

    @property
    def active(self) -> bool:
        return self._ok

    def check(self, candidate_expression: str) -> tuple[float, Optional[str]]:
        """(max_abs_corr, most_correlated_name). (0.0, None) when the gate is
        inactive or the candidate can't be evaluated on the plain panel."""
        if not self._ok:
            return (0.0, None)
        cand = _daily_returns_for(
            self._panel, self._fwd, candidate_expression, "__candidate__"
        )
        if cand is None:
            return (0.0, None)
        return max_corr_against(cand, self._existing_rets)
