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
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from alpha_agent.market_session import _xnys_calendar
from alpha_agent.news.aggregator import MacroAggregator, PerTickerAggregator
from alpha_agent.news.fed_adapter import FedRSSAdapter
from alpha_agent.news.finnhub_adapter import FinnhubAdapter
from alpha_agent.news.fmp_adapter import FMPAdapter
from alpha_agent.news.ofac_adapter import OFACRSSAdapter
from alpha_agent.news.queries import upsert_macro_events, upsert_news_items
from alpha_agent.news.rss_adapter import RSSAdapter
from alpha_agent.news.truth_adapter import TruthSocialAdapter
from alpha_agent.orchestrator.batch_runner import run_batched
from alpha_agent.storage.postgres import get_pool

_NEWS_ROTATION_SIZE = 150  # two scheduled 75-ticker shards
_NEWS_WINDOW = timedelta(days=7)
_PER_TICKER_CAP = 20
_ROTATION_EPOCH = date(2026, 1, 2)
_NEW_YORK = ZoneInfo('America/New_York')


def rotating_news_universe(universe: list[str], at: datetime) -> tuple[date, list[str]]:
    """Deterministic contiguous rotation by XNYS trading-day ordinal.

    The fixed origin makes the same session repeatable across requests. Weekends
    and exchange holidays do not consume a day's slice; manual runs reuse the
    preceding session on non-trading days.
    """
    calendar = _xnys_calendar()
    session = calendar.date_to_session(at.astimezone(_NEW_YORK).date(), direction='previous')
    origin = calendar.date_to_session(_ROTATION_EPOCH)
    ordinal = calendar.sessions.get_loc(session) - calendar.sessions.get_loc(origin)
    start = (ordinal * _NEWS_ROTATION_SIZE) % len(universe) if universe else 0
    return session.date(), universe[start:] + universe[:start]


def _per_ticker_aggregator() -> PerTickerAggregator:
    # Graceful skip on missing API keys. The platform runs in BYOK mode for
    # LLM calls (no global key by design — see feedback_byok_cron_architectural_tension.md);
    # the same constraint applies to platform news adapters when an env var
    # is intentionally unset. Hard `os.environ["X"]` raises KeyError → 500
    # on every shard, silently leaving news_items empty (observed 2026-05-18).
    # RSS has no key and is always included.
    adapters: list = []
    if finnhub_key := os.environ.get("FINNHUB_API_KEY"):
        adapters.append(FinnhubAdapter(api_key=finnhub_key))
    if fmp_key := os.environ.get("FMP_API_KEY"):
        adapters.append(FMPAdapter(api_key=fmp_key))
    adapters.append(RSSAdapter())
    return PerTickerAggregator(adapters)


def _macro_aggregator() -> MacroAggregator:
    return MacroAggregator([
        TruthSocialAdapter(),
        FedRSSAdapter(),
        OFACRSSAdapter(),
    ])


async def _record_cron(pool, name: str, started_at, rows_written: int,
                       errors: list[dict], **details) -> None:
    await pool.execute(
        "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, "
        "error_count, details) VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
        name, started_at, datetime.now(UTC),
        len(errors) == 0, len(errors),
        json.dumps({"rows_written": rows_written, **details}),
    )


async def per_ticker_handler(
    limit: int | None = None, offset: int | None = None
) -> dict[str, Any]:
    from alpha_agent.universe import get_watchlist

    pool = await get_pool(os.environ["DATABASE_URL"])
    started_at = datetime.now(UTC)
    since = started_at - _NEWS_WINDOW
    session_date, rotation = rotating_news_universe(get_watchlist(top_n=600), started_at)
    shard_start = offset or 0
    universe = rotation[shard_start:shard_start + (limit or 100)]
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
        observed_at = datetime.now(UTC)
        recent = sorted((item for item in items if since <= item.published_at <= observed_at),
                        key=lambda item: item.published_at, reverse=True)[:_PER_TICKER_CAP]
        return await upsert_news_items(pool, recent)

    results = await run_batched(universe, _one, batch_size=20)
    rows_written = sum(v for v in results.values() if isinstance(v, int))
    await agg.aclose()
    await _record_cron(pool, "news_per_ticker", started_at, rows_written, errors,
                       market_session=session_date.isoformat(), offset=shard_start, tickers_scanned=len(universe))
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


# llm_enrich_handler removed 2026-05-17 - BYOK architecture requires
# user-context (which cron does not have). Read-time replacement lives
# in alpha_agent/api/routes/news_enrich.py + enrich_news_for_ticker
# in llm_worker.py.
