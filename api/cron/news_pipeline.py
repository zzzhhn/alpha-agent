"""Three cron handlers for the news pipeline.

per_ticker_handler: walks 557 SP500 tickers + watchlist extras, calls
    PerTickerAggregator(Finnhub, FMP, RSS) for each, upserts.
macro_handler: parallel poll of TruthSocial + Fed + OFAC, upserts.
llm_enrich_handler: picks 100 rows with llm_processed_at IS NULL,
    batches them through the BYOK LiteLLM client, writes results back.

Each handler returns a dict for the GH Actions step summary and stamps
a row into cron_runs.
"""
from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from typing import Any

from alpha_agent.news.aggregator import MacroAggregator, PerTickerAggregator
from alpha_agent.news.fed_adapter import FedRSSAdapter
from alpha_agent.news.finnhub_adapter import FinnhubAdapter
from alpha_agent.news.fmp_adapter import FMPAdapter
from alpha_agent.news.llm_worker import enrich_pending
from alpha_agent.news.ofac_adapter import OFACRSSAdapter
from alpha_agent.news.queries import upsert_macro_events, upsert_news_items
from alpha_agent.news.rss_adapter import RSSAdapter
from alpha_agent.news.truth_adapter import TruthSocialAdapter
from alpha_agent.orchestrator.batch_runner import run_batched
from alpha_agent.storage.postgres import get_pool


def _per_ticker_aggregator() -> PerTickerAggregator:
    return PerTickerAggregator([
        FinnhubAdapter(api_key=os.environ["FINNHUB_API_KEY"]),
        FMPAdapter(api_key=os.environ["FMP_API_KEY"]),
        RSSAdapter(),
    ])


def _macro_aggregator() -> MacroAggregator:
    return MacroAggregator([
        TruthSocialAdapter(),
        FedRSSAdapter(),
        OFACRSSAdapter(),
    ])


async def _record_cron(pool, name: str, started_at, rows_written: int,
                       errors: list[dict]) -> None:
    await pool.execute(
        "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, "
        "error_count, details) VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
        name, started_at, datetime.now(UTC),
        len(errors) == 0, len(errors),
        json.dumps({"rows_written": rows_written}),
    )


async def per_ticker_handler(
    limit: int | None = None, offset: int | None = None
) -> dict[str, Any]:
    from alpha_agent.universe import get_watchlist

    pool = await get_pool(os.environ["DATABASE_URL"])
    started_at = datetime.now(UTC)
    since = started_at - timedelta(hours=24)
    universe = get_watchlist(top_n=limit if limit else 100, offset=offset or 0)
    if (offset or 0) == 0:
        wl_rows = await pool.fetch("SELECT DISTINCT ticker FROM user_watchlist")
        extras = {r["ticker"] for r in wl_rows} - set(universe)
        universe = universe + sorted(extras)

    agg = _per_ticker_aggregator()
    errors: list[dict] = []
    rows_written = 0

    async def _one(t: str) -> int:
        try:
            items = await agg.fetch(ticker=t, since=since)
        except Exception as exc:
            errors.append({"ticker": t, "err": f"{type(exc).__name__}: {exc}"[:200]})
            return 0
        return await upsert_news_items(pool, items)

    results = await run_batched(universe, _one, batch_size=20)
    rows_written = sum(v for v in results.values() if isinstance(v, int))
    await agg.aclose()
    await _record_cron(pool, "news_per_ticker", started_at, rows_written, errors)
    return {"ok": True, "rows_written": rows_written, "errors": errors[:5]}


async def macro_handler() -> dict[str, Any]:
    pool = await get_pool(os.environ["DATABASE_URL"])
    started_at = datetime.now(UTC)
    since = started_at - timedelta(hours=24)
    agg = _macro_aggregator()
    try:
        events = await agg.fetch_all(since=since)
    finally:
        await agg.aclose()
    rows_written = await upsert_macro_events(pool, events)
    await _record_cron(pool, "news_macro", started_at, rows_written, [])
    return {"ok": True, "rows_written": rows_written, "errors": []}


async def llm_enrich_handler() -> dict[str, Any]:
    pool = await get_pool(os.environ["DATABASE_URL"])
    started_at = datetime.now(UTC)
    n_processed, n_failed = await enrich_pending(pool, row_limit=100)
    await _record_cron(
        pool, "news_llm_enrich", started_at, n_processed,
        [{"failed_batches": n_failed}] if n_failed else [],
    )
    return {"ok": True, "processed": n_processed, "failed_batches": n_failed}
