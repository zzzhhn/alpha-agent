"""Economic calendar display-only signal. Always z=0; raw carries events.

Spec §3.1 weight 0.00 — fusion engine excludes from composite.
Raw field carries the event list for the "Catalysts" section of RatingCard.

Note: do NOT `import calendar` (Python stdlib) anywhere in this module;
the module name intentionally shadows it. Use `from __future__ import annotations`
for forward refs; never import the stdlib calendar module here.
"""
from __future__ import annotations

from datetime import datetime

from alpha_agent.signals.base import SignalScore, safe_fetch


def _fetch_events(as_of: datetime) -> list[dict]:
    # Real impl pulls FRED + agent-reach for upcoming macro events.
    return []


def _fetch(ticker: str, as_of: datetime) -> SignalScore:
    events = _fetch_events(as_of)
    return SignalScore(
        ticker=ticker, z=0.0, raw=events,
        confidence=1.0 if events else 0.5,
        as_of=as_of, source="fred+reach", error=None,
    )


def fetch_signal(ticker: str, as_of: datetime) -> SignalScore:
    return safe_fetch(_fetch, ticker, as_of, source="fred+reach")
