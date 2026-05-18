"""Analyst consensus signal. yfinance .info exposes recommendationKey
('strong_buy'|'buy'|'hold'|'underperform'|'sell') + targetMeanPrice.
We map the key to [-2, +2] and target upside to [-1, +1], average.

Academic anchors (added 2026-05-18):
- Primary modern reference: So (2013, JFE 108(3)) "A New Approach to
  Predicting Analyst Forecast Errors" — *changes* in analyst forecasts
  (revisions) carry more alpha than *levels* (consensus rating). Our
  current signal uses only levels; revision-momentum is the canonical
  upgrade path.
- Cross-asset framing: Engelberg, McLean, Pontiff (2018, JoF 73(5))
  "Anomalies and News" — analyst-revision price moves cluster around
  news events; useful when combining analyst with news signal weights.
- Long-vs-short horizon: Da & Warachka (2011, JFE 100(2)) "The Disparity
  between Long-Term and Short-Term Forecasted Earnings Growth" — LTG/STG
  spread as additional analyst-based predictor.
- Historical anchors: Womack (1996, JoF) initial documentation of analyst
  recommendation drift; Barber-Lehavy-McNichols-Trueman (2001, JoF)
  systematic profit from consensus rating sorts.

Phase X TBD: add target-revision-momentum term using a daily target_mean
snapshot table — yfinance doesn't expose historical target series cleanly
so we'd build our own 30d snapshot via cron, then:
  z = 0.4 * rec_z + 0.3 * upside_z + 0.3 * tanh(target_revision_30d / 0.05)"""
from __future__ import annotations
from datetime import datetime
from alpha_agent.signals.base import SignalScore, safe_fetch

_REC_MAP = {
    "strong_buy": 2.0, "buy": 1.0, "hold": 0.0,
    "underperform": -1.0, "sell": -2.0, "strong_sell": -2.0,
}


def _fetch_info(ticker: str) -> dict:
    import yfinance as yf
    return yf.Ticker(ticker).info or {}


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    info = _fetch_info(ticker)
    rec = (info.get("recommendationKey") or "").lower()
    cur = info.get("currentPrice")
    tgt = info.get("targetMeanPrice")
    if rec not in _REC_MAP:
        return SignalScore(ticker=ticker, z=0.0, raw=None, confidence=0.2,
                           as_of=as_of, source="yfinance",
                           error="missing recommendationKey")
    rec_z = _REC_MAP[rec] / 2.0  # -> [-1, +1]
    target_upside_z = 0.0
    if cur and tgt:
        upside = (tgt - cur) / cur
        target_upside_z = max(min(upside / 0.20, 1.0), -1.0)  # ±20% saturates
    z = max(min((rec_z + target_upside_z) / 2 * 2, 3.0), -3.0)
    return SignalScore(
        ticker=ticker, z=z,
        raw={"recommendation": rec, "current": cur, "target": tgt},
        confidence=0.80, as_of=as_of, source="yfinance", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="yfinance")
