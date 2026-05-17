"""NewsAdapter Protocol + shared HTTP session factory + circuit breaker.

Per-adapter rate-limit / IP-block behavior differs (Finnhub 60req/min,
Yahoo blocks aggressive fanout, etc.). Each adapter owns its own
backoff / retry; the breaker here is for cross-cycle health: an adapter
failing N consecutive cycles is marked down for a cooldown window so the
aggregator skips it without re-paying its timeout.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from typing import Any, Literal, Protocol, runtime_checkable

import httpx


# Per spec: 5 consecutive cycle failures triggers a 1h cooldown.
BREAKER_FAILURE_THRESHOLD = 5
BREAKER_COOLDOWN = timedelta(hours=1)


@dataclass
class CircuitBreaker:
    consecutive_failures: int = 0
    cooldown_until: datetime | None = None

    def record_success(self) -> None:
        self.consecutive_failures = 0
        self.cooldown_until = None

    def record_failure(self) -> None:
        self.consecutive_failures += 1
        if self.consecutive_failures >= BREAKER_FAILURE_THRESHOLD:
            self.cooldown_until = datetime.now(UTC) + BREAKER_COOLDOWN

    def is_open(self) -> bool:
        if self.cooldown_until is None:
            return False
        if datetime.now(UTC) >= self.cooldown_until:
            # Probe: leave consecutive_failures alone; next success resets.
            self.cooldown_until = None
            return False
        return True


def make_client(timeout_seconds: float = 10.0) -> httpx.AsyncClient:
    """Standard httpx async session used by every HTTP adapter."""
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds, connect=5.0),
        follow_redirects=True,
        headers={"User-Agent": "alpha-agent-news/1.0 (+https://alpha.bobbyzhong.com)"},
    )


@runtime_checkable
class NewsAdapter(Protocol):
    """Every adapter implements this. Adapters are constructed once per
    cron run and reused across all tickers in that run; httpx connection
    pool reuse matters for not getting rate-limited."""

    name: str  # 'finnhub', 'fmp', 'rss_yahoo', ...
    channel: Literal["per_ticker", "macro"]
    priority: int  # per_ticker: 1=primary, 2=failover, 3=tertiary

    async def fetch(
        self,
        *,
        ticker: str | None = None,
        since: datetime,
    ) -> list[Any]:  # NewsItem or MacroEvent
        ...

    async def is_available(self) -> bool:
        ...

    async def aclose(self) -> None:
        ...
