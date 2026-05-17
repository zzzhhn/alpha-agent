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


def _yf_history(ticker: str) -> pd.DataFrame:
    """Indirection layer so tests can monkeypatch."""
    return yf.Ticker(ticker).history(period=_PERIOD, interval=_INTERVAL)


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
