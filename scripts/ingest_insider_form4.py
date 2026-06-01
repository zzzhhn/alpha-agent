#!/usr/bin/env python3
"""Ingest SEC EDGAR Form 4 net insider value for the whole universe -> Neon.

Runs OUTSIDE the Vercel cron (daily on GitHub Actions, or locally) because the
universe needs thousands of rate-limited SEC requests, which does not fit the
300s function budget. Writes insider_form4; the signal crons read that table.

    DATABASE_URL=... python scripts/ingest_insider_form4.py
    python scripts/ingest_insider_form4.py --limit 20   # smoke test
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

from alpha_agent.signals.insider_edgar import (  # noqa: E402
    SEC_HEADERS,
    fetch_form4_net,
    load_cik_map,
)
from alpha_agent.storage.postgres import get_pool  # noqa: E402
from alpha_agent.storage.queries import upsert_insider_form4  # noqa: E402
from alpha_agent.universe import SP500_UNIVERSE  # noqa: E402


async def main(limit: int, window_days: int) -> None:
    load_dotenv(ROOT / ".env")
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        sys.exit("DATABASE_URL not set.")
    pool = await get_pool(db_url)
    as_of = datetime.now(UTC)
    tickers = SP500_UNIVERSE[:limit] if limit else SP500_UNIVERSE

    written = nonzero = no_cik = failed = 0
    try:
        # trust_env=False: SEC is directly reachable; a misconfigured system
        # proxy (seen locally on macOS) resets the TLS handshake to sec.gov.
        # On GHA egress is direct anyway, so this is correct in both places.
        with httpx.Client(headers=SEC_HEADERS, trust_env=False) as client:
            cik_map = load_cik_map(client)
            print(f"CIK map: {len(cik_map)} tickers; processing {len(tickers)}.")
            for i, ticker in enumerate(tickers, 1):
                cik = cik_map.get(ticker.upper())
                if not cik:
                    no_cik += 1
                    continue
                try:
                    net, n = await asyncio.to_thread(
                        fetch_form4_net, client, cik, as_of, window_days
                    )
                except Exception as exc:  # noqa: BLE001 - log + continue, see below
                    failed += 1
                    print(f"  FAIL {ticker}: {type(exc).__name__}: {exc}",
                          file=sys.stderr)
                    continue
                await upsert_insider_form4(pool, ticker, net, n)
                written += 1
                if n > 0:
                    nonzero += 1
                if i % 50 == 0:
                    print(f"  ...{i}/{len(tickers)} ({nonzero} with filings)")
        print(
            f"\nDone. written={written} nonzero={nonzero} "
            f"no_cik={no_cik} failed={failed}"
        )
    finally:
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="0 = full universe")
    ap.add_argument("--window-days", type=int, default=30)
    asyncio.run(main(**{k.replace("-", "_"): v for k, v in vars(ap.parse_args()).items()}))
