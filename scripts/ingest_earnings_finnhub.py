#!/usr/bin/env python3
"""Ingest Finnhub earnings-surprise inputs for the universe into Neon.

Runs OUTSIDE the Vercel cron (daily on GitHub Actions). yfinance gave usable
earnings for only ~21/557 tickers; Finnhub's free tier covers the universe.
Writes earnings_finnhub; the signal crons read that table.

    FINNHUB_API_KEY=... DATABASE_URL=... python scripts/ingest_earnings_finnhub.py
    python scripts/ingest_earnings_finnhub.py --limit 20   # smoke test
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from alpha_agent.signals.finnhub_earnings import (  # noqa: E402
    fetch_surprise,
    load_upcoming_map,
)
from alpha_agent.storage.postgres import get_pool  # noqa: E402
from alpha_agent.storage.queries import upsert_earnings_finnhub  # noqa: E402
from alpha_agent.universe import SP500_UNIVERSE  # noqa: E402


async def main(limit: int) -> None:
    load_dotenv(ROOT / ".env")
    db_url = os.environ.get("DATABASE_URL")
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not db_url:
        sys.exit("DATABASE_URL not set.")
    if not api_key:
        sys.exit("FINNHUB_API_KEY not set.")
    pool = await get_pool(db_url)
    as_of = datetime.now(UTC)
    tickers = SP500_UNIVERSE[:limit] if limit else SP500_UNIVERSE

    written = with_surprise = failed = 0
    try:
        # trust_env=False: avoid a misconfigured local system proxy (resets TLS
        # on macOS); GHA egress is direct so it's correct there too.
        with httpx.Client(trust_env=False) as client:
            upcoming = load_upcoming_map(client, api_key, as_of)
            print(f"upcoming map: {len(upcoming)} symbols; processing {len(tickers)}.")
            for i, ticker in enumerate(tickers, 1):
                try:
                    surp = fetch_surprise(client, api_key, ticker)
                except Exception as exc:  # noqa: BLE001 - log + continue
                    failed += 1
                    print(f"  FAIL {ticker}: {type(exc).__name__}: {exc}",
                          file=sys.stderr)
                    continue
                up = upcoming.get(ticker.upper(), {})
                if surp is None and not up:
                    continue
                surp = surp or {}
                await upsert_earnings_finnhub(
                    pool, ticker,
                    surp.get("recent_surprise"), surp.get("sigma"),
                    surp.get("report_date"), up.get("next_date"),
                    up.get("eps_estimate"), up.get("revenue_estimate"),
                )
                written += 1
                if surp.get("recent_surprise") is not None:
                    with_surprise += 1
                if i % 50 == 0:
                    print(f"  ...{i}/{len(tickers)} ({with_surprise} with surprise)")
        print(f"\nDone. written={written} with_surprise={with_surprise} failed={failed}")
    finally:
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="0 = full universe")
    asyncio.run(main(**vars(ap.parse_args())))
