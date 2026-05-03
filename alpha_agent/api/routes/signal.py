"""Signal layer endpoints — today's ranking, IC time-series, sector exposure.

P3 of the Data → Signal → Report pipeline. These endpoints turn a
FactorSpec expression into "what does this factor say about the market
today" — the answer a portfolio manager actually wants.

All three endpoints share the same factor-evaluation path used by
`/api/v1/factor/backtest`: validate the AST, load the panel, build the
operand dict, evaluate to a (T, N) array. Differences are purely
post-processing / aggregation.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from typing import Literal

from alpha_agent.core.factor_ast import (
    FactorSpecValidationError,
    validate_expression,
)
from alpha_agent.core.types import FactorSpec
from alpha_agent.factor_engine.factor_backtest import (
    _load_panel,
    _membership_csv_as_of,
    _sector_neutralize_factor,
)
from alpha_agent.factor_engine.kernel import (
    build_data_dict,
    evaluate_factor_full,
    spearman_ic,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/signal", tags=["signal"])


# ── Shared request envelope ─────────────────────────────────────────────────


class _SignalRequest(BaseModel):
    spec: FactorSpec
    # v4 (Bundle A.2 cross-page parity): sector-neutralize factor before
    # ranking so within-sector picks dominate. Same semantics as
    # /factor/backtest. Default 'none' preserves back-compat for callers
    # that haven't been updated.
    neutralize: Literal["none", "sector"] = "none"
    model_config = {"protected_namespaces": ()}


class TodayRequest(_SignalRequest):
    top_n: int = Field(default=10, ge=1, le=50)


class ICTimeseriesRequest(_SignalRequest):
    lookback: int = Field(default=60, ge=5, le=252)


class ExposureRequest(_SignalRequest):
    top_n: int = Field(default=10, ge=1, le=50)


# ── Response models ─────────────────────────────────────────────────────────


class TickerRow(BaseModel):
    ticker: str
    factor: float
    sector: str | None = None
    cap: float | None = None


class TodayResponse(BaseModel):
    as_of: str
    factor_name: str
    universe_size: int
    n_valid: int
    top: list[TickerRow]
    bottom: list[TickerRow]
    # v4 cross-page parity: surface survivorship-correction status so
    # the SignalView can show the same "✓ SP500 校正" badge that /backtest does.
    survivorship_corrected: bool = False
    membership_as_of: str | None = None
    neutralize: Literal["none", "sector"] = "none"


class ICPoint(BaseModel):
    date: str
    ic: float
    rolling_mean: float | None = None  # 20-day rolling mean of ic


class ICTimeseriesResponse(BaseModel):
    factor_name: str
    lookback: int
    points: list[ICPoint]
    summary: dict[str, float]    # {ic_mean, ic_std, ic_ir, hit_rate, ic_ci_low, ic_ci_high}
    survivorship_corrected: bool = False
    membership_as_of: str | None = None
    neutralize: Literal["none", "sector"] = "none"


class SectorExposure(BaseModel):
    sector: str
    long_pct: float
    short_pct: float
    net_pct: float
    n_long: int
    n_short: int


class CapBucket(BaseModel):
    bucket: str             # e.g. "Q1 (smallest)"
    long_pct: float
    short_pct: float
    net_pct: float


class ExposureResponse(BaseModel):
    factor_name: str
    as_of: str
    sector_exposure: list[SectorExposure]
    cap_quintile: list[CapBucket]
    survivorship_corrected: bool = False
    membership_as_of: str | None = None
    neutralize: Literal["none", "sector"] = "none"


# ── Shared evaluation helper ────────────────────────────────────────────────


def _evaluate_spec(
    spec: FactorSpec, neutralize: str = "none"
) -> tuple[np.ndarray, dict[str, np.ndarray], Any]:
    """Validate + load + evaluate. Returns (factor_TxN, data, panel).

    Operand-dict construction and factor evaluation both delegate to
    kernel.build_data_dict / kernel.evaluate_factor_full so this endpoint
    stays in lockstep with /factor/backtest and /screener/run.

    `neutralize='sector'` subtracts per-sector cross-sectional mean from
    the factor before ranking — matches the /factor/backtest knob so a
    sector-neutral signal in /signal/today behaves identically to the
    same expression on /backtest.
    """
    try:
        validate_expression(spec.expression, spec.operators_used)
    except FactorSpecValidationError as exc:
        raise HTTPException(status_code=400, detail=f"spec invalid: {exc}") from exc

    panel = _load_panel()
    data = build_data_dict(panel)

    try:
        factor = evaluate_factor_full(panel, spec)
    except (ValueError, KeyError, NotImplementedError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"factor evaluation failed: {type(exc).__name__}: {exc}",
        ) from exc

    if neutralize == "sector" and panel.sector is not None:
        factor = _sector_neutralize_factor(factor, panel.sector)

    return factor, data, panel


# ── /api/v1/signal/today ────────────────────────────────────────────────────


@router.post("/today", response_model=TodayResponse)
def signal_today(body: TodayRequest) -> TodayResponse:
    """Return the latest cross-sectional ranking — top/bottom N tickers."""
    factor, _data, panel = _evaluate_spec(body.spec, body.neutralize)
    last = factor[-1]
    valid_mask = ~np.isnan(last)
    valid_idx = np.where(valid_mask)[0]
    sectors = panel.sector[-1] if panel.sector is not None else None
    caps = panel.cap[-1] if panel.cap is not None else None

    rows: list[TickerRow] = []
    for i in valid_idx:
        rows.append(TickerRow(
            ticker=panel.tickers[i],
            factor=float(last[i]),
            sector=str(sectors[i]) if sectors is not None else None,
            cap=float(caps[i]) if caps is not None and not np.isnan(caps[i]) else None,
        ))
    rows.sort(key=lambda r: r.factor, reverse=True)
    n = body.top_n
    return TodayResponse(
        as_of=str(panel.dates[-1]),
        factor_name=body.spec.name,
        universe_size=int(len(panel.tickers)),
        n_valid=int(valid_mask.sum()),
        top=rows[:n],
        bottom=list(reversed(rows[-n:])),
        survivorship_corrected=panel.is_member is not None,
        membership_as_of=_membership_csv_as_of(),
        neutralize=body.neutralize,
    )


# ── /api/v1/signal/ic_timeseries ────────────────────────────────────────────


@router.post("/ic_timeseries", response_model=ICTimeseriesResponse)
def signal_ic_timeseries(body: ICTimeseriesRequest) -> ICTimeseriesResponse:
    """Daily cross-sectional Spearman IC over the trailing `lookback` window.

    For each day t, IC(t) = Spearman(factor[t], fwd_return[t]). Forward
    return is close[t+1]/close[t]-1, so the last day is naturally NaN
    (no T+1 yet) and is omitted.
    """
    factor, _data, panel = _evaluate_spec(body.spec, body.neutralize)
    T, _N = factor.shape

    fwd = np.full_like(panel.close, np.nan)
    fwd[:-1] = panel.close[1:] / panel.close[:-1] - 1.0

    start = max(0, T - body.lookback - 1)
    ics: list[float] = []
    dates_used: list[str] = []
    for t in range(start, T - 1):  # T-1 because last fwd is NaN
        ic = spearman_ic(factor[t], fwd[t])
        ics.append(ic)
        dates_used.append(str(panel.dates[t]))

    arr = np.asarray(ics, dtype=np.float64)
    # 20-day trailing mean — None for early indices
    rolling: list[float | None] = []
    win = 20
    for i in range(len(arr)):
        if i + 1 < win:
            rolling.append(None)
        else:
            rolling.append(float(arr[i + 1 - win : i + 1].mean()))

    points = [
        ICPoint(date=d, ic=float(v), rolling_mean=r)
        for d, v, r in zip(dates_used, arr, rolling)
    ]
    ic_mean = float(arr.mean()) if len(arr) else 0.0
    ic_std = float(arr.std()) if len(arr) else 0.0
    ic_ir = ic_mean / ic_std * np.sqrt(252) if ic_std > 0 else 0.0
    hit_rate = float((arr > 0).sum()) / len(arr) if len(arr) else 0.0

    # v4: bootstrap CI on the IC mean — same stationary block bootstrap
    # used by /factor/backtest. With block_len=20 (≈ 1 month autocorr
    # horizon) and 1000 resamples, gives a 95% CI around the realized
    # IC. Visible in frontend SignalView as a band beneath the rolling
    # mean line.
    ic_ci_low = ic_ci_high = float("nan")
    if len(arr) >= 20:
        from alpha_agent.scan.significance import stationary_block_bootstrap_ci
        ic_ci_low, ic_ci_high = stationary_block_bootstrap_ci(
            arr, lambda x: float(np.mean(x)), block_len=20, n_resamples=1000, ci=0.95, seed=42,
        )

    return ICTimeseriesResponse(
        factor_name=body.spec.name,
        lookback=body.lookback,
        points=points,
        summary={
            "ic_mean": ic_mean,
            "ic_std": ic_std,
            "ic_ir": float(ic_ir),
            "hit_rate": hit_rate,
            "ic_ci_low": float(ic_ci_low) if not np.isnan(ic_ci_low) else 0.0,
            "ic_ci_high": float(ic_ci_high) if not np.isnan(ic_ci_high) else 0.0,
        },
        survivorship_corrected=panel.is_member is not None,
        membership_as_of=_membership_csv_as_of(),
        neutralize=body.neutralize,
    )


# ── /api/v1/signal/exposure ─────────────────────────────────────────────────


@router.post("/exposure", response_model=ExposureResponse)
def signal_exposure(body: ExposureRequest) -> ExposureResponse:
    """Sector and cap-quintile exposure of today's top-N long / bottom-N short."""
    factor, _data, panel = _evaluate_spec(body.spec, body.neutralize)
    last = factor[-1]
    valid = ~np.isnan(last)
    n = body.top_n

    if panel.sector is None:
        raise HTTPException(
            status_code=400,
            detail="sector exposure requires v2 panel with sector column",
        )

    # Sort indices by factor value (desc); pick top/bottom n among valid
    valid_idx = np.where(valid)[0]
    order = valid_idx[np.argsort(-last[valid_idx])]
    if len(order) < 2 * n:
        n = len(order) // 2
    long_idx = order[:n]
    short_idx = order[-n:]

    sectors_today = panel.sector[-1]
    long_sectors = sectors_today[long_idx]
    short_sectors = sectors_today[short_idx]
    all_sectors = sorted(set(sectors_today.tolist()))

    sector_rows: list[SectorExposure] = []
    for sec in all_sectors:
        n_long = int((long_sectors == sec).sum())
        n_short = int((short_sectors == sec).sum())
        long_pct = 100.0 * n_long / max(n, 1)
        short_pct = 100.0 * n_short / max(n, 1)
        sector_rows.append(SectorExposure(
            sector=sec,
            long_pct=long_pct,
            short_pct=short_pct,
            net_pct=long_pct - short_pct,
            n_long=n_long,
            n_short=n_short,
        ))
    sector_rows.sort(key=lambda r: abs(r.net_pct), reverse=True)

    # Cap quintile (Q1 = smallest, Q5 = largest)
    cap_rows: list[CapBucket] = []
    if panel.cap is not None:
        caps_today = panel.cap[-1]
        cap_valid = ~np.isnan(caps_today)
        if cap_valid.sum() >= 5:
            cap_ranks = np.full_like(caps_today, np.nan)
            order_cap = np.argsort(caps_today[cap_valid])
            ranks = np.argsort(order_cap).astype(float)
            cap_ranks[cap_valid] = ranks * 5.0 / cap_valid.sum()
            buckets = np.clip(cap_ranks.astype(np.int64, casting="unsafe"), 0, 4)
            for q in range(5):
                in_bucket = buckets == q
                n_long_q = int(in_bucket[long_idx].sum())
                n_short_q = int(in_bucket[short_idx].sum())
                cap_rows.append(CapBucket(
                    bucket=f"Q{q+1}" + (" (smallest)" if q == 0 else " (largest)" if q == 4 else ""),
                    long_pct=100.0 * n_long_q / max(n, 1),
                    short_pct=100.0 * n_short_q / max(n, 1),
                    net_pct=100.0 * (n_long_q - n_short_q) / max(n, 1),
                ))

    return ExposureResponse(
        factor_name=body.spec.name,
        as_of=str(panel.dates[-1]),
        sector_exposure=sector_rows,
        cap_quintile=cap_rows,
        survivorship_corrected=panel.is_member is not None,
        membership_as_of=_membership_csv_as_of(),
        neutralize=body.neutralize,
    )
