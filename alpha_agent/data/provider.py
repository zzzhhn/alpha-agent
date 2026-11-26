"""Data providers for fetching A-share market data."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod

import pandas as pd

logger = logging.getLogger(__name__)

# Column schema returned by all providers
OHLCV_COLUMNS = ("open", "close", "high", "low", "volume", "amount")

_CN_MARKET = "CN"
_CN_PRICE_BASIS = "qfq"

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
    checked for full interval coverage first; partial coverage fetches only
    missing sub-ranges and atomically merges them back into cache.
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
        upstream_calls = 0

        for code in stock_codes:
            if self._cache is not None:
                cached = self._cache.get(
                    code,
                    start_date,
                    end_date,
                    market=_CN_MARKET,
                    price_basis=_CN_PRICE_BASIS,
                    allow_empty=True,
                )
                if cached is not None:
                    logger.debug("Cache hit for %s (%d rows).", code, len(cached))
                    if not cached.empty:
                        frames.append(cached)
                    continue

                missing = self._cache.missing_ranges(
                    code,
                    start_date,
                    end_date,
                    market=_CN_MARKET,
                    price_basis=_CN_PRICE_BASIS,
                )
            else:
                missing = [(start_date, end_date)]

            all_segments_ok = True
            fetched_segments: list[pd.DataFrame] = []
            for seg_start, seg_end in missing:
                if upstream_calls > 0:
                    time.sleep(_REQUEST_INTERVAL)
                upstream_calls += 1

                try:
                    fetch_history = getattr(ak, "stock_zh_a_hist_em", None) or ak.stock_zh_a_hist
                    raw = fetch_history(
                        symbol=code,
                        period="daily",
                        start_date=seg_start,
                        end_date=seg_end,
                        adjust=_CN_PRICE_BASIS,
                    )
                except Exception:
                    logger.warning(
                        "Failed to fetch data for %s [%s..%s], skipping.",
                        code,
                        seg_start,
                        seg_end,
                        exc_info=True,
                    )
                    all_segments_ok = False
                    break

                if raw is None or raw.empty:
                    logger.info(
                        "No rows returned for %s [%s..%s] (closed or halted).",
                        code,
                        seg_start,
                        seg_end,
                    )
                    if self._cache is not None:
                        self._cache.put(
                            code,
                            _empty_ohlcv_frame(),
                            start_date=seg_start,
                            end_date=seg_end,
                            market=_CN_MARKET,
                            price_basis=_CN_PRICE_BASIS,
                            record_empty_range=True,
                        )
                    continue

                seg_df = _normalize_akshare_df(raw, code)
                fetched_segments.append(seg_df)
                if self._cache is not None:
                    self._cache.put(
                        code,
                        seg_df,
                        start_date=seg_start,
                        end_date=seg_end,
                        market=_CN_MARKET,
                        price_basis=_CN_PRICE_BASIS,
                        record_empty_range=True,
                    )

            if not all_segments_ok:
                continue
            if self._cache is not None:
                merged = self._cache.peek_slice(
                    code,
                    start_date,
                    end_date,
                    market=_CN_MARKET,
                    price_basis=_CN_PRICE_BASIS,
                )
                if merged is not None:
                    if not merged.empty:
                        frames.append(merged)
                    continue
            if fetched_segments:
                combined = pd.concat(fetched_segments)
                combined = combined[~combined.index.duplicated(keep="last")].sort_index()
                frames.append(combined)

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
