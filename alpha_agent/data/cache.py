"""Parquet-based local cache for market data."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Data fresher than this (in seconds) is considered valid
_FRESHNESS_THRESHOLD: float = 24 * 60 * 60  # 24 hours

# Default cache directory relative to project root
_DEFAULT_CACHE_DIR = Path("data/parquet")


class ParquetCache:
    """Read/write Parquet files as a simple file-based cache.

    Each stock code gets its own Parquet file.  Files older than 24 hours
    are treated as stale and ignored on reads.
    """

    def __init__(self, cache_dir: Path = _DEFAULT_CACHE_DIR) -> None:
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(
        self,
        stock_code: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame | None:
        """Return cached data for *stock_code* if fresh, else ``None``.

        Parameters
        ----------
        stock_code : str
            6-digit stock code.
        start_date, end_date : str
            Date range in ``YYYYMMDD`` format.  Used to slice the cached
            DataFrame — only rows within the range are returned.
        """
        path = self._path_for(stock_code)
        if not path.exists():
            return None

        if not self._is_fresh(path):
            logger.debug("Cache stale for %s, ignoring.", stock_code)
            return None

        try:
            df = pd.read_parquet(path)
        except Exception:
            logger.warning("Failed to read cache for %s.", stock_code, exc_info=True)
            return None

        # Slice to requested date range (inclusive)
        start = pd.Timestamp(start_date)
        end = pd.Timestamp(end_date)

        # Filter on the 'date' level of the MultiIndex
        mask = (
            df.index.get_level_values("date") >= start
        ) & (
            df.index.get_level_values("date") <= end
        )
        result = df.loc[mask]

        if result.empty:
            return None

        return result

    def put(self, stock_code: str, data: pd.DataFrame) -> None:
        """Persist *data* as a Parquet file.  Does not mutate *data*."""
        if data.empty:
            return

        path = self._path_for(stock_code)
        data.to_parquet(path, engine="pyarrow")
        logger.debug("Cached %d rows for %s.", len(data), stock_code)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _path_for(self, stock_code: str) -> Path:
        return self._cache_dir / f"{stock_code}.parquet"

    @staticmethod
    def _is_fresh(path: Path) -> bool:
        age = time.time() - path.stat().st_mtime
        return age < _FRESHNESS_THRESHOLD
