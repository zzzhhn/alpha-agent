#!/usr/bin/env python3
"""Backfill daily_prices with ~3y of daily closes for the universe.

yfinance daily history is rate-limited on the local IP but works from the
production backend; this script runs LOCALLY against the prod DATABASE_URL,
pulling daily closes via yfinance (period configurable) and upserting them.
Run before the IC loop has any history:

    uv run python scripts/backfill_daily_prices.py --period 3y
    uv run python scripts/backfill_daily_prices.py --period 3y --tickers AAPL,MSFT

Idempotent: ON CONFLICT upsert, so re-running refreshes existing rows.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from alpha_agent.signals.yf_helpers import get_ticker  # noqa: E402
from alpha_agent.storage.postgres import close_pool, get_pool  # noqa: E402
from alpha_agent.storage.queries import upsert_daily_close  # noqa: E402


async def _load_universe(pool) -> list[str]:
    """Universe = distinct tickers in daily_signals_slow (~557), the same
    source the minute_bars cron uses for deterministic coverage."""
    rows = await pool.fetch(
        "SELECT DISTINCT ticker FROM daily_signals_slow ORDER BY ticker"
    )
    return [r["ticker"] for r in rows]


async def _backfill_one(pool, ticker: str, period: str) -> int:
    df = get_ticker(ticker).history(period=period)
    if df is None or df.empty:
        return 0
    n = 0
    for ts, row in df.iterrows():
        close = row.get("Close")
        if close is None:
            continue
        await upsert_daily_close(pool, ticker, ts.date().isoformat(), float(close))
        n += 1
    return n


async def main(tickers: list[str], period: str) -> None:
    load_dotenv(ROOT / ".env")
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        sys.exit("DATABASE_URL not set. Add it to .env before running.")
    pool = await get_pool(db_url)
    if not tickers:
        tickers = await _load_universe(pool)
    try:
        total = 0
        for tk in tickers:
            try:
                n = await _backfill_one(pool, tk, period)
                total += n
                print(f"{tk}: {n} closes")
            except Exception as exc:  # noqa: BLE001
                print(f"{tk}: FAILED {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"Done: {total} closes across {len(tickers)} tickers.")
    finally:
        await close_pool()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="3y")
    ap.add_argument("--tickers", default="")
    args = ap.parse_args()
    tk = [t for t in args.tickers.split(",") if t.strip()] if args.tickers else []
    asyncio.run(main(tk, args.period))
