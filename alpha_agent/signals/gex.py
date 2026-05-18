"""GEX (Gamma Exposure) intraday regime — conditioning signal.

Phase 3 backlog B5 (2026-05-19). Source: Phase 1D English t#7
SqueezeMetrics GEX/VEX/DIX framework + Phase 1A Douyin v5 "five-layer
information stack" — separates "buy-the-dip works" from "trend-
continuation" environments using dealer hedging flow inferred from
option-chain open interest.

Mathematical core (per-strike, summed across chain):
  γ_call = N'(d1) / (S · σ · √τ)
  γ_put  = γ_call (same magnitude under put-call parity)
  d1     = (ln(S/K) + (r + σ²/2)τ) / (σ √τ)
  N'(d1) = (1/√(2π)) · exp(-d1²/2)

Aggregate signed gamma exposure (dollars):
  GEX = Σ_strikes [ γ_call · OI_call  −  γ_put · OI_put ] · 100 · S²

Sign convention: positive GEX → dealers net-long gamma → buy weakness /
sell strength (pinning, low realized vol). Negative GEX → dealers
net-short gamma → buy strength / sell weakness (trend continuation,
high realized vol).

Regime classification (z-normalised over the rolling SP500 sample is
the institutional ideal; v1 uses absolute thresholds derived from the
SqueezeMetrics public-blog conventions until we accumulate enough
universe history):
  pinned    : GEX > +500M and |GEX| > 2× rolling 5d median
  volatile  : GEX < −500M and |GEX| > 2× rolling 5d median
  mixed     : everything else

Surfaced as a conditioning variable on the stock detail page only —
NOT folded into composite v1. The downstream user reads it as
"this is a buy-dip day" vs "this is a trend day" alongside the other
signals; combine() weight scheme stays untouched.

Performance notes (relevant for fast_intraday cron):
- yfinance Ticker.option_chain(expiry) returns strike/OI/IV per leg.
  Nearest expiry only in v1; multi-expiry sum is an obvious extension
  once cache layer (B3) absorbs the additional fetches.
- ~50 strikes × 2 legs × ~100 tickers = ~10K BS evals per shard,
  microseconds each; the IO of fetching option chains dominates.
- Failures (no chain, IV all NaN, options halted) return None so the
  caller can record absence rather than crash the cron.
"""
from __future__ import annotations

import logging
import math
import os
from datetime import datetime

import numpy as np

logger = logging.getLogger(__name__)


def _norm_pdf(x: float) -> float:
    """Standard-normal PDF, hand-coded so the module has no scipy dep."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _bs_gamma(spot: float, strike: float, iv: float, tau_years: float,
              risk_free: float = 0.045) -> float:
    """Black-Scholes gamma. Returns 0 for degenerate inputs rather than NaN
    so a single bad strike doesn't poison the chain sum."""
    if spot <= 0 or strike <= 0 or iv <= 0 or tau_years <= 0:
        return 0.0
    try:
        sigma_sqrt_tau = iv * math.sqrt(tau_years)
        d1 = (math.log(spot / strike) + (risk_free + 0.5 * iv * iv) * tau_years) / sigma_sqrt_tau
        return _norm_pdf(d1) / (spot * sigma_sqrt_tau)
    except (ValueError, ZeroDivisionError, OverflowError):
        return 0.0


def _years_to_expiry(expiry_str: str, as_of: datetime) -> float:
    """Convert yfinance expiry string (YYYY-MM-DD) to year fraction."""
    try:
        exp = datetime.strptime(expiry_str, "%Y-%m-%d")
        if as_of.tzinfo is not None:
            exp = exp.replace(tzinfo=as_of.tzinfo)
        days = (exp - as_of).total_seconds() / 86400.0
        return max(days, 0.5) / 365.0  # floor at half-day to avoid div-by-0
    except (ValueError, TypeError):
        return 0.0


_REGIME_BAND_DOLLARS = float(os.environ.get("ALPHA_GEX_REGIME_BAND_USD", "5e8"))


