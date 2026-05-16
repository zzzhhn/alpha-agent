"""One-shot macro backfill: pull last N days of Truth Social + Fed + OFAC
and upsert into macro_events with llm_processed_at NULL. The
news_llm_enrich cron will pick them up over the following cycles.

Usage:
    python scripts/backfill_macro.py --days 30
"""
from __future__ import annotations

import argparse
import asyncio
import os
from datetime import UTC, datetime, timedelta

from alpha_agent.news.fed_adapter import FedRSSAdapter
from alpha_agent.news.ofac_adapter import OFACRSSAdapter
from alpha_agent.news.queries import upsert_macro_events
from alpha_agent.news.truth_adapter import TruthSocialAdapter
from alpha_agent.storage.postgres import get_pool


async def main(days: int) -> None:
    pool = await get_pool(os.environ["DATABASE_URL"])
    since = datetime.now(UTC) - timedelta(days=days)
    adapters = [TruthSocialAdapter(), FedRSSAdapter(), OFACRSSAdapter()]
    total = 0
    try:
        for a in adapters:
            events = await a.fetch(since=since)
            n = await upsert_macro_events(pool, events)
            print(f"{a.name}: pulled={len(events)} inserted={n}")
            total += n
    finally:
        for a in adapters:
            await a.aclose()
    print(f"total new macro_events: {total}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30)
    args = p.parse_args()
    asyncio.run(main(args.days))
