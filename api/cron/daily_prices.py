# api/cron/daily_prices.py
"""Append daily closes for the universe into daily_prices.

Mirrors the minute_bars cron pattern. Hobby function budget is ~300s, so
this supports limit/offset multi-shot like the other crons.

`period` selects the yfinance history window: the default "5d" is the daily
append (every row in the short window is upserted, which idempotently
refreshes any provisionally-settled recent closes). A longer period (e.g.
"3y") turns the same endpoint into a backfill driver: it must run from the
production backend because local-IP yfinance is rate-limited. Drive a
backfill by curling this endpoint with ?period=3y over offset slices.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any

from alpha_agent.signals.yf_helpers import get_ticker
from alpha_agent.storage.postgres import get_pool
from alpha_agent.storage.queries import upsert_daily_close


async def handler(
    limit: int | None = None,
    offset: int | None = None,
    period: str = "5d",
) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    pool = await get_pool(os.environ["DATABASE_URL"])
    rows = await pool.fetch(
        "SELECT DISTINCT ticker FROM daily_signals_slow ORDER BY ticker"
    )
    tickers = [r["ticker"] for r in rows]
    start = offset if offset is not None else 0
    end = (start + limit) if limit else len(tickers)
    n = 0
    error_count = 0
    errors: list[str] = []
    # Tickers yfinance returned NO usable data for (delisting / ticker change /
    # halt / rate-limit). Previously `if df.empty: continue` dropped these
    # silently, so a feed that died (e.g. HOLX/SEE now return nothing; BK/CTRA
    # stopped on a date) left the ticker's daily_prices frozen with no trace —
    # invisible for weeks, silently degrading the IC + consistency datasets.
    # Record them so the gap is observable in cron_runs (Silent Exception
    # Anti-Pattern): an empty feed is NOT the same as "no close yet today".
    skipped: list[str] = []
    for tk in tickers[start:end]:
        try:
            df = get_ticker(tk).history(period=period)
            if df is None or df.empty:
                skipped.append(tk)
                continue
            # Upsert every row in the window: for "5d" this idempotently
            # refreshes recent closes; for a backfill period it loads history.
            wrote = 0
            for ts, row in df.iterrows():
                close = row.get("Close")
                if close is None:
                    continue
                await upsert_daily_close(pool, tk, ts.date().isoformat(), float(close))
                n += 1
                wrote += 1
            if wrote == 0:
                skipped.append(tk)  # non-empty frame but every Close was null
        except Exception as exc:  # noqa: BLE001
            # Surface per-ticker failures (rate-limit, schema drift) instead of
            # swallowing them: a silent skip is indistinguishable from "no close
            # yet today" and would silently degrade the IC dataset.
            error_count += 1
            if len(errors) < 10:
                errors.append(f"{tk}: {type(exc).__name__}: {exc}")
    # Stamp cron_runs for observability, mirroring the other cron handlers.
    await pool.execute(
        "INSERT INTO cron_runs "
        "(cron_name, started_at, finished_at, ok, error_count, details) "
        "VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
        "daily_prices",
        started_at,
        datetime.now(UTC),
        error_count == 0,
        error_count,
        json.dumps({
            "updated": n,
            "range": [start, end],
            "errors": errors,
            "skipped_count": len(skipped),
            "skipped": skipped[:40],
        }),
    )
    return {
        "cron": "daily_prices",
        "updated": n,
        "range": [start, end],
        "error_count": error_count,
        "errors": errors,
        "skipped_count": len(skipped),
        "skipped": skipped[:40],
    }
