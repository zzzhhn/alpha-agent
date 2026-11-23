"""Inspect one free indicative sample locally. No DB, LLM, broker order or file write."""

from __future__ import annotations

import argparse
import asyncio
import os
from datetime import UTC, datetime

import httpx
from dotenv import load_dotenv

from alpha_agent.data.option_observatory import SYMBOLS, collect


async def main(symbol):
    # Explicit user-invoked local research only; never load dotenv in the API.
    load_dotenv(".env.local", override=False)
    load_dotenv(".env", override=False)
    key, secret = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_API_SECRET")
    if not key or not secret:
        raise SystemExit("Missing local Alpaca research credentials.")
    async with httpx.AsyncClient(
        timeout=6,
        headers={
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
        },
    ) as client:
        try:
            status, sample = await collect(client, symbol, datetime.now(UTC))
        except httpx.HTTPStatusError as exc:
            raise SystemExit(f"Alpaca rejected read: HTTP {exc.response.status_code}") from None
        except httpx.RequestError:
            raise SystemExit("Alpaca read unavailable.") from None
    rows = sample.get("contracts", [])
    print(f"{symbol}: {status}; {len(rows)} indicative contracts; executable=False")
    for row in rows:
        print(
            row["contract"],
            row["quality"],
            "bid/ask",
            row["bid"],
            row["ask"],
            "quote_at",
            row["quote_at"],
            "iv",
            row["iv"],
            "oi",
            row["oi"],
            "oi_as_of",
            row["oi_as_of"],
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("symbol", choices=SYMBOLS)
    asyncio.run(main(parser.parse_args().symbol))
