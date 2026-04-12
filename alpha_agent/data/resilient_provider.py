"""Resilient data provider with multi-source fallback and health monitoring.

Blueprint p4: "Alpha Core fetches from multiple providers with fallback logic.
Each data source has a health monitor and queue system to tolerate provider downtime."

Provider chain: yfinance → AKShare US → (future: IB, Financial Datasets MCP)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol

import pandas as pd

from alpha_agent.data.cache import ParquetCache
from alpha_agent.data.provider import DataProvider, _empty_ohlcv_frame

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderHealth:
    """Health status of a single data provider."""

    name: str
    status: str  # "healthy" | "degraded" | "down"
    last_success: float  # unix timestamp
    last_failure: float  # unix timestamp
    success_count: int
    failure_count: int
    avg_latency_ms: float


class ResilientProvider(DataProvider):
    """Wraps multiple DataProvider instances with fallback and health tracking.

    Tries providers in order. On failure, moves to the next.
    Tracks per-provider health for monitoring endpoints.

    Parameters
    ----------
    providers : list of (name, DataProvider) tuples
        Ordered by priority. First working provider wins.
    cache : ParquetCache, optional
        Shared cache — only the first successful result is cached.
    cooldown_seconds : float
        After a provider fails, skip it for this many seconds.
    """

    def __init__(
        self,
        providers: list[tuple[str, DataProvider]],
        cache: ParquetCache | None = None,
        cooldown_seconds: float = 300.0,
    ) -> None:
        self._providers = providers
        self._cache = cache
        self._cooldown = cooldown_seconds

        # Per-provider health tracking (mutable — monitoring state, not data)
        self._health: dict[str, _MutableHealth] = {
            name: _MutableHealth(name=name) for name, _ in providers
        }

    def fetch(
        self,
        stock_codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Fetch OHLCV with cascading fallback across providers."""
        # Try cache first (across all tickers at once)
        if self._cache is not None:
            cached_frames: list[pd.DataFrame] = []
            uncached_codes: list[str] = []
            for code in stock_codes:
                cached = self._cache.get(code, start_date, end_date)
                if cached is not None and not cached.empty:
                    cached_frames.append(cached)
                else:
                    uncached_codes.append(code)

            if not uncached_codes:
                logger.debug("All %d tickers served from cache", len(stock_codes))
                return pd.concat(cached_frames).sort_index()
        else:
            uncached_codes = stock_codes
            cached_frames = []

        # Try providers in order for uncached tickers
        fetched = _empty_ohlcv_frame()
        source_name = "none"

        for name, provider in self._providers:
            health = self._health[name]

            # Skip if in cooldown
            if health.is_in_cooldown(self._cooldown):
                logger.debug(
                    "Skipping %s (cooldown, last failure %.0fs ago)",
                    name,
                    time.time() - health.last_failure,
                )
                continue

            start_time = time.monotonic()
            try:
                result = provider.fetch(uncached_codes, start_date, end_date)
                elapsed_ms = (time.monotonic() - start_time) * 1000

                if result is not None and not result.empty:
                    health.record_success(elapsed_ms)
                    fetched = result
                    source_name = name
                    logger.info(
                        "%s returned %d rows for %d tickers (%.0fms)",
                        name,
                        len(result),
                        len(uncached_codes),
                        elapsed_ms,
                    )
                    break
                else:
                    health.record_failure()
                    logger.warning("%s returned empty data", name)

            except Exception:
                elapsed_ms = (time.monotonic() - start_time) * 1000
                health.record_failure()
                logger.warning(
                    "%s failed after %.0fms",
                    name,
                    elapsed_ms,
                    exc_info=True,
                )

        # Cache the fetched data
        if self._cache is not None and not fetched.empty:
            for code in uncached_codes:
                try:
                    code_data = fetched.xs(code, level="stock_code")
                    if not code_data.empty:
                        # Re-add the stock_code level for caching
                        code_data = code_data.assign(stock_code=code).set_index(
                            "stock_code", append=True
                        )
                        self._cache.put(code, code_data)
                except (KeyError, Exception):
                    pass

        # Combine cached + freshly fetched
        all_frames = cached_frames + ([fetched] if not fetched.empty else [])
        if not all_frames:
            return _empty_ohlcv_frame()

        return pd.concat(all_frames).sort_index()

    def get_health(self) -> list[ProviderHealth]:
        """Return health status of all providers (for monitoring API)."""
        return [h.to_frozen() for h in self._health.values()]


class _MutableHealth:
    """Internal mutable health tracker for a single provider."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.last_success: float = 0.0
        self.last_failure: float = 0.0
        self.success_count: int = 0
        self.failure_count: int = 0
        self._latencies: list[float] = []

    def record_success(self, latency_ms: float) -> None:
        self.last_success = time.time()
        self.success_count += 1
        self._latencies.append(latency_ms)
        # Keep last 100 latencies
        if len(self._latencies) > 100:
            self._latencies = self._latencies[-100:]

    def record_failure(self) -> None:
        self.last_failure = time.time()
        self.failure_count += 1

    def is_in_cooldown(self, cooldown_seconds: float) -> bool:
        if self.last_failure == 0:
            return False
        return (time.time() - self.last_failure) < cooldown_seconds

    def to_frozen(self) -> ProviderHealth:
        avg_lat = (
            sum(self._latencies) / len(self._latencies)
            if self._latencies
            else 0.0
        )
        if self.failure_count == 0:
            status = "healthy"
        elif self.success_count > self.failure_count:
            status = "degraded"
        else:
            status = "down"

        return ProviderHealth(
            name=self.name,
            status=status,
            last_success=self.last_success,
            last_failure=self.last_failure,
            success_count=self.success_count,
            failure_count=self.failure_count,
            avg_latency_ms=round(avg_lat, 1),
        )
