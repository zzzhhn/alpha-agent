#!/usr/bin/env python3
"""Parallel summary_zh backfill — same translation as
backfill_company_profiles_zh.py but runs N claude-CLI calls concurrently so
500 companies finish in minutes, not hours. Each summary is still translated in
its own CLI call (long paragraphs don't batch safely), just many at once.

    uv run python scripts/backfill_summaries_zh_parallel.py --concurrency 8
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from alpha_agent.storage.postgres import get_pool  # noqa: E402
from alpha_agent.storage.queries import (  # noqa: E402
    list_profiles_missing_zh,
    set_company_profile_zh,
)

_PROMPT = (
    "Translate the following public-company business summary into natural, "
    "professional Simplified Chinese suitable for an investment research UI. "
    "Keep ticker symbols, product names, and figures intact. Output ONLY the "
    "translation — no preamble, no quotes, no explanation.\n\n"
)


def _translate(summary_en: str) -> str | None:
    try:
        # Use a fast model: translation is a simple task and the default
        # (Opus) made each call ~3min, dominated by session startup. Sonnet
        # cuts per-call latency several-fold at no quality cost for prose.
        proc = subprocess.run(
            ["claude", "-p", "--model", "claude-sonnet-4-6", _PROMPT + summary_en],
            capture_output=True, text=True, timeout=180,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


async def main(concurrency: int, limit: int) -> None:
    load_dotenv(ROOT / ".env")
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        sys.exit("DATABASE_URL not set.")
    pool = await get_pool(db_url)
    sem = asyncio.Semaphore(concurrency)
    done = 0
    failed = 0

    try:
        rows = await list_profiles_missing_zh(pool, limit)
        print(f"{len(rows)} summaries to translate, {concurrency} at a time.")

        async def one(r) -> None:
            nonlocal done, failed
            async with sem:
                zh = await asyncio.to_thread(_translate, r["summary_en"])
            if zh:
                await set_company_profile_zh(pool, r["ticker"], zh)
                done += 1
                if done % 20 == 0:
                    print(f"  ...{done} done")
            else:
                failed += 1
                print(f"  FAIL {r['ticker']}", file=sys.stderr)

        await asyncio.gather(*(one(r) for r in rows))
        print(f"\nDone. {done} translated, {failed} failed (re-run picks up fails).")
    finally:
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--limit", type=int, default=1000)
    asyncio.run(main(**vars(ap.parse_args())))
