# api/cron/daily_prices.py
"""Daily append of today's close for the universe into daily_prices.

Mirrors the minute_bars cron pattern. Hobby function budget is ~300s, so
this supports limit/offset multi-shot like the other crons.
"""
from __future__ import annotations

import os
from typing import Any

from alpha_agent.signals.yf_helpers import get_ticker
from alpha_agent.storage.postgres import get_pool
from alpha_agent.storage.queries import upsert_daily_close


async def handler(limit: int | None = None, offset: int | None = None) -> dict[str, Any]:
    pool = await get_pool(os.environ["DATABASE_URL"])
    rows = await pool.fetch(
        "SELECT DISTINCT ticker FROM daily_signals_slow ORDER BY ticker"
    )
    tickers = [r["ticker"] for r in rows]
    start = offset or 0
    end = (start + limit) if limit else len(tickers)
    n = 0
    error_count = 0
    errors: list[str] = []
    for tk in tickers[start:end]:
        try:
            # 5d window ensures a row exists even on Mondays / post-holiday.
            df = get_ticker(tk).history(period="5d")
            if df is None or df.empty:
                continue
            ts = df.index[-1]
            close = df["Close"].iloc[-1]
            await upsert_daily_close(pool, tk, ts.date().isoformat(), float(close))
            n += 1
        except Exception as exc:  # noqa: BLE001
            # Surface per-ticker failures (rate-limit, schema drift) instead of
            # swallowing them: a silent skip is indistinguishable from "no close
            # yet today" and would silently degrade the IC dataset.
            error_count += 1
            if len(errors) < 10:
                errors.append(f"{tk}: {type(exc).__name__}: {exc}")
    return {
        "cron": "daily_prices",
        "updated": n,
        "range": [start, end],
        "error_count": error_count,
        "errors": errors,
    }
