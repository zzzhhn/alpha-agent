"""US stock data provider using priority-failover across yfinance + AKShare.

Source ordering is controlled by `DataFetcherManager` from data/manager.py
rather than hardcoded fallback chains. Adding a new data source is now a
matter of writing a class that implements the `BaseFetcher` Protocol and
calling `manager.register()`.
"""

from __future__ import annotations

import logging
import random
import time

import pandas as pd
from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from alpha_agent.data.manager import DataFetcherManager
from alpha_agent.data.provider import DataProvider, OHLCV_COLUMNS, _empty_ohlcv_frame

logger = logging.getLogger(__name__)

# Base inter-request delay; actual sleep adds 0.5-2.0s jitter.
_REQUEST_INTERVAL: float = 0.3

# Network-level transient errors worth retrying. Crucially, generic HTTPError
# (4xx auth / 422 schema) is excluded — retrying those just burns quota.
_TRANSIENT_NETWORK_EXCEPTIONS: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
)
try:
    import requests

    _TRANSIENT_NETWORK_EXCEPTIONS = (
        *_TRANSIENT_NETWORK_EXCEPTIONS,
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.ChunkedEncodingError,
    )
except ImportError:  # requests is a transitive dep of yfinance/akshare; if absent the libs aren't usable
    pass


_retry_network = retry(
    reraise=True,
    stop=stop_after_attempt(4),
    wait=wait_random_exponential(multiplier=1.0, min=2.0, max=30.0),
    retry=retry_if_exception_type(_TRANSIENT_NETWORK_EXCEPTIONS),
)


def _jittered_sleep() -> None:
    time.sleep(_REQUEST_INTERVAL + random.uniform(0.5, 2.0))


class AkshareUSFetcher:
    """AKShare's stock_us_daily — Sina Finance backed, works from mainland China.

    Conforms to BaseFetcher Protocol (data/manager.py). priority=1 because
    in this deployment context (frequently China-network) AKShare typically
    succeeds first.
    """

    name = "akshare_us"
    priority = 1

    def fetch_ohlcv(
        self, ticker: str, start: str, end: str,
    ) -> pd.DataFrame | None:
        try:
            import akshare as ak
        except ImportError:
            logger.debug("akshare not installed, %s skipped", self.name)
            return None

        @_retry_network
        def _call() -> "pd.DataFrame":
            return ak.stock_us_daily(symbol=ticker, adjust="qfq")

        try:
            raw = _call()
        except RetryError:
            logger.warning("%s retries exhausted for %s", self.name, ticker)
            return None
        except Exception:  # noqa: BLE001 — non-transient, hand off to manager
            logger.warning("%s failed for %s", self.name, ticker, exc_info=True)
            return None

        if raw is None or raw.empty:
            return None
        return _normalize_akshare_us(raw, ticker, start, end)


class YFinanceFetcher:
    """yfinance — works on non-China networks. priority=2 (fallback)."""

    name = "yfinance"
    priority = 2

    def fetch_ohlcv(
        self, ticker: str, start: str, end: str,
    ) -> pd.DataFrame | None:
        try:
            import yfinance as yf
        except ImportError:
            logger.debug("yfinance not installed, %s skipped", self.name)
            return None

        @_retry_network
        def _call() -> "pd.DataFrame":
            return yf.download(
                ticker, start=start, end=end,
                progress=False, auto_adjust=True, threads=False,
            )

        try:
            data = _call()
        except RetryError:
            logger.warning("%s retries exhausted for %s", self.name, ticker)
            return None
        except Exception:  # noqa: BLE001
            logger.warning("%s failed for %s", self.name, ticker, exc_info=True)
            return None

        if data is None or data.empty:
            return None
        return _normalize_yfinance(data, ticker)


def build_default_us_manager() -> DataFetcherManager:
    """Wire up the default US-equity fetcher chain (akshare → yfinance).

    Anything wanting to add a third source (polygon, EODHD) just registers
    its own BaseFetcher implementation here without touching the call sites.
    """
    mgr = DataFetcherManager()
    mgr.register(AkshareUSFetcher())
    mgr.register(YFinanceFetcher())
    return mgr


class YFinanceProvider(DataProvider):
    """Top-level US OHLCV provider.

    Delegates to a `DataFetcherManager` for the actual source-failover logic.
    The class name is kept for back-compat (existing call sites import
    `YFinanceProvider`); internally it no longer cares which source serves
    the data.
    """

    def __init__(
        self,
        cache: "ParquetCache | None" = None,
        manager: DataFetcherManager | None = None,
    ) -> None:
        self._cache = cache
        self._manager = manager if manager is not None else build_default_us_manager()

    def fetch(
        self,
        stock_codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Fetch daily OHLCV for a list of US tickers.

        Parameters
        ----------
        stock_codes : list[str]
            US ticker symbols (e.g. ["AAPL", "MSFT"]).
        start_date, end_date : str
            "YYYYMMDD" format (provider contract).
        """
        frames: list[pd.DataFrame] = []
        start_fmt = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
        end_fmt = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

        for i, ticker in enumerate(stock_codes):
            if self._cache is not None:
                cached = self._cache.get(ticker, start_date, end_date)
                if cached is not None and not cached.empty:
                    logger.debug("Cache hit for %s (%d rows).", ticker, len(cached))
                    frames.append(cached)
                    continue

            if i > 0:
                _jittered_sleep()

            df = self._manager.fetch_ohlcv(ticker, start_fmt, end_fmt)

            if df is None or df.empty:
                logger.warning("No data for %s from any source (%s)", ticker, self._manager.names())
                continue

            frames.append(df)

            if self._cache is not None:
                self._cache.put(ticker, df)

        if not frames:
            return _empty_ohlcv_frame()
        return pd.concat(frames).sort_index()


def _normalize_yfinance(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Transform yfinance output into canonical MultiIndex format."""
    df = raw.reset_index()
    # Handle multi-level columns from yfinance
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]

    col_map = {"Date": "date", "Open": "open", "Close": "close",
               "High": "high", "Low": "low", "Volume": "volume"}
    df = df.rename(columns=col_map)

    keep = ["date"] + [c for c in OHLCV_COLUMNS if c in df.columns]
    df = df[keep]
    df = df.assign(
        date=pd.to_datetime(df["date"]),
        stock_code=ticker,
    )
    df = df.set_index(["date", "stock_code"])
    return df


def _normalize_akshare_us(
    raw: pd.DataFrame, ticker: str, start: str, end: str,
) -> pd.DataFrame:
    """Transform AKShare US daily output into canonical format."""
    col_map = {"date": "date", "open": "open", "close": "close",
               "high": "high", "low": "low", "volume": "volume"}
    df = raw.rename(columns=col_map)

    keep = ["date"] + [c for c in OHLCV_COLUMNS if c in df.columns]
    df = df[[c for c in keep if c in df.columns]]
    df = df.assign(
        date=pd.to_datetime(df["date"]),
        stock_code=ticker,
    )

    # Filter date range
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    df = df[(df["date"] >= start_ts) & (df["date"] <= end_ts)]

    df = df.set_index(["date", "stock_code"])
    return df
