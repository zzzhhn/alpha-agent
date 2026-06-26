"""yfinance 1-minute bar puller + Neon storage + event-window query.

Backs the event-study CAR calculator. yfinance only retains 1m bars for
the last 7-30 days, so this module is deliberately a rolling cache
not a historical archive. Events older than 30 days fall back to
daily-level handling in caller modules.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd
import yfinance as yf


_PERIOD = "7d"      # yfinance 1m bar max retention
_INTERVAL = "1m"

# DB-side retention for the minute_bars rolling cache. Tightened from 7 to 2
# days after the 2026-06-26 incident: ~557 tickers x ~390 bars/session is
# ~200K rows/day; a 7-day window held ~1.4M rows / ~324MB and, on the 512MB
# Neon free tier, crowded out every other table's writes — producing
# asyncpg.DiskFullError on news_macro / fast_intraday / slow_daily, which
# surfaced as unhandled 500s and flooded GH Actions with cron-failure emails.
# The intraday signals only consume the last 1-2 sessions, so 2 days is ample
# and keeps the table near ~100MB with headroom for the rest of the schema.
MINUTE_BARS_RETENTION_DAYS = 2


def _yf_history(ticker: str) -> pd.DataFrame:
    """Indirection layer so tests can monkeypatch."""
    return yf.Ticker(ticker).history(period=_PERIOD, interval=_INTERVAL)


async def prune_minute_bars(pool) -> str:
    """Delete minute_bars older than MINUTE_BARS_RETENTION_DAYS.

    Parameterized interval (make_interval) so the window can never drift from
    the constant. DELETE does not extend the file, so this is safe to run even
    when the DB is at its size limit (it is the operation that frees space).
    Returns asyncpg's status string (e.g. "DELETE 12345")."""
    return await pool.execute(
        "DELETE FROM minute_bars WHERE ts < now() - make_interval(days => $1)",
        MINUTE_BARS_RETENTION_DAYS,
    )


async def pull_and_store_minute_bars(pool, ticker: str) -> int:
    """Pull last 7 days of 1m bars for ticker, upsert into minute_bars.
    Returns number of rows upserted. Idempotent via ON CONFLICT."""
    df = _yf_history(ticker)
    if df is None or df.empty:
        return 0
    rows = [
        (
            ticker.upper(),
            ts.to_pydatetime().astimezone(UTC),
            float(row["Open"]) if pd.notna(row["Open"]) else None,
            float(row["High"]) if pd.notna(row["High"]) else None,
            float(row["Low"])  if pd.notna(row["Low"])  else None,
            float(row["Close"])if pd.notna(row["Close"])else None,
            int(row["Volume"]) if pd.notna(row["Volume"]) else 0,
        )
        for ts, row in df.iterrows()
    ]
    await pool.executemany(
        """
        INSERT INTO minute_bars
            (ticker, ts, open, high, low, close, volume)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (ticker, ts) DO UPDATE SET
            open = EXCLUDED.open, high = EXCLUDED.high,
            low  = EXCLUDED.low,  close = EXCLUDED.close,
            volume = EXCLUDED.volume, fetched_at = now()
        """,
        rows,
    )
    return len(rows)


async def get_bars_for_event(
    pool, ticker: str, event_ts: datetime, window_min: int = 60,
) -> pd.DataFrame:
    """Return DataFrame of (ts, close) for window_min after event_ts.
    Empty DataFrame if event is more than 30 days old or no bars in window."""
    if event_ts < datetime.now(UTC) - timedelta(days=30):
        return pd.DataFrame(columns=["ts", "close"])
    end = event_ts + timedelta(minutes=window_min)
    rows = await pool.fetch(
        """
        SELECT ts, close FROM minute_bars
        WHERE ticker = $1 AND ts BETWEEN $2 AND $3
        ORDER BY ts
        """,
        ticker.upper(), event_ts, end,
    )
    if not rows:
        return pd.DataFrame(columns=["ts", "close"])
    return pd.DataFrame(
        [(r["ts"], float(r["close"]) if r["close"] is not None else None) for r in rows],
        columns=["ts", "close"],
    )
