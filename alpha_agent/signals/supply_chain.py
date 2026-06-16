"""Supply-chain bottleneck signal (serenity-skill integration seam #2).

A research-driven signal: a serenity supply-chain study scores each name's
bottleneck thesis (0-100, see signals/supply_chain_scorecard.py), and that
score maps to a z-tilt fed into fusion. Studies are qualitative, so the inputs
are NOT auto-derivable from the market-data adapters; they are written to the
supply_chain_scorecard table by a research session and read here.

Architecture mirrors insider.py: a separate job populates the table, the signal
crons call prime_cache(...) once per run, and fetch_signal then reads the primed
dict with no DB/network access. A ticker with no scorecard emits z=None so it is
dropped from the composite and the cross-sectional grade (no fake signal, rule 9).

Live weight is 0 (display-only) until the bottleneck z is validated against
forward returns in ic_backtest_monthly, exactly like calendar / geopolitical_
impact. Flip fusion/weights.py once the IC history supports it.
"""
from __future__ import annotations

from datetime import datetime

from alpha_agent.signals.base import SignalScore, safe_fetch
from alpha_agent.signals.supply_chain_scorecard import score_to_z

# Primed once per cron run from the supply_chain_scorecard table:
# {TICKER: {"final_score": float, "verdict": str, "evidence_quality": float}}.
# Empty until prime_cache() runs (and empty is the normal early state: most
# tickers have no serenity study), in which case every ticker emits z=None.
_SCORECARD_CACHE: dict[str, dict] = {}


def prime_cache(values: dict[str, dict]) -> None:
    """Replace the in-memory scorecard cache (called by the signal crons)."""
    global _SCORECARD_CACHE
    _SCORECARD_CACHE = dict(values)


def _confidence_from_evidence(evidence_quality: float) -> float:
    """Confidence scales with the scorecard's evidence_quality factor (0-5):
    a thesis backed by filings/orders is trusted more than a thin lead. Capped
    at 0.9 so a research signal never claims more certainty than the factor."""
    return min(0.9, 0.3 + max(0.0, min(5.0, evidence_quality)) / 5.0 * 0.6)


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    entry = _SCORECARD_CACHE.get(ticker.upper())
    if entry is None:
        # No serenity supply-chain study for this name = genuinely NO signal,
        # not a measured-neutral 0. z=None drops it from the composite and the
        # cross-sectional grade (shown "—"), same graceful contract as insider.
        return SignalScore(
            ticker=ticker, z=None,  # type: ignore[typeddict-item]
            raw={"scored": False},
            confidence=0.0, as_of=as_of, source="serenity-scorecard",
            error="no supply-chain scorecard",
        )
    final_score = float(entry.get("final_score", 0.0))
    evidence_quality = float(entry.get("evidence_quality", 0.0))
    return SignalScore(
        ticker=ticker,
        z=score_to_z(final_score),
        raw={
            "final_score": final_score,
            "verdict": entry.get("verdict", ""),
            "evidence_quality": evidence_quality,
        },
        confidence=_confidence_from_evidence(evidence_quality),
        as_of=as_of, source="serenity-scorecard", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="serenity-scorecard")
