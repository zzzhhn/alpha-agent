"""Data providers for fetching A-share market data."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

import pandas as pd

logger = logging.getLogger(__name__)

# Column schema returned by all providers
OHLCV_COLUMNS = ("open", "close", "high", "low", "volume", "amount")

# AKShare column mapping: Chinese column names -> English
_AKSHARE_COL_MAP: dict[str, str] = {
    "日期": "date",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "amount",
    "股票代码": "stock_code",
}

# Seconds to sleep between consecutive AKShare requests
_REQUEST_INTERVAL: float = 0.5


class DataProvider(ABC):
    """Abstract interface for market data sources."""

    @abstractmethod
    def fetch(
        self,
        stock_codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Fetch daily OHLCV data for a list of stocks.

        Parameters
        ----------
        stock_codes : list[str]
            6-digit A-share stock codes (e.g. ["600519", "000001"]).
        start_date : str
            Start date in "YYYYMMDD" format.
        end_date : str
            End date in "YYYYMMDD" format.

        Returns
        -------
        pd.DataFrame
            MultiIndex (date, stock_code) with columns defined in OHLCV_COLUMNS.
        """


class AKShareProvider(DataProvider):
    """Fetches forward-adjusted daily data from AKShare (one stock at a time).

    Accepts an optional ``ParquetCache`` — when provided, each stock is
    looked up in cache first and API results are written back after fetch.
    """

    def __init__(self, cache: "ParquetCache | None" = None) -> None:  # noqa: F821
        self._cache = cache

    def fetch(
        self,
        stock_codes: list[str],
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """Fetch daily OHLCV from AKShare for each stock code sequentially."""
        import akshare as ak  # lazy import to keep module importable without akshare

        frames: list[pd.DataFrame] = []

        for i, code in enumerate(stock_codes):
            # Try cache first
            if self._cache is not None:
                cached = self._cache.get(code, start_date, end_date)
                if cached is not None and not cached.empty:
                    logger.debug("Cache hit for %s (%d rows).", code, len(cached))
                    frames.append(cached)
                    continue

            if i > 0:
                time.sleep(_REQUEST_INTERVAL)

            try:
                raw = ak.stock_zh_a_hist(
                    symbol=code,
                    period="daily",
                    start_date=start_date,
                    end_date=end_date,
                    adjust="qfq",
                )
            except Exception:
                logger.warning("Failed to fetch data for %s, skipping.", code, exc_info=True)
                continue

            if raw is None or raw.empty:
                logger.warning("No data returned for %s, skipping.", code)
                continue

            df = _normalize_akshare_df(raw, code)
            frames.append(df)

            # Write back to cache
            if self._cache is not None:
                self._cache.put(code, df)

        if not frames:
            return _empty_ohlcv_frame()

        return pd.concat(frames).sort_index()


def _normalize_akshare_df(raw: pd.DataFrame, stock_code: str) -> pd.DataFrame:
    """Transform raw AKShare output into the canonical MultiIndex format.

    Creates a new DataFrame — the input is never mutated.
    """
    df = raw.rename(columns=_AKSHARE_COL_MAP)

    # Keep only the columns we need
    keep = ["date"] + list(OHLCV_COLUMNS)
    df = df[[c for c in keep if c in df.columns]]

    # Coerce date column
    df = df.assign(
        date=pd.to_datetime(df["date"]),
        stock_code=stock_code,
    )

    # Build MultiIndex (date, stock_code)
    df = df.set_index(["date", "stock_code"])

    # Ensure numeric types
    for col in OHLCV_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df


def _empty_ohlcv_frame() -> pd.DataFrame:
    """Return an empty DataFrame with the canonical schema."""
    idx = pd.MultiIndex.from_tuples([], names=["date", "stock_code"])
    return pd.DataFrame(columns=list(OHLCV_COLUMNS), index=idx)
