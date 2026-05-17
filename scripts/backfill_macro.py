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
import sys
from datetime import UTC, datetime, timedelta

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Local-driver httpx-client patch (must run BEFORE adapter imports so that
# any module-level binding of make_client picks up the patched version).
#
# Why: on macOS, ClashX/Surge set a system-level HTTPS proxy (e.g.
# 127.0.0.1:7897) that httpx automatically reads through urllib's
# getproxies_macosx_sysconf. Default behaviour produces two failure
# modes from CN:
#   - federalreserve.gov: Clash node fails TLS handshake (EndOfStream)
#   - ofac.treasury.gov:  direct from CN ConnectTimeouts (GFW drops IP)
# Solution: build the AsyncClient with trust_env=False and explicit
# per-host mounts:
#   - default route -> Clash proxy (handles CNN GFW block + OFAC reach)
#   - federalreserve.gov -> None (direct, bypass Clash for TLS fidelity)
# Vercel runtime has no system proxy and is unaffected; the production
# cron uses the unpatched base.make_client.
# ---------------------------------------------------------------------------
import httpx

from alpha_agent.news import base as _news_base

_LOCAL_PROXY_URL = "http://127.0.0.1:7897"


def _local_driver_make_client(timeout_seconds: float = 10.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=httpx.Timeout(timeout_seconds, connect=10.0),
        follow_redirects=True,
        headers={"User-Agent": "alpha-agent-news/1.0 (+https://alpha.bobbyzhong.com)"},
        trust_env=False,
        mounts={
            "all://": httpx.AsyncHTTPTransport(proxy=_LOCAL_PROXY_URL),
            "all://*federalreserve.gov": None,
        },
    )


_news_base.make_client = _local_driver_make_client

# Adapter imports must come after the patch so their __init__ sees it.
from alpha_agent.news.fed_adapter import FedRSSAdapter  # noqa: E402
from alpha_agent.news.ofac_adapter import OFACRSSAdapter  # noqa: E402
from alpha_agent.news.queries import upsert_macro_events  # noqa: E402
from alpha_agent.news.truth_adapter import TruthSocialAdapter  # noqa: E402
from alpha_agent.storage.postgres import get_pool  # noqa: E402


async def main(days: int, skip: set[str]) -> None:
    load_dotenv()
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        sys.exit(
            "DATABASE_URL not set. Add it to .env in repo root or export it before running."
        )
    pool = await get_pool(db_url)
    since = datetime.now(UTC) - timedelta(days=days)
    all_adapters = [TruthSocialAdapter(), FedRSSAdapter(), OFACRSSAdapter()]
    adapters = [a for a in all_adapters if a.name not in skip]
    skipped = [a.name for a in all_adapters if a.name in skip]
    if skipped:
        print(f"skipping: {', '.join(skipped)}")
    total = 0
    try:
        for a in adapters:
            try:
                events = await a.fetch(since=since)
                n = await upsert_macro_events(pool, events)
                print(f"{a.name}: pulled={len(events)} inserted={n}")
                total += n
            except Exception as exc:
                print(f"{a.name}: FAILED ({type(exc).__name__}: {exc})")
    finally:
        for a in all_adapters:
            await a.aclose()
    print(f"total new macro_events: {total}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30)
    p.add_argument(
        "--skip",
        default="",
        help="Comma-separated adapter names to skip, e.g. 'ofac_rss,truth_social'.",
    )
    args = p.parse_args()
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    asyncio.run(main(args.days, skip))