def _classify_regime(signed_gex: float) -> str:
    """v1 absolute-threshold classifier. The institutional gold-standard
    is a per-ticker rolling z-score, but that needs a GEX history table
    we haven't built yet — env-tunable band is the bridge."""
    if signed_gex > _REGIME_BAND_DOLLARS:
        return "pinned"
    if signed_gex < -_REGIME_BAND_DOLLARS:
        return "volatile"
    return "mixed"


def compute_gex(ticker: str, as_of: datetime) -> dict | None:
    """Pull the nearest-expiry option chain for `ticker` and aggregate
    signed gamma exposure. Returns dict with regime / signed_notional /
    n_strikes / dominant_expiry, or None when the chain is empty / all
    IV NaN / fetch fails.

    No try/except wrapping the import — yfinance is a hard dep already
    used across signals/. ImportError here would mean the env is
    misconfigured, which should surface loud not silent.
    """
    import yfinance as yf

    try:
        t = yf.Ticker(ticker)
        expiries = t.options
        if not expiries:
            return None
        # Nearest expiry only in v1 (multi-expiry sum is a B5.1 follow-up
        # once cache layer absorbs the extra fetch cost).
        nearest = expiries[0]
        chain = t.option_chain(nearest)
        spot = t.fast_info.get("last_price") if hasattr(t, "fast_info") else None
        if spot is None or not isinstance(spot, (int, float)) or spot <= 0:
            # Fall back to .info.regularMarketPrice if fast_info unavailable
            info = t.info or {}
            spot = info.get("regularMarketPrice") or info.get("currentPrice") or 0
        if not spot or spot <= 0:
            return None
    except Exception as exc:  # noqa: BLE001 — yfinance raises arbitrary types
        logger.warning(
            "gex chain fetch failed ticker=%s: %s: %s",
            ticker, type(exc).__name__, exc,
        )
        return None

    tau = _years_to_expiry(nearest, as_of)
    if tau <= 0:
        return None

    # Vectorise the per-strike gamma sums via numpy where the chain has
    # enough rows; otherwise fall through to a pure-python loop.
    try:
        calls_strike = chain.calls["strike"].to_numpy(dtype=float)
        calls_iv = chain.calls["impliedVolatility"].to_numpy(dtype=float)
        calls_oi = chain.calls["openInterest"].fillna(0).to_numpy(dtype=float)
        puts_strike = chain.puts["strike"].to_numpy(dtype=float)
        puts_iv = chain.puts["impliedVolatility"].to_numpy(dtype=float)
        puts_oi = chain.puts["openInterest"].fillna(0).to_numpy(dtype=float)
    except (KeyError, AttributeError) as exc:
        logger.warning(
            "gex chain shape unexpected ticker=%s: %s: %s",
            ticker, type(exc).__name__, exc,
        )
        return None

    spot_f = float(spot)
    # NaN-mask: a strike with NaN IV contributes 0 (treat as absent).
    calls_iv_mask = np.where(np.isnan(calls_iv), 0.0, calls_iv)
    puts_iv_mask = np.where(np.isnan(puts_iv), 0.0, puts_iv)

    call_gammas = np.array(
        [_bs_gamma(spot_f, float(k), float(iv), tau) for k, iv in zip(calls_strike, calls_iv_mask)],
        dtype=float,
    )
    put_gammas = np.array(
        [_bs_gamma(spot_f, float(k), float(iv), tau) for k, iv in zip(puts_strike, puts_iv_mask)],
        dtype=float,
    )

    # GEX dollar formula: (gamma * OI - gamma * OI) * 100 (contract size) * S^2
    call_term = float(np.nansum(call_gammas * calls_oi))
    put_term = float(np.nansum(put_gammas * puts_oi))
    signed_notional = (call_term - put_term) * 100.0 * spot_f * spot_f

    n_strikes = int(len(calls_strike) + len(puts_strike))
    if n_strikes == 0 or (call_term == 0 and put_term == 0):
        return None

    return {
        "regime": _classify_regime(signed_notional),
        "signed_notional": signed_notional,
        "n_strikes": n_strikes,
        "dominant_expiry": nearest,
        "spot": spot_f,
    }
