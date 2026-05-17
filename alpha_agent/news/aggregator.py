"""PerTickerAggregator + MacroAggregator.

PerTicker: priority-failover (Finnhub -> FMP -> RSS). Each adapter
gets a CircuitBreaker; 5 consecutive failures trips a 1h cooldown.
Inside the cooldown the adapter is silently skipped.

Macro: parallel poll, no failover (sources cover disjoint events).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from alpha_agent.news.base import CircuitBreaker
from alpha_agent.news.types import MacroEvent, NewsItem

logger = logging.getLogger(__name__)


class PerTickerAggregator:
    def __init__(self, adapters: list[Any]) -> None:
        # Sort by priority ascending so iteration is failover order.
        self._adapters = sorted(adapters, key=lambda a: a.priority)
        self._breakers: dict[str, CircuitBreaker] = {
            a.name: CircuitBreaker() for a in self._adapters
        }

    async def fetch(
        self, *, ticker: str, since: datetime
    ) -> list[NewsItem]:
        for adapter in self._adapters:
            breaker = self._breakers[adapter.name]
            if breaker.is_open():
                logger.info(
                    "news: skipping %s for %s, breaker open until %s",
                    adapter.name, ticker, breaker.cooldown_until,
                )
                continue
            try:
                items = await adapter.fetch(ticker=ticker, since=since)
            except Exception as exc:
                breaker.record_failure()
                logger.warning(
                    "news: adapter %s failed for %s: %s: %s",
                    adapter.name, ticker, type(exc).__name__, exc,
                )
                continue
            breaker.record_success()
            if items:
                return items
        return []

    async def aclose(self) -> None:
        for a in self._adapters:
            try:
                await a.aclose()
            except Exception:
                pass


class MacroAggregator:
    def __init__(self, adapters: list[Any]) -> None:
        self._adapters = adapters
        self._breakers: dict[str, CircuitBreaker] = {
            a.name: CircuitBreaker() for a in adapters
        }

    async def fetch_all(self, *, since: datetime) -> list[MacroEvent]:
        async def _safe_fetch(a):
            breaker = self._breakers[a.name]
            if breaker.is_open():
                logger.info("news: macro %s breaker open", a.name)
                return []
            try:
                events = await a.fetch(since=since)
            except Exception as exc:
                breaker.record_failure()
                logger.warning(
                    "news: macro adapter %s failed: %s: %s",
                    a.name, type(exc).__name__, exc,
                )
                return []
            breaker.record_success()
            return events

        results = await asyncio.gather(*(_safe_fetch(a) for a in self._adapters))
        merged: list[MacroEvent] = []
        for batch in results:
            merged.extend(batch)
        return merged

    async def aclose(self) -> None:
        for a in self._adapters:
            try:
                await a.aclose()
            except Exception:
                pass
