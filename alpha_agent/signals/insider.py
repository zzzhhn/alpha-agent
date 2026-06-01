"""Insider trading signal from SEC EDGAR Form 4 last 30 days.
Net dollar value (open-market purchases - sales); tanh normalized.

Architecture (2026-06-01): the signal no longer fetches SEC inline (that was a
stub returning []). Form 4 parsing for the whole universe is thousands of
rate-limited SEC requests and cannot run on the signal path / Vercel cron, so a
separate daily job (scripts/ingest_insider_form4.py via GitHub Actions, using
alpha_agent.signals.insider_edgar) precomputes the net value per ticker into the
insider_form4 table. Each signal cron run loads that table once and calls
prime_cache(...) before iterating tickers; fetch_signal then reads the primed
dict with no network or DB access.

Academic anchors (2026-05-18):
- Primary modern reference: Cohen, Malloy, Pomorski (2012, JoF 67(3))
  "Decoding Inside Information" — opportunistic (irregular, info-loaded) buys
  earn ~10%/yr alpha; routine trades ~0. The ingestion keeps open-market codes
  (P / S) and drops grants / exercises / gifts (A / M / G / F) as a first-order
  opportunistic filter.
- Attention refinement: Alldredge & Cicero (2015, JFE 115(1)).
- Firm-level trait: Ali & Hirshleifer (2017, JFE 126(3)).
- Historical anchors: Seyhun (1986; 1998); Lakonishok & Lee (2001, RFS 14(1)).

Phase X TBD: routine-vs-opportunistic classifier (trade-month clustering)."""
from __future__ import annotations

from datetime import datetime

import numpy as np

from alpha_agent.signals.base import SignalScore, safe_fetch

# Primed once per cron run from the insider_form4 table:
# {TICKER: (net_value, n_filings)}. Empty until prime_cache() is called, in
# which case every ticker reports a neutral z=0 (no filings) — same graceful
# behavior as before, never a hard failure.
_NET_CACHE: dict[str, tuple[float, int]] = {}


def prime_cache(values: dict[str, tuple[float, int]]) -> None:
    """Replace the in-memory net-value cache (called by the signal crons)."""
    global _NET_CACHE
    _NET_CACHE = dict(values)


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    entry = _NET_CACHE.get(ticker.upper())
    if entry is None or entry[1] == 0:
        return SignalScore(
            ticker=ticker, z=0.0,
            raw={"net_value": 0, "n_fillings": 0},
            confidence=0.4, as_of=as_of, source="edgar",
            error="no filings in 30d",
        )
    net, n = entry
    z = float(np.tanh(net / 1_000_000))
    return SignalScore(
        ticker=ticker, z=z,
        raw={"net_value": net, "n_fillings": n},
        confidence=0.70, as_of=as_of, source="edgar", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="edgar")
