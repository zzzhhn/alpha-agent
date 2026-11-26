"""Parquet-based local cache for market data."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import tempfile
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

logger = logging.getLogger(__name__)

# Data fresher than this (in seconds) is considered valid
_FRESHNESS_THRESHOLD: float = 24 * 60 * 60  # 24 hours

# Default cache directory relative to project root
_DEFAULT_CACHE_DIR = Path("data/parquet")

_METADATA_KEY = b"alpha_agent_cache"
_METADATA_VERSION = 1
_MARKET_CALENDARS: dict[str, str] = {
    "US": "XNYS",
    "CN": "XSHG",
}

_IN_PROCESS_LOCKS_GUARD = threading.Lock()
_IN_PROCESS_LOCKS: dict[Path, threading.RLock] = {}


def _parse_day(value: str | date | pd.Timestamp) -> date:
    return pd.Timestamp(value).date()


def _format_ymd(value: date) -> str:
    return value.strftime("%Y%m%d")


@lru_cache(maxsize=4)
def _exchange_calendar(calendar_name: str):
    import exchange_calendars as xcals

    return xcals.get_calendar(calendar_name)


def _in_process_lock(lock_path: Path) -> threading.RLock:
    resolved = lock_path.resolve()
    with _IN_PROCESS_LOCKS_GUARD:
        lock = _IN_PROCESS_LOCKS.get(resolved)
        if lock is None:
            lock = threading.RLock()
            _IN_PROCESS_LOCKS[resolved] = lock
        return lock


@contextmanager
def _exclusive_file_lock(lock_path: Path) -> Iterator[None]:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    thread_lock = _in_process_lock(lock_path)
    with thread_lock:
        with lock_path.open("a+b") as fh:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _empty_like(columns: list[str] | tuple[str, ...]) -> pd.DataFrame:
    idx = pd.MultiIndex.from_arrays(
        [
            pd.DatetimeIndex([], name="date"),
            pd.Index([], dtype="object", name="stock_code"),
        ]
    )
    return pd.DataFrame(columns=list(columns), index=idx, dtype="float64")


def _normalize_intervals(raw_intervals: list[tuple[date, date]]) -> list[tuple[date, date]]:
    cleaned = sorted((s, e) for s, e in raw_intervals if s <= e)
    if not cleaned:
        return []
    merged: list[tuple[date, date]] = [cleaned[0]]
    for start, end in cleaned[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end + timedelta(days=1):
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _subtract_intervals(
    target: tuple[date, date],
    covered: list[tuple[date, date]],
) -> list[tuple[date, date]]:
    start, end = target
    if start > end:
        return []
    missing: list[tuple[date, date]] = []
    cursor = start
    for cov_start, cov_end in _normalize_intervals(covered):
        if cov_end < cursor:
            continue
        if cov_start > end:
            break
        if cov_start > cursor:
            missing.append((cursor, min(end, cov_start - timedelta(days=1))))
        cursor = max(cursor, cov_end + timedelta(days=1))
        if cursor > end:
            break
    if cursor <= end:
        missing.append((cursor, end))
    return missing


def _expected_sessions(
    start: date,
    end: date,
    market: str | None,
) -> list[date] | None:
    """Return trading sessions in ``[start, end]``, or ``None`` if calendar-out-of-bounds."""
    if start > end or market is None:
        return None
    cal_name = _MARKET_CALENDARS.get(market.upper())
    if cal_name is None:
        return None
    cal = _exchange_calendar(cal_name)
    first_session = cal.first_session.date()
    last_session = cal.last_session.date()
    if start < first_session or end > last_session:
        return None
    return [s.date() for s in cal.sessions_in_range(start.isoformat(), end.isoformat())]


def _trim_closed_days(
    interval: tuple[date, date],
    market: str | None,
) -> tuple[date, date] | None:
    """Trim leading/trailing non-trading days; return ``None`` if all days are closed."""
    start, end = interval
    sessions = _expected_sessions(start, end, market)
    if sessions is None:
        return interval if start <= end else None
    if not sessions:
        return None
    return (sessions[0], sessions[-1])


def _derive_legacy_intervals(df: pd.DataFrame, market: str | None) -> list[tuple[date, date]]:
    """Conservative coverage inference for pre-existing Parquet files without metadata.

    Without stored request bounds, only observed trading dates are proven.
    Adjacent trading sessions on a known exchange calendar can merge across
    weekends/holidays, while missing trading sessions remain uncovered gaps.
    """
    if df.empty or "date" not in df.index.names:
        return []
    observed = sorted({pd.Timestamp(ts).date() for ts in df.index.get_level_values("date")})
    if not observed:
        return []

    sessions = _expected_sessions(observed[0], observed[-1], market)
    if sessions is None:
        return _normalize_intervals([(d, d) for d in observed])

    observed_set = set(observed)
    runs: list[tuple[date, date]] = []
    run_start: date | None = None
    run_end: date | None = None
    for session in sessions:
        if session in observed_set:
            if run_start is None:
                run_start = session
            run_end = session
        elif run_start is not None and run_end is not None:
            runs.append((run_start, run_end))
            run_start = None
            run_end = None
    if run_start is not None and run_end is not None:
        runs.append((run_start, run_end))

    session_set = set(sessions)
    extras = [(d, d) for d in observed if d not in session_set]
    return _normalize_intervals(runs + extras)


class ParquetCache:
    """Read/write Parquet files as a simple file-based cache.

    Each stock code gets its own Parquet file alongside schema metadata
    recording which ``(start_date, end_date)`` request intervals, ``market``,
    and ``price_basis`` are covered.  Partial range coverage is treated as a
    cache miss unless all missing trading sessions are fetched and merged.
    """

    def __init__(
        self,
        cache_dir: Path = _DEFAULT_CACHE_DIR,
        freshness_seconds: float = _FRESHNESS_THRESHOLD,
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._freshness = freshness_seconds
        self._hits: int = 0
        self._misses: int = 0
        self._stats_lock = threading.Lock()

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
        *,
        market: str | None = None,
        price_basis: str | None = None,
        allow_empty: bool = False,
    ) -> pd.DataFrame | None:
        """Return cached data for *stock_code* if fresh and fully covered, else ``None``.

        Parameters
        ----------
        stock_code : str
            Ticker or stock code.
        start_date, end_date : str
            Requested inclusive date range (``YYYYMMDD`` or ``YYYY-MM-DD``).
        market : str, optional
            Market identifier (e.g. ``"US"``, ``"CN"``) for exchange-calendar
            closed-day handling and cross-market isolation.
        price_basis : str, optional
            Price adjustment basis (e.g. ``"adjusted"``, ``"qfq"``) so
            incompatible bases never masquerade as cache hits.
        """
        req_start = _parse_day(start_date)
        req_end = _parse_day(end_date)
        if req_start > req_end:
            self._record_miss()
            return None

        state = self._load_state(
            stock_code,
            expected_market=market,
            expected_price_basis=price_basis,
        )
        if state is None:
            self._record_miss()
            return None

        df, intervals = state
        missing = self._compute_missing_intervals(
            (req_start, req_end),
            intervals,
            market=market,
        )
        if missing:
            self._record_miss()
            return None

        result = self._slice_frame(df, req_start, req_end)
        if result.empty:
            if allow_empty:
                sessions = _expected_sessions(req_start, req_end, market)
                if sessions == [] or intervals:
                    self._record_hit()
                    return result
            self._record_miss()
            return None

        self._record_hit()
        return result

    def peek_slice(
        self,
        stock_code: str,
        start_date: str,
        end_date: str,
        *,
        market: str | None = None,
        price_basis: str | None = None,
    ) -> pd.DataFrame | None:
        """Return cached rows in [start_date, end_date] without altering hit/miss stats."""
        req_start = _parse_day(start_date)
        req_end = _parse_day(end_date)
        if req_start > req_end:
            return None
        state = self._load_state(
            stock_code,
            expected_market=market,
            expected_price_basis=price_basis,
        )
        if state is None:
            return None
        df, intervals = state
        if self._compute_missing_intervals((req_start, req_end), intervals, market=market):
            return None
        return self._slice_frame(df, req_start, req_end)

    def missing_ranges(
        self,
        stock_code: str,
        start_date: str,
        end_date: str,
        *,
        market: str | None = None,
        price_basis: str | None = None,
    ) -> list[tuple[str, str]]:
        """Return uncovered ``(YYYYMMDD, YYYYMMDD)`` sub-ranges for *stock_code*.

        Weekends and exchange holidays on known markets (``US``/``XNYS``,
        ``CN``/``XSHG``) are trimmed so closed days never trigger upstream
        re-fetches.
        """
        req_start = _parse_day(start_date)
        req_end = _parse_day(end_date)
        if req_start > req_end:
            return []

        state = self._load_state(
            stock_code,
            expected_market=market,
            expected_price_basis=price_basis,
        )
        intervals = state[1] if state is not None else []
        missing = self._compute_missing_intervals(
            (req_start, req_end),
            intervals,
            market=market,
        )
        return [(_format_ymd(s), _format_ymd(e)) for s, e in missing]

    def put(
        self,
        stock_code: str,
        data: pd.DataFrame,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        market: str | None = None,
        price_basis: str | None = None,
        record_empty_range: bool = False,
    ) -> None:
        """Atomically merge and persist *data* (and optional coverage bounds).

        Does not mutate *data*.  Concurrent writers for the same cache file
        serialize on a per-file lock, re-read the latest fresh Parquet table +
        coverage intervals, merge rows and intervals, and publish via atomic
        temp-file ``os.replace``.
        """
        has_rows = data is not None and not data.empty
        if not has_rows and not (record_empty_range and start_date and end_date):
            return

        incoming = data.copy() if has_rows else _empty_like(
            list(data.columns) if data is not None and len(data.columns) > 0
            else ("open", "close", "high", "low", "volume", "amount")
        )

        new_intervals: list[tuple[date, date]] = []
        if start_date is not None and end_date is not None:
            s_day = _parse_day(start_date)
            e_day = _parse_day(end_date)
            if s_day <= e_day:
                new_intervals.append((s_day, e_day))
        if has_rows and "date" in incoming.index.names:
            dates = incoming.index.get_level_values("date")
            min_day = pd.Timestamp(dates.min()).date()
            max_day = pd.Timestamp(dates.max()).date()
            if not new_intervals:
                new_intervals.append((min_day, max_day))
            else:
                s_day, e_day = new_intervals[0]
                new_intervals[0] = (min(s_day, min_day), max(e_day, max_day))

        path = self._path_for(stock_code, market=market, price_basis=price_basis)
        lock_path = path.with_name(f".{path.name}.lock")

        with _exclusive_file_lock(lock_path):
            existing_df: pd.DataFrame | None = None
            existing_intervals: list[tuple[date, date]] = []
            eff_market = market
            eff_basis = price_basis

            if path.exists() and self._is_fresh(path):
                loaded = self._read_parquet_with_meta(
                    path,
                    expected_market=market,
                    expected_price_basis=price_basis,
                )
                if loaded is not None:
                    existing_df, existing_intervals, prev_market, prev_basis = loaded
                    if eff_market is None:
                        eff_market = prev_market
                    if eff_basis is None:
                        eff_basis = prev_basis

            if existing_df is not None and not existing_df.empty and has_rows:
                combined = pd.concat([existing_df, incoming])
                combined = combined[~combined.index.duplicated(keep="last")].sort_index()
            elif has_rows:
                combined = incoming[~incoming.index.duplicated(keep="last")].sort_index()
            elif existing_df is not None:
                combined = existing_df
            else:
                combined = incoming

            merged_intervals = _normalize_intervals(existing_intervals + new_intervals)
            self._write_atomic(
                path,
                combined,
                intervals=merged_intervals,
                market=eff_market,
                price_basis=eff_basis,
            )
            logger.debug(
                "Cached %d rows for %s (intervals=%s).",
                len(combined),
                stock_code,
                [(s.isoformat(), e.isoformat()) for s, e in merged_intervals],
            )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _record_hit(self) -> None:
        with self._stats_lock:
            self._hits += 1

    def _record_miss(self) -> None:
        with self._stats_lock:
            self._misses += 1

    def _path_for(
        self,
        stock_code: str,
        *,
        market: str | None = None,
        price_basis: str | None = None,
    ) -> Path:
        safe_code = stock_code.replace("/", "_")
        if market is None and price_basis is None:
            return self._cache_dir / f"{safe_code}.parquet"
        legacy = self._cache_dir / f"{safe_code}.parquet"
        m_tag = (market or "any").lower()
        b_tag = (price_basis or "any").lower()
        scoped = self._cache_dir / f"{safe_code}__{m_tag}__{b_tag}.parquet"
        if scoped.exists():
            return scoped
        if legacy.exists():
            meta = self._peek_meta(legacy)
            if meta is None:
                return legacy
            prev_market = meta.get("market")
            prev_basis = meta.get("price_basis")
            market_ok = prev_market is None or market is None or prev_market == market
            basis_ok = prev_basis is None or price_basis is None or prev_basis == price_basis
            if market_ok and basis_ok:
                return legacy
            return scoped
        return legacy

    @staticmethod
    def _slice_frame(df: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
        if df.empty:
            return df.copy()
        dates = df.index.get_level_values("date")
        mask = (dates >= pd.Timestamp(start)) & (dates <= pd.Timestamp(end))
        return df.loc[mask]

    @staticmethod
    def _compute_missing_intervals(
        requested: tuple[date, date],
        covered: list[tuple[date, date]],
        *,
        market: str | None,
    ) -> list[tuple[date, date]]:
        trimmed_req = _trim_closed_days(requested, market)
        if trimmed_req is None:
            return []
        raw_gaps = _subtract_intervals(trimmed_req, covered)
        gaps: list[tuple[date, date]] = []
        for gap in raw_gaps:
            trimmed_gap = _trim_closed_days(gap, market)
            if trimmed_gap is not None:
                gaps.append(trimmed_gap)
        return gaps

    def _peek_meta(self, path: Path) -> dict[str, object] | None:
        try:
            schema = pq.read_schema(path)
        except Exception:
            return None
        raw_meta = schema.metadata or {}
        payload = raw_meta.get(_METADATA_KEY)
        if not payload:
            return None
        try:
            parsed = json.loads(payload.decode("utf-8"))
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    def _load_state(
        self,
        stock_code: str,
        *,
        expected_market: str | None,
        expected_price_basis: str | None,
    ) -> tuple[pd.DataFrame, list[tuple[date, date]]] | None:
        path = self._path_for(
            stock_code,
            market=expected_market,
            price_basis=expected_price_basis,
        )
        if not path.exists():
            return None
        if not self._is_fresh(path):
            logger.debug("Cache stale for %s, ignoring.", stock_code)
            return None
        loaded = self._read_parquet_with_meta(
            path,
            expected_market=expected_market,
            expected_price_basis=expected_price_basis,
        )
        if loaded is None:
            return None
        df, intervals, _, _ = loaded
        return df, intervals

    def _read_parquet_with_meta(
        self,
        path: Path,
        *,
        expected_market: str | None,
        expected_price_basis: str | None,
    ) -> tuple[pd.DataFrame, list[tuple[date, date]], str | None, str | None] | None:
        try:
            table = pq.read_table(path, use_threads=False)
            df = table.to_pandas()
        except Exception:
            logger.warning("Failed to read cache at %s.", path, exc_info=True)
            return None

        if not isinstance(df.index, pd.MultiIndex):
            if "date" in df.columns and "stock_code" in df.columns:
                df = df.assign(date=pd.to_datetime(df["date"])).set_index(
                    ["date", "stock_code"]
                )
            else:
                return None

        raw_meta = table.schema.metadata or {}
        payload = raw_meta.get(_METADATA_KEY)
        if payload:
            try:
                meta = json.loads(payload.decode("utf-8"))
            except Exception:
                logger.warning("Corrupt cache metadata in %s; falling back to row inference.", path)
                meta = None
        else:
            meta = None

        if isinstance(meta, dict):
            stored_market = meta.get("market")
            stored_basis = meta.get("price_basis")
            if (
                expected_market is not None
                and stored_market is not None
                and stored_market != expected_market
            ):
                return None
            if (
                expected_price_basis is not None
                and stored_basis is not None
                and stored_basis != expected_price_basis
            ):
                return None
            raw_intervals = meta.get("intervals")
            if isinstance(raw_intervals, list):
                parsed_intervals: list[tuple[date, date]] = []
                for item in raw_intervals:
                    if isinstance(item, list | tuple) and len(item) == 2:
                        parsed_intervals.append((_parse_day(item[0]), _parse_day(item[1])))
                return (
                    df,
                    _normalize_intervals(parsed_intervals),
                    stored_market if isinstance(stored_market, str) else None,
                    stored_basis if isinstance(stored_basis, str) else None,
                )

        inferred = _derive_legacy_intervals(df, expected_market)
        return df, inferred, expected_market, expected_price_basis

    @staticmethod
    def _write_atomic(
        path: Path,
        df: pd.DataFrame,
        *,
        intervals: list[tuple[date, date]],
        market: str | None,
        price_basis: str | None,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pandas(df, preserve_index=True)
        meta = dict(table.schema.metadata or {})
        envelope = {
            "version": _METADATA_VERSION,
            "market": market,
            "price_basis": price_basis,
            "intervals": [[s.isoformat(), e.isoformat()] for s, e in intervals],
        }
        meta[_METADATA_KEY] = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
        table = table.replace_schema_metadata(meta)

        fd, tmp_name = tempfile.mkstemp(
            prefix=f".{path.stem}.",
            suffix=".tmp",
            dir=str(path.parent),
        )
        os.close(fd)
        tmp_path = Path(tmp_name)
        try:
            pq.write_table(table, tmp_path)
            os.replace(tmp_path, path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def stats(self) -> dict[str, object]:
        """Return cache hit/miss statistics."""
        with self._stats_lock:
            hits = self._hits
            misses = self._misses
        total = hits + misses
        hit_rate = hits / total if total > 0 else 0.0
        cached_files = [
            p for p in self._cache_dir.glob("*.parquet") if not p.name.startswith(".")
        ]
        return {
            "hits": hits,
            "misses": misses,
            "hit_rate": round(hit_rate, 4),
            "cached_tickers": len(cached_files),
            "freshness_seconds": self._freshness,
            "cache_dir": str(self._cache_dir),
        }

    def _is_fresh(self, path: Path) -> bool:
        age = time.time() - path.stat().st_mtime
        return age < self._freshness
