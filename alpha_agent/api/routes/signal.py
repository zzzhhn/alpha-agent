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

from alpha_agent.core.factor_ast import (
    FactorSpecValidationError,
    validate_expression,
)
from alpha_agent.core.types import FactorSpec
from alpha_agent.factor_engine.factor_backtest import (
    _ADV_WINDOWS,
    _load_panel,
    _spearman_ic,
)
from alpha_agent.scan.vectorized import OPS, evaluate as eval_factor, ts_mean

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/signal", tags=["signal"])


# ── Shared request envelope ─────────────────────────────────────────────────


class _SignalRequest(BaseModel):
    spec: FactorSpec
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


class ICPoint(BaseModel):
    date: str
    ic: float
    rolling_mean: float | None = None  # 20-day rolling mean of ic


class ICTimeseriesResponse(BaseModel):
    factor_name: str
    lookback: int
    points: list[ICPoint]
    summary: dict[str, float]    # {ic_mean, ic_std, ic_ir, hit_rate}


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


# ── Shared evaluation helper ────────────────────────────────────────────────


def _evaluate_spec(spec: FactorSpec) -> tuple[np.ndarray, dict[str, np.ndarray], Any]:
    """Validate + load + evaluate. Returns (factor_TxN, data, panel)."""
    try:
        validate_expression(spec.expression, spec.operators_used)
    except FactorSpecValidationError as exc:
        raise HTTPException(status_code=400, detail=f"spec invalid: {exc}") from exc

    panel = _load_panel()
    T, N = panel.close.shape

    trailing_returns = np.full_like(panel.close, np.nan)
    trailing_returns[1:] = panel.close[1:] / panel.close[:-1] - 1.0
    vwap_proxy = (panel.high + panel.low + panel.close) / 3.0

    data: dict[str, np.ndarray] = {
        "close": panel.close, "open": panel.open_, "high": panel.high,
        "low": panel.low, "volume": panel.volume,
        "returns": trailing_returns, "vwap": vwap_proxy,
    }
    if panel.cap is not None:
        data["cap"] = panel.cap
        dollar_vol = panel.close * panel.volume
        data["dollar_volume"] = dollar_vol
        for w in _ADV_WINDOWS:
            data[f"adv{w}"] = ts_mean(dollar_vol, w)
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

    try:
        factor = np.asarray(eval_factor(spec.expression, data), dtype=np.float64)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"factor evaluation failed: {type(exc).__name__}: {exc}",
        ) from exc

    if factor.shape != (T, N):
        raise HTTPException(
            status_code=400,
            detail=f"factor shape {factor.shape} != panel shape ({T}, {N})",
        )
    return factor, data, panel


# ── /api/v1/signal/today ────────────────────────────────────────────────────


@router.post("/today", response_model=TodayResponse)
def signal_today(body: TodayRequest) -> TodayResponse:
    """Return the latest cross-sectional ranking — top/bottom N tickers."""
    factor, _data, panel = _evaluate_spec(body.spec)
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
    )


# ── /api/v1/signal/ic_timeseries ────────────────────────────────────────────


@router.post("/ic_timeseries", response_model=ICTimeseriesResponse)
def signal_ic_timeseries(body: ICTimeseriesRequest) -> ICTimeseriesResponse:
    """Daily cross-sectional Spearman IC over the trailing `lookback` window.

    For each day t, IC(t) = Spearman(factor[t], fwd_return[t]). Forward
    return is close[t+1]/close[t]-1, so the last day is naturally NaN
    (no T+1 yet) and is omitted.
    """
    factor, _data, panel = _evaluate_spec(body.spec)
    T, _N = factor.shape

    fwd = np.full_like(panel.close, np.nan)
    fwd[:-1] = panel.close[1:] / panel.close[:-1] - 1.0

    start = max(0, T - body.lookback - 1)
    ics: list[float] = []
    dates_used: list[str] = []
    for t in range(start, T - 1):  # T-1 because last fwd is NaN
        ic = _spearman_ic(factor[t], fwd[t])
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

    return ICTimeseriesResponse(
        factor_name=body.spec.name,
        lookback=body.lookback,
        points=points,
        summary={
            "ic_mean": ic_mean,
            "ic_std": ic_std,
            "ic_ir": float(ic_ir),
            "hit_rate": hit_rate,
        },
    )


# ── /api/v1/signal/exposure ─────────────────────────────────────────────────


@router.post("/exposure", response_model=ExposureResponse)
def signal_exposure(body: ExposureRequest) -> ExposureResponse:
    """Sector and cap-quintile exposure of today's top-N long / bottom-N short."""
    factor, _data, panel = _evaluate_spec(body.spec)
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
    )
