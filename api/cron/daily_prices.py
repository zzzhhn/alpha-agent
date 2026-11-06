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
import math
import os
from datetime import UTC, datetime
from typing import Any

from alpha_agent.signals.yf_helpers import get_ticker
from alpha_agent.storage.postgres import get_pool
from alpha_agent.storage.queries import upsert_daily_close
from alpha_agent.data.research_refresh import price_universe
from alpha_agent.market_session import latest_completed_xnys_session


async def handler(
    limit: int | None = None,
    offset: int | None = None,
    period: str = "5d",
) -> dict[str, Any]:
    started_at = datetime.now(UTC)
    pool = await get_pool(os.environ["DATABASE_URL"])
    tickers = await price_universe(pool)
    expected_date = latest_completed_xnys_session(started_at)
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
                if close is None or not math.isfinite(float(close)) or float(close) <= 0:
                    continue
                # Intraday history may include today's unfinished candle. It is
                # not a settled daily close and must not advance ledger dates.
                if ts.date() > expected_date:
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
    # Materialize consistency outcomes now that today's closes (and thus
    # yesterday's realized next-day returns) are in — keeps the durable
    # consistency_outcomes history current so daily_signals_slow/fast can be
    # pruned in a future disk emergency without losing 历史一致性. Keep any
    # successfully fetched prices, but expose materialization errors in job health.
    consistency_materialized = 0
    try:
        from alpha_agent.backtest.consistency import materialize_outcomes
        consistency_materialized = await materialize_outcomes(pool, tickers=tickers[start:end])
    except Exception as exc:  # noqa: BLE001
        error_count += 1
        errors.append(f"consistency_materialize: {type(exc).__name__}: {exc}")

    fresh_rows = await pool.fetch(
        "SELECT ticker FROM daily_prices WHERE date=$1 AND ticker=ANY($2::text[]) AND close>0",
        expected_date, tickers[start:end],
    )
    fresh_tickers = {r["ticker"] for r in fresh_rows}
    freshness = {
        "expected_market_date": expected_date.isoformat(),
        "requested_count": len(tickers[start:end]),
        "fresh_count": len(fresh_tickers),
        "stale_tickers": [tk for tk in tickers[start:end] if tk not in fresh_tickers][:40],
        "price_universe_count": len(tickers),
    }
    # `updated` is retained for existing clients; it counts valid rows offered
    # to the idempotent upsert, not changed rows or fresh ticker coverage.
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
            "rows_processed": n,
            **freshness,
            "range": [start, end],
            "errors": errors,
            "skipped_count": len(skipped),
            "skipped": skipped[:40],
            "consistency_materialized": consistency_materialized,
        }),
    )
    return {
        "cron": "daily_prices",
        "updated": n,
        "rows_processed": n,
        **freshness,
        "range": [start, end],
        "error_count": error_count,
        "errors": errors,
        "skipped_count": len(skipped),
        "skipped": skipped[:40],
        "consistency_materialized": consistency_materialized,
    }
