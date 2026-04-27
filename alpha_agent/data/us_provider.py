"""US stock data provider using AKShare primary (with yfinance fallback for non-China networks)."""

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


class YFinanceProvider(DataProvider):
    """Fetches US daily OHLCV data via yfinance.

    Accepts an optional ``ParquetCache`` for per-ticker caching.
    Falls back to AKShare's US stock API when yfinance is blocked (e.g. mainland China).
    """

    def __init__(self, cache: "ParquetCache | None" = None) -> None:
        self._cache = cache

    def fetch(
        self,
        stock_codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Fetch daily OHLCV for US tickers.

        Parameters
        ----------
        stock_codes : list[str]
            US ticker symbols (e.g. ["AAPL", "MSFT"]).
        start_date, end_date : str
            Date range in "YYYYMMDD" format.
        """
        frames: list[pd.DataFrame] = []
        start_fmt = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:]}"
        end_fmt = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:]}"

        for i, ticker in enumerate(stock_codes):
            # Cache check
            if self._cache is not None:
                cached = self._cache.get(ticker, start_date, end_date)
                if cached is not None and not cached.empty:
                    logger.debug("Cache hit for %s (%d rows).", ticker, len(cached))
                    frames.append(cached)
                    continue

            if i > 0:
                _jittered_sleep()

            # AKShare primary (Sina Finance — works from China without VPN)
            df = self._fetch_akshare_us(ticker, start_fmt, end_fmt)
            if df is None:
                df = self._fetch_yfinance(ticker, start_fmt, end_fmt)

            if df is None or df.empty:
                logger.warning("No data for %s, skipping.", ticker)
                continue

            frames.append(df)

            if self._cache is not None:
                self._cache.put(ticker, df)

        if not frames:
            return _empty_ohlcv_frame()

        return pd.concat(frames).sort_index()

    @staticmethod
    def _fetch_yfinance(ticker: str, start: str, end: str) -> pd.DataFrame | None:
        """Try fetching via yfinance. Returns None on failure.

        Network-level transient errors (ConnectionError/Timeout) are retried
        up to 4 times with jittered exponential backoff. 4xx HTTPErrors,
        parse errors, and any non-network exception fail fast and fall back
        to AKShare.
        """
        try:
            import yfinance as yf
        except ImportError:
            logger.debug("yfinance not installed, skipping.")
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
            logger.warning("yfinance retries exhausted for %s.", ticker)
            return None
        except Exception:
            # Non-transient: 4xx, parse errors, etc. — give the fallback a chance.
            logger.warning("yfinance failed for %s.", ticker, exc_info=True)
            return None

        if data is None or data.empty:
            return None

        return _normalize_yfinance(data, ticker)

    @staticmethod
    def _fetch_akshare_us(ticker: str, start: str, end: str) -> pd.DataFrame | None:
        """Fallback: use AKShare's US stock daily API (works from China).

        Same retry policy as yfinance: only transient network errors are retried.
        """
        try:
            import akshare as ak
        except ImportError:
            logger.debug("akshare not installed, skipping US fallback.")
            return None

        @_retry_network
        def _call() -> "pd.DataFrame":
            # AKShare uses stock_us_daily with symbol like "AAPL"
            return ak.stock_us_daily(symbol=ticker, adjust="qfq")

        try:
            raw = _call()
        except RetryError:
            logger.warning("AKShare retries exhausted for %s.", ticker)
            return None
        except Exception:
            logger.warning("AKShare US fallback failed for %s.", ticker, exc_info=True)
            return None

        if raw is None or raw.empty:
            return None

        return _normalize_akshare_us(raw, ticker, start, end)


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
