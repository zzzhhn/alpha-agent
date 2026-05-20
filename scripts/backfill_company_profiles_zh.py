#!/usr/bin/env python3
"""Backfill Chinese translations for company_profiles.summary_zh.

The platform holds no global LLM key (BYOK only), so the Chinese summary
can't be produced in the request path. This offline script translates each
English summary via the local `claude` CLI (reuses the Claude Code OAuth
session — no API key needed) and writes summary_zh into the DB.

Run locally with the prod DATABASE_URL in .env:

    uv run python scripts/backfill_company_profiles_zh.py
    uv run python scripts/backfill_company_profiles_zh.py --tickers AAPL,MSFT,NVDA
    uv run python scripts/backfill_company_profiles_zh.py --limit 50

  --tickers  pre-fetch English profiles for these tickers (via yfinance)
             before translating, so they exist in the table even if no one
             has browsed them yet. Without it, only already-cached rows
             (lazy-filled by /profile views) get translated.
  --limit    cap how many rows to translate this run (default 1000).

Idempotent: only rows with summary_en and no summary_zh are translated, so
re-running picks up where it left off.
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

from alpha_agent.signals.yf_helpers import extract_profile, get_ticker  # noqa: E402
from alpha_agent.storage.postgres import get_pool  # noqa: E402
from alpha_agent.storage.queries import (  # noqa: E402
    list_profiles_missing_zh,
    set_company_profile_zh,
    upsert_company_profile_en,
)

_PROMPT = (
    "Translate the following public-company business summary into natural, "
    "professional Simplified Chinese suitable for an investment research UI. "
    "Keep ticker symbols, product names, and figures intact. Output ONLY the "
    "translation — no preamble, no quotes, no explanation.\n\n"
)


def _translate(summary_en: str) -> str | None:
    """Translate via the local claude CLI. Returns None on failure."""
    try:
        proc = subprocess.run(
            ["claude", "-p", _PROMPT + summary_en],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"  claude CLI error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return None
    if proc.returncode != 0:
        print(f"  claude exited {proc.returncode}: {proc.stderr[:200]}", file=sys.stderr)
        return None
    out = proc.stdout.strip()
    return out or None


async def _prefetch_en(pool, tickers: list[str]) -> None:
    for tk in tickers:
        tk = tk.strip().upper()
        if not tk:
            continue
        try:
            prof = extract_profile(get_ticker(tk).info or {})
            await upsert_company_profile_en(
                pool, tk,
                name=prof["name"], sector=prof["sector"],
                industry=prof["industry"], summary_en=prof["summary"],
                website=prof["website"], country=prof["country"],
                employees=prof["employees"],
            )
            print(f"  prefetched EN: {tk}" + ("" if prof["summary"] else " (no summary)"))
        except Exception as exc:  # noqa: BLE001
            print(f"  prefetch failed {tk}: {type(exc).__name__}: {exc}", file=sys.stderr)


async def main(tickers: list[str], limit: int) -> None:
    load_dotenv(ROOT / ".env")
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        sys.exit("DATABASE_URL not set. Add it to .env or export it before running.")
    pool = await get_pool(db_url)
    try:
        if tickers:
            print(f"Pre-fetching EN for {len(tickers)} ticker(s)...")
            await _prefetch_en(pool, tickers)
        rows = await list_profiles_missing_zh(pool, limit)
        print(f"{len(rows)} row(s) need a Chinese translation.")
        ok = 0
        for r in rows:
            tk, en = r["ticker"], r["summary_en"]
            print(f"translating {tk} ({len(en)} chars)...")
            zh = _translate(en)
            if zh:
                await set_company_profile_zh(pool, tk, zh)
                ok += 1
            else:
                print(f"  skipped {tk} (translation failed)")
        print(f"Done: {ok}/{len(rows)} translated.")
    finally:
        await pool.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default="", help="comma-separated tickers to pre-fetch EN for")
    ap.add_argument("--limit", type=int, default=1000)
    args = ap.parse_args()
    tickers = [t for t in args.tickers.split(",") if t.strip()] if args.tickers else []
    asyncio.run(main(tickers, args.limit))
