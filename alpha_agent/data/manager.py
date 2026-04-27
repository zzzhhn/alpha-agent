"""Pluggable data-source manager with priority-failover.

Why this exists (A4 of v3): the legacy `YFinanceProvider.fetch()` had the
yfinance → akshare fallback chain hardcoded as inline `if df is None` calls.
Adding a third source (polygon, EODHD, Tiingo) would mean editing the call
site every time, and there was no single place to add cross-cutting concerns
like per-source rate-limit RLocks.

`DataFetcherManager` solves this by accepting any object that satisfies the
`BaseFetcher` Protocol (just needs `name`, `priority`, and `fetch_ohlcv()`),
sorts them by priority, and walks the chain on every call. A failed fetcher
falls through to the next; the first one that returns non-empty wins.

Each registered fetcher owns its own `RLock`. The lock is acquired around the
fetcher's fetch call so concurrent threads can't simultaneously hammer the
*same* source (most external APIs rate-limit per-IP-per-source), but DIFFERENT
sources still parallelize freely. This is the same pattern
`daily_stock_analysis/data_provider/base.py` uses — see horizontal-vertical
analysis report for the cross-repo audit.
"""
from __future__ import annotations

import logging
import threading
from typing import Protocol, runtime_checkable

import pandas as pd

logger = logging.getLogger(__name__)


@runtime_checkable
class BaseFetcher(Protocol):
    """Minimum surface a data source must implement to be registered.

    `priority`: lower number = tried first. Convention: 1 for primary,
    2 for fallback, etc.
    `name`: short human-readable label for logging and per-source RLock keys.
    `fetch_ohlcv()`: return a normalized OHLCV DataFrame, or None / empty
    DataFrame on miss. Should NOT raise — internal exceptions handled there.
    """

    name: str
    priority: int

    def fetch_ohlcv(
        self, ticker: str, start: str, end: str
    ) -> pd.DataFrame | None: ...


class DataFetcherManager:
    """Priority-sorted fetcher registry with per-source RLock + failover.

    Usage:
        mgr = DataFetcherManager()
        mgr.register(YFinanceFetcher())     # priority=1
        mgr.register(AkshareUSFetcher())    # priority=2
        df = mgr.fetch_ohlcv("AAPL", "2025-01-01", "2025-12-31")
    """

    def __init__(self) -> None:
        self._fetchers: list[BaseFetcher] = []
        self._locks: dict[str, threading.RLock] = {}

    def register(self, fetcher: BaseFetcher) -> None:
        if fetcher.name in self._locks:
            raise ValueError(f"fetcher {fetcher.name!r} already registered")
        self._fetchers.append(fetcher)
        self._locks[fetcher.name] = threading.RLock()
        # Re-sort after every register so the order is always stable
        # regardless of registration order.
        self._fetchers.sort(key=lambda f: f.priority)
        logger.debug("registered fetcher %s (priority=%d)", fetcher.name, fetcher.priority)

    def names(self) -> list[str]:
        """Names in active priority order. Useful for diagnostics."""
        return [f.name for f in self._fetchers]

    def fetch_ohlcv(
        self, ticker: str, start: str, end: str,
    ) -> pd.DataFrame | None:
        """Try each fetcher in priority order; return first non-empty hit.

        Each fetcher's call is wrapped in its own RLock so multiple threads
        targeting the same source serialize, while parallel calls hitting
        DIFFERENT sources stay parallel. Per-source exceptions are caught
        and logged so one bad source doesn't kill the chain.
        """
        if not self._fetchers:
            logger.warning("no fetchers registered; returning None for %s", ticker)
            return None

        attempted: list[str] = []
        for f in self._fetchers:
            attempted.append(f.name)
            with self._locks[f.name]:
                try:
                    df = f.fetch_ohlcv(ticker, start, end)
                except Exception:  # noqa: BLE001 — surface upstream and continue
                    logger.warning(
                        "fetcher %s raised on %s, falling through",
                        f.name, ticker, exc_info=True,
                    )
                    continue
            if df is not None and not df.empty:
                if len(attempted) > 1:
                    logger.info(
                        "%s served %s after %d miss(es): %s",
                        f.name, ticker, len(attempted) - 1, attempted[:-1],
                    )
                return df
            logger.debug("%s: miss for %s", f.name, ticker)

        logger.warning(
            "all %d fetchers missed for %s: %s",
            len(self._fetchers), ticker, attempted,
        )
        return None
