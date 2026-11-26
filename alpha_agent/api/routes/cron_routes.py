"""FastAPI cron endpoints (M2 fixup for Vercel deployment).

Background: M2 originally placed cron handlers at `api/cron/*.py` as standalone
Vercel serverless functions. They had a non-standard `async def handler() -> dict`
signature that Vercel's Python runtime can't invoke. Combined with the catchall
`/api/(.*)` rewrite forwarding every request to `api/index.py`, the cron files
were never reachable as deployed URLs.

Fix: expose 3 POST routes here that thin-wrap the M2 handlers. The existing
rewrite captures /api/cron/* and routes to FastAPI, which dispatches here.
Vercel cron config (vercel.json) keeps the same paths.

Each route returns the handler's dict directly (200 with {ok, ...}).
"""
from __future__ import annotations

import json
import os
import time
from bisect import bisect_right
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query

from alpha_agent.auth.dependencies import require_cron
from alpha_agent.scheduling.ticks import Job
from alpha_agent.storage.postgres import get_pool

router = APIRouter(
    prefix="/api/cron",
    tags=["cron"],
    dependencies=[Depends(require_cron)],
)


@router.get("/tick/{job}")
async def cron_tick(job: Job) -> dict[str, Any]:
    """Advance a bounded scheduled job from durable receipts; no in-tick retry."""
    from alpha_agent.api.dependencies import get_db_pool
    from alpha_agent.scheduling.runner import run_tick

    return await run_tick(job, await get_db_pool())


@router.get("/dispatch/{workflow}")
async def cron_dispatch(workflow: str) -> dict[str, Any]:
    """Start a long GitHub job at the Vercel clock's time.

    Python-script ingests and BRAIN mining run for 30-150 minutes, longer than
    a function may live, so they stay GitHub jobs; only their trigger moves
    off GitHub's delayed `schedule:`. A dispatch event starts promptly. One
    dispatch per workflow per UTC day; a failed dispatch is recorded, not retried.
    """
    from alpha_agent.api.dependencies import get_db_pool
    from alpha_agent.scheduling.dispatch import dispatch_workflow

    return await dispatch_workflow(await get_db_pool(), workflow)


@router.get("/auth_check")
async def cron_auth_check() -> dict[str, bool]:
    """Cheap production smoke test for cron authentication; performs no I/O."""
    return {"ok": True}


@router.get("/event-shadow")
async def event_shadow_tick():
    """Research-only, always independent of the account runner and its BYOK budget."""
    from alpha_agent.api.dependencies import get_db_pool
    from alpha_agent.data.capacity import read_capacity
    from alpha_agent.paper.event_shadow import run_event_shadow_cycle
    if os.getenv("EVENT_SHADOW_ENABLED", "").lower() != "true":
        return {"status": "disabled"}
    pool = await get_db_pool()
    if not (await read_capacity(pool))["allow_writes"]:
        return {"status": "capacity_paused"}
    from alpha_agent.paper.event_shadow_review import record_session_sample
    from alpha_agent.paper.shadow_borrow_receipts import known_receipts
    result = await run_event_shadow_cycle(pool, borrow=await known_receipts(pool))
    await record_session_sample(pool)
    from alpha_agent.news.event_reaction import observe_event_reactions
    return {**result, "event_reactions": await observe_event_reactions(pool)}


@router.get("/premarket-review")
async def premarket_review_tick():
    from alpha_agent.api.dependencies import get_db_pool
    from alpha_agent.data.capacity import read_capacity
    from alpha_agent.paper.premarket_review import slot, tick

    if os.getenv("PREMARKET_REVIEW_ENABLED", "").lower() != "true":
        return {"status": "disabled"}
    if not slot(datetime.now(UTC)):
        return {"status": "outside_window"}
    owners = {s.strip() for s in os.getenv("ALPHACORE_ADMIN_USER_IDS", "").split(",") if s.strip()}
    if len(owners) != 1 or not next(iter(owners)).isdecimal():
        return {"status": "single_research_owner_required"}
    pool = await get_db_pool()
    if not (await read_capacity(pool))["allow_writes"]:
        return {"status": "capacity_paused"}
    return await tick(pool, int(next(iter(owners))))


@router.get("/option-observations")
async def private_option_tick():
    from alpha_agent.api.dependencies import get_db_pool
    from alpha_agent.data.option_observatory import enabled, sample_options
    if not enabled():
        return {"status": "disabled"}
    return await sample_options(await get_db_pool())


@router.get("/research_readiness")
async def cron_research_readiness() -> dict[str, Any]:
    """Read-only actual-date coverage; no provider requests or model calls."""
    from alpha_agent.api.dependencies import get_db_pool
    from alpha_agent.data.research_refresh import research_price_readiness

    return await research_price_readiness(await get_db_pool())


@router.get("/preflight")
async def cron_preflight() -> dict[str, Any]:
    """Authenticated read-only check. Does not ingest, prune, trade or call LLMs."""
    from alpha_agent.api.dependencies import get_db_pool
    from alpha_agent.data.capacity import read_capacity

    pool = await get_db_pool()
    capacity = await read_capacity(pool)
    return {"ok": True, **capacity}


@router.post("/slow_daily")
@router.get("/slow_daily")
async def slow_daily(
    limit: int | None = Query(None, ge=1, le=600),
    offset: int | None = Query(None, ge=0, le=600),
) -> dict[str, Any]:
    """Run slow_daily cron. `limit=N` caps universe (≤300s Hobby budget).
    `offset=M` starts at SP500_UNIVERSE[M]; combined with limit, enables
    GH-Actions multi-shot full SP500 coverage (e.g. 4 × {limit:140, offset:0/140/280/420}).
    """
    from api.cron.slow_daily import handler
    return await handler(limit=limit, offset=offset)


@router.post("/fast_intraday")
@router.get("/fast_intraday")
async def fast_intraday(
    limit: int | None = Query(None, ge=1, le=600),
    offset: int | None = Query(None, ge=0, le=600),
    tier: str = Query("full", pattern="^(full|tech|mid|slow)$"),
    run_key: str | None = Query(None, max_length=120),
) -> dict[str, Any]:
    """Run fast_intraday cron. `limit=N` caps watchlist (Hobby 300s budget).
    `offset=M` starts at SP500_UNIVERSE[M]; combined with limit, enables
    multi-shot coverage of the top tickers.

    `tier`: which signal subset to refresh this run. full = all 10 modules
    (legacy bootstrap); tech / mid / slow refresh only their named subset
    and round-trip the rest from the previous breakdown (see
    api/cron/fast_intraday.py docstring for the schedule design).
    """
    from api.cron.fast_intraday import handler
    return await handler(limit=limit, offset=offset, tier=tier, run_key=run_key)


@router.post("/publish_recommendation")
@router.get("/publish_recommendation")
async def publish_recommendation(
    request_id: str | None = Query(None, max_length=100),
) -> dict[str, Any]:
    """Publish one immutable recommendation only after every shard finished."""
    from alpha_agent.ledger import record_daily_close

    pool = await get_pool(os.environ["DATABASE_URL"])
    started_at = datetime.now(UTC)
    try:
        run_id = await record_daily_close(pool, started_at=started_at, require_full_universe=True)
    except Exception as exc:
        await pool.execute(
            """
            INSERT INTO cron_runs
                (cron_name, started_at, finished_at, ok, error_count, details)
            VALUES ('recommendation_publish', $1, now(), false, 1, $2::jsonb)
            """,
            started_at,
            json.dumps(
                {
                    "publish_status": "failed",
                    "reason": "publish_exception",
                    "error_type": type(exc).__name__,
                    "request_id": request_id,
                }
            ),
        )
        raise RuntimeError("recommendation snapshot publication failed") from exc

    if run_id is None:
        canonical = await pool.fetchrow(
            """
            SELECT id, scheduled_for_date
            FROM research_run
            WHERE run_type = 'daily_close' AND status = 'complete'
            ORDER BY scheduled_for_date DESC, id DESC
            LIMIT 1
            """
        )
        details = {
            "publish_status": "no_op_same_market_date",
            "run_id": int(canonical["id"]) if canonical else None,
            "market_date": (
                canonical["scheduled_for_date"].isoformat() if canonical else None
            ),
            "reason": "complete_run_already_exists",
            "request_id": request_id,
        }
        await pool.execute(
            """
            INSERT INTO cron_runs
                (cron_name, started_at, finished_at, ok, error_count, details)
            VALUES ('recommendation_publish', $1, now(), true, 0, $2::jsonb)
            """,
            started_at,
            json.dumps(details),
        )
        return {
            "ok": True,
            "run_id": details["run_id"],
            "market_date": details["market_date"],
            "publish_status": "no_op_same_market_date",
            "skipped": True,
            "reason": "no_op_same_market_date",
            "request_id": request_id,
        }
    run = await pool.fetchrow(
        "SELECT status, scheduled_for_date, health_json FROM research_run WHERE id=$1",
        run_id,
    )
    published = bool(run and run["status"] == "complete")
    publish_status = "published" if published else "health_gate_failed"
    details = {
        "publish_status": publish_status,
        "run_id": int(run_id),
        "market_date": run["scheduled_for_date"].isoformat() if run else None,
        "reason": None if published else "run_health_gate_failed",
        "request_id": request_id,
    }
    await pool.execute(
        """
        INSERT INTO cron_runs
            (cron_name, started_at, finished_at, ok, error_count, details)
        VALUES ('recommendation_publish', $1, now(), $2, $3, $4::jsonb)
        """,
        started_at,
        published,
        0 if published else 1,
        json.dumps(details),
    )
    return {
        "ok": published,
        "run_id": run_id,
        "publish_status": publish_status,
        "request_id": request_id,
        "status": run["status"] if run else "missing",
        "market_date": run["scheduled_for_date"].isoformat() if run else None,
        "health": (
            json.loads(run["health_json"])
            if run and isinstance(run["health_json"], str)
            else (run["health_json"] if run else {})
        ),
        "skipped": False,
        "reason": None if published else "run_health_gate_failed",
    }


@router.post("/alert_dispatcher")
@router.get("/alert_dispatcher")
async def alert_dispatcher() -> dict[str, Any]:
    from api.cron.alert_dispatcher import handler
    return await handler()


@router.post("/l2_cycle")
@router.get("/l2_cycle")
async def l2_cycle() -> dict[str, Any]:
    """Advance the L2 paper book one step over the product ledger (generate ->
    fill -> mark any due rebalance). Idempotent; schedule daily after the close
    so l2_equity_daily accumulates a forward curve."""
    from api.cron.l2_cycle import handler
    return await handler()


@router.post("/news_per_ticker")
@router.get("/news_per_ticker")
async def cron_news_per_ticker(
    limit: int | None = Query(None, ge=1, le=600),
    offset: int | None = Query(None, ge=0, le=600),
) -> dict[str, Any]:
    """Walk SP500 + watchlist, call PerTickerAggregator, upsert
    news_items. Limit + offset enable multi-shot sharding."""
    from api.cron.news_pipeline import per_ticker_handler
    return await per_ticker_handler(limit=limit, offset=offset)


@router.post("/news_macro")
@router.get("/news_macro")
async def cron_news_macro() -> dict[str, Any]:
    """Parallel-poll Truth/Fed/OFAC, upsert macro_events."""
    from api.cron.news_pipeline import macro_handler
    return await macro_handler()


@router.post("/minute_bars")
@router.get("/minute_bars")
async def cron_minute_bars(
    limit: int = 75,
    offset: int = 0,
) -> dict[str, Any]:
    """Pull 1-min bars for a slice of the SP500 universe and stamp cron_runs.

    Sharded via limit/offset so a single Hobby invocation stays under the
    300s budget. Universe is read from daily_signals_slow (~557 tickers)
    and ordered alphabetically for deterministic slicing across shards.
    """
    from alpha_agent.data.minute_price import (
        prune_minute_bars,
        pull_and_store_minute_bars,
    )
    from alpha_agent.data.retention import prune_daily_signals, prune_news_items

    started_at = datetime.now(UTC)
    pool = await get_pool(os.environ["DATABASE_URL"])

    # Retention prune (first shard only, once per cycle). The Neon free-tier
    # storage limit cannot hold a 7-day minute_bars window (~1.4M rows / ~324MB
    # crowded out every other table and produced DiskFullError on 2026-06-26),
    # so the window is now 1 day. A daily DELETE stabilizes each table at its
    # high-water mark: plain VACUUM does not shrink the file on Neon, but it
    # marks pages reusable so new inserts reuse them instead of extending it.
    #
    # daily_signals_fast and news_items had NO prune at all until 2026-07-26 —
    # they grew unbounded and were the tables sitting under the 460/500MB
    # storage reading when the 2026-07-25 quota outage hit. prune_daily_signals
    # refuses to outrun consistency_outcomes, so pruning cannot destroy the
    # picks-page consistency history.
    if offset == 0:
        prune_results = {
            "minute_bars": await prune_minute_bars(pool),
            "news_items": await prune_news_items(pool),
            "daily_signals_fast": await prune_daily_signals(pool),
        }
        print(f"[retention] {prune_results}", flush=True)

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT DISTINCT ticker FROM daily_signals_slow ORDER BY ticker LIMIT $1 OFFSET $2",
            limit,
            offset,
        )
    tickers = [r["ticker"] for r in rows]

    total_rows = 0
    tickers_pulled = 0
    error_count = 0
    failed: list[dict[str, str]] = []
    for ticker in tickers:
        try:
            written = await pull_and_store_minute_bars(pool, ticker)
            total_rows += int(written or 0)
            tickers_pulled += 1
        except Exception as exc:
            error_count += 1
            if len(failed) < 20:
                failed.append({"ticker": ticker, "error": f"{type(exc).__name__}: {exc}"})

    details = json.dumps(
        {
            "tickers_pulled": tickers_pulled,
            "rows_written": total_rows,
            "offset": offset,
            "limit": limit,
            "error_count": error_count,
            "failed_tickers": failed,
        }
    )
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details) "
            "VALUES ('minute_bars_pull', $1, now(), true, $2, $3::jsonb)",
            started_at,
            error_count,
            details,
        )

    return {
        "ok": True,
        "tickers_pulled": tickers_pulled,
        "rows_written": total_rows,
        "offset": offset,
        "limit": limit,
        "error_count": error_count,
    }


# ── Paper-trading daily fill ──────────────────────────────────────────────

def _insufficient_cash_fail_reason(cost: float, cash: float | None) -> str:
    cash_str = f"${cash:,.2f}" if cash is not None else "N/A"
    return (
        f"Insufficient cash at fill time: needed ${cost:,.2f}, account balance was {cash_str}"
        if os.environ.get("LOCALE", "zh") == "en"
        else f"成交时现金不足：需要 ${cost:,.2f}，账户余额为 {cash_str}"
    )


_PAPER_FILL_LOCK_NAME = "alpha_agent.paper_fill"
_PAPER_FILL_BATCH_SIZE = 200


async def _write_paper_equity_snapshots(conn: Any, today: date) -> None:
    """Publish one coherent daily read of human positions, orders and closes."""
    from alpha_agent.market_session import xnys_close
    from alpha_agent.paper.daily_valuation import read_daily_closes, summarize_daily_closes

    closing = xnys_close(today)
    async with conn.transaction(isolation="repeatable_read"):
        rows = await conn.fetch(
            """
            WITH eligible_accounts AS MATERIALIZED (
                SELECT sa.id,sa.reset_count,sa.cash,
                       EXISTS (
                           SELECT 1 FROM sim_order so
                           WHERE so.account_id=sa.id AND so.cohort_id=sa.reset_count
                             AND so.execution_model='daily_close_v1' AND so.status='pending'
                             AND so.signal_date<$1
                       ) AS settlement_pending
                FROM sim_account sa
                WHERE sa.kind='human' AND COALESCE(sa.reset_at,sa.created_at)<=$2
            )
            SELECT sa.*,sp.ticker,sp.qty,sp.avg_cost,sp.realized_pnl
            FROM eligible_accounts sa
            LEFT JOIN sim_position sp ON sp.account_id=sa.id AND sp.cohort_id=sa.reset_count
            """,
            today, closing,
        )
        if not rows:
            return
        books = {}
        tickers = {'SPY'}
        for row in rows:
            book = books.setdefault(row['id'], {
                'cohort': row['reset_count'], 'cash': row['cash'], 'realized': 0.0,
                'settlement_pending': row['settlement_pending'], 'positions': [],
            })
            book['realized'] += row['realized_pnl'] or 0.0
            if row['qty'] is not None and row['qty'] > 0:
                book['positions'].append(dict(row))
                tickers.add(row['ticker'])
        quotes = await read_daily_closes(conn, list(tickers), today)
        benchmark = quotes.get('SPY')
        snapshots = []
        for account_id, book in books.items():
            if book['settlement_pending']:
                nav, pnl, quality = None, None, 'orders_pending'
            else:
                valuation = summarize_daily_closes(book['positions'], quotes, book['cash'], today)
                nav = valuation['portfolio_value']
                pnl = valuation['unrealized_pnl']
                quality = valuation['valuation_quality']
            snapshots.append((
                account_id, book['cohort'], today, nav, book['cash'], pnl, book['realized'],
                benchmark['close'] if benchmark else None, quality, closing,
                closing if benchmark else None,
            ))
        await conn.executemany(
            """
            INSERT INTO sim_equity_daily
                (account_id,cohort_id,as_of_date,portfolio_value,cash,unrealized_pnl,
                 realized_pnl,benchmark_close,valuation_quality,valued_at,benchmark_close_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            ON CONFLICT (account_id,cohort_id,as_of_date) DO UPDATE SET
                portfolio_value=EXCLUDED.portfolio_value,cash=EXCLUDED.cash,
                unrealized_pnl=EXCLUDED.unrealized_pnl,realized_pnl=EXCLUDED.realized_pnl,
                benchmark_close=EXCLUDED.benchmark_close,valuation_quality=EXCLUDED.valuation_quality,
                valued_at=EXCLUDED.valued_at,benchmark_close_at=EXCLUDED.benchmark_close_at
            """,
            snapshots,
        )


async def _record_daily_order_outcome(
    conn: Any, order_id: int, status: str, reason: str | None,
    evidence: dict | None = None, review_deadline: datetime | None = None,
) -> None:
    await conn.execute(
        "UPDATE sim_order SET status=$1,fail_reason=$2,"
        "execution_evidence=CASE WHEN $3::jsonb IS NULL THEN execution_evidence "
        "ELSE COALESCE(execution_evidence,'{}'::jsonb) || $3::jsonb END,"
        "expires_at=COALESCE(expires_at,$4) WHERE id=$5",
        status, reason, json.dumps(evidence) if evidence is not None else None,
        review_deadline, order_id,
    )


async def _run_paper_fill_locked(pool: Any, today: date) -> dict[str, Any]:
    """Process one bounded fill batch while the job advisory lock is held."""
    from alpha_agent.market_session import xnys_close, xnys_sessions
    from alpha_agent.paper.fill_engine import (
        MARKET_AWAITING_QUOTE,
        MARKET_QUOTE_GRACE_SESSIONS,
        LimitExpiry,
        MarketReview,
        compute_limit_fill,
        has_sufficient_cash,
        market_order_window,
        new_avg_cost,
        realized_pnl_delta,
        review_market_fill,
    )
    from alpha_agent.paper.market_order_identity import market_identity_verified, read_market_instrument

    filled_count = 0
    expired_count = 0
    failed_count = 0
    skipped_locked = 0

    async with pool.acquire() as conn:
        pending_filter = (
            "so.status='pending' AND so.cohort_id=sa.reset_count "
            "AND sa.kind='human' AND so.execution_model='daily_close_v1'"
        )
        first_signal: date | None = await conn.fetchval(
            "SELECT min(so.signal_date) FROM sim_order so "
            f"JOIN sim_account sa ON sa.id=so.account_id WHERE {pending_filter} "
            "AND so.signal_date<$1", today,
        )
        completed = xnys_sessions(first_signal + timedelta(days=1), today) if first_signal else []
        pending_orders = []
        if completed:
            assert first_signal is not None
            # PostgreSQL's one-based array positions, indexed by signal
            # calendar day, avoid scanning the session list for every order.
            next_indices = [
                bisect_right(completed, first_signal + timedelta(days=offset)) + 1
                for offset in range((today - first_signal).days)
            ]
            # Prioritize verifiable fills and limits ahead of market quote
            # reviews. A pending notice is actionable only once per order.
            pending_orders = await conn.fetch(
                f"""
                WITH actionable AS (
                    SELECT so.*, quote.date AS quote_date, quote.close AS quote_close,
                        eligible.sessions AS quote_sessions,
                        CASE WHEN so.order_type='market' AND quote.date IS NOT NULL
                                  AND first.session_index + $5 >= cardinality($2::date[]) THEN 0
                             WHEN so.order_type='limit' THEN 1 ELSE 2 END AS priority
                    FROM sim_order so
                    JOIN sim_account sa ON sa.id=so.account_id
                    CROSS JOIN LATERAL (
                        SELECT ($3::int[])[so.signal_date-$4::date+1] AS session_index
                    ) first
                    CROSS JOIN LATERAL (
                        SELECT ($2::date[])[first.session_index:
                            (first.session_index + CASE WHEN so.order_type='market' THEN 0
                                ELSE GREATEST(so.expire_after_days,1)-1 END)] AS sessions
                    ) eligible
                    LEFT JOIN LATERAL (
                        SELECT dp.date, dp.close
                        FROM daily_prices dp
                        WHERE dp.ticker=so.ticker
                          AND dp.date=ANY(eligible.sessions)
                          AND dp.close>0 AND dp.close<'Infinity'::double precision
                          AND (so.order_type='market'
                              OR (so.side='buy' AND dp.close<so.limit_price)
                              OR (so.side='sell' AND dp.close>so.limit_price))
                        ORDER BY dp.date
                        LIMIT 1
                    ) quote ON TRUE
                    WHERE {pending_filter}
                      AND (quote.date IS NOT NULL OR (so.order_type='limit' AND
                          first.session_index + GREATEST(so.expire_after_days,1)-1 <= cardinality($2::date[]))
                          OR (so.order_type='market' AND first.session_index <= cardinality($2::date[])
                              AND (first.session_index + $5 <= cardinality($2::date[])
                                   OR so.fail_reason IS DISTINCT FROM $6)))
                    ORDER BY priority, so.created_at, so.id
                    LIMIT $1
                )
                SELECT a.*, CASE WHEN a.order_type='limit' AND a.quote_date IS NULL THEN (
                    SELECT jsonb_object_agg(to_char(dp.date, 'YYYY-MM-DD'), dp.close)
                    FROM daily_prices dp
                    WHERE dp.ticker=a.ticker AND dp.date=ANY(a.quote_sessions)
                      AND dp.close>0 AND dp.close<'Infinity'::double precision
                ) END AS window_quotes
                FROM actionable a
                ORDER BY a.priority, a.created_at, a.id
                """,
                _PAPER_FILL_BATCH_SIZE, completed, next_indices, first_signal,
                MARKET_QUOTE_GRACE_SESSIONS, MARKET_AWAITING_QUOTE,
            )

    if not pending_orders:
        async with pool.acquire() as conn:
            await _write_paper_equity_snapshots(conn, today)
            remaining_pending = await conn.fetchval(
                "SELECT COUNT(*) FROM sim_order so JOIN sim_account sa ON sa.id=so.account_id "
                f"WHERE {pending_filter}"
            )
        return {
            "ok": True,
            "filled": 0,
            "expired": 0,
            "failed": 0,
            "skipped_locked": 0,
            "remaining_pending": int(remaining_pending or 0),
            "market_pending_policy": "exact_t1_close_one_session_review",
            "batch_limit": _PAPER_FILL_BATCH_SIZE,
            "batch_full": False,
        }

    for order in pending_orders:
        ticker = order["ticker"]
        prices = {order["quote_date"]: order["quote_close"]} if order["quote_date"] else {}
        if order["window_quotes"]:
            prices = {date.fromisoformat(day): close
                      for day, close in json.loads(order["window_quotes"]).items()}
        signal_date = order["signal_date"]

        market_order = order["order_type"] == "market"
        result = None
        if not market_order:
            result = compute_limit_fill(
                order["side"],
                order["limit_price"],
                signal_date,
                prices,
                order["expire_after_days"],
                as_of=today,
            )

        if result is None and not market_order:
            continue

        async with pool.acquire() as conn:
            async with conn.transaction():
                locked_order = await conn.fetchrow(
                    "SELECT * FROM sim_order "
                    "WHERE id=$1 AND status='pending' AND execution_model='daily_close_v1' "
                    "AND EXISTS (SELECT 1 FROM sim_account sa WHERE sa.id=sim_order.account_id "
                    "AND sa.kind='human') FOR UPDATE SKIP LOCKED",
                    order["id"],
                )
                if locked_order is None:
                    skipped_locked += 1
                    continue

                account_id = locked_order["account_id"]
                account = await conn.fetchrow(
                    "SELECT cash, reset_count FROM sim_account WHERE id=$1 AND kind='human' FOR UPDATE",
                    account_id,
                )
                if account is None or int(account["reset_count"] or 0) != int(
                    locked_order["cohort_id"] or 0
                ):
                    await conn.execute(
                        "UPDATE sim_order SET status='cancelled' WHERE id=$1",
                        locked_order["id"],
                    )
                    continue

                market_evidence = None
                if market_order:
                    target, deadline = market_order_window(signal_date)
                    instrument = await read_market_instrument(conn, ticker)
                    result = review_market_fill(
                        signal_date, prices, as_of=today, identity_verified=market_identity_verified(
                            ticker, target, instrument, locked_order['instrument_id'],
                        ),
                    )
                    if result is None:
                        continue
                    market_evidence = {
                        'execution_model': 'daily_close_v1',
                        'target_session_date': target.isoformat(),
                        'quote_deadline_session_date': deadline.isoformat(),
                    }
                    if isinstance(result, MarketReview):
                        market_evidence.update(status=result.status, reason=result.reason)
                        await _record_daily_order_outcome(
                            conn, locked_order['id'], result.status, result.reason,
                            market_evidence, xnys_close(deadline),
                        )
                        expired_count += int(result.status == 'expired')
                        failed_count += int(result.status == 'failed')
                        continue

                if isinstance(result, LimitExpiry):
                    reason = ("limit_expired_missing_quotes" if result.missing_quote_dates
                              else "limit_expired_no_cross")
                    evidence = {
                        "execution_model": "daily_close_v1", "status": "expired", "reason": reason,
                        "missing_quote_dates": [day.isoformat() for day in result.missing_quote_dates],
                    }
                    await _record_daily_order_outcome(conn, locked_order['id'], 'expired', reason, evidence)
                    expired_count += 1
                    continue

                fill_date, fill_price = result
                qty = locked_order["qty"]
                current_cash = float(account["cash"])
                cohort_id = int(locked_order["cohort_id"] or 0)
                fee_bps = float(locked_order["fee_bps"] or 0.0)
                fee = float(fill_price) * int(qty) * fee_bps / 10000.0

                if locked_order["side"] == "buy":
                    # Fill-time re-check: order-time validation only estimated
                    # against cash at submission; an earlier fill in this same
                    # batch may have already spent it. The account row lock also
                    # serializes cash updates for buys and sells.
                    total_cost = float(fill_price) * int(qty) + fee
                    if not has_sufficient_cash(current_cash, total_cost, 1):
                        if market_evidence is not None:
                            market_evidence.update(status='failed', reason='insufficient_cash_at_fill')
                        await _record_daily_order_outcome(
                            conn, locked_order['id'], 'failed',
                            _insufficient_cash_fail_reason(total_cost, current_cash), market_evidence,
                        )
                        failed_count += 1
                        continue

                    # Upsert position with new avg_cost
                    existing = await conn.fetchrow(
                        "SELECT qty, avg_cost FROM sim_position "
                        "WHERE account_id=$1 AND cohort_id=$2 AND ticker=$3 FOR UPDATE",
                        account_id, cohort_id, ticker,
                    )
                    effective_unit_cost = float(fill_price) + fee / int(qty)
                    if existing and existing["qty"] > 0:
                        na = new_avg_cost(
                            existing["qty"], existing["avg_cost"], qty,
                            effective_unit_cost,
                        )
                        new_qty = existing["qty"] + qty
                        await conn.execute(
                            "UPDATE sim_position SET qty=$1, avg_cost=$2, updated_at=now() "
                            "WHERE account_id=$3 AND cohort_id=$4 AND ticker=$5",
                            new_qty, na, account_id, cohort_id, ticker,
                        )
                    else:
                        await conn.execute(
                            "INSERT INTO sim_position "
                            "(account_id, cohort_id, ticker, qty, avg_cost) "
                            "VALUES ($1, $2, $3, $4, $5) "
                            "ON CONFLICT (account_id, cohort_id, ticker) DO UPDATE "
                            "SET qty=$4, avg_cost=$5, updated_at=now()",
                            account_id, cohort_id, ticker, qty, effective_unit_cost,
                        )
                    # Deduct cash
                    await conn.execute(
                        "UPDATE sim_account SET cash = cash - $1 WHERE id = $2",
                        total_cost, account_id,
                    )
                else:  # sell
                    existing = await conn.fetchrow(
                        "SELECT qty, avg_cost, realized_pnl FROM sim_position "
                        "WHERE account_id=$1 AND cohort_id=$2 AND ticker=$3 FOR UPDATE",
                        account_id, cohort_id, ticker,
                    )
                    if existing is None or existing["qty"] < qty:
                        # Oversell guard: expire the order, do not process
                        failure = None
                        if market_evidence is not None:
                            failure = 'insufficient_position_at_fill'
                            market_evidence.update(status='expired', reason=failure)
                        await _record_daily_order_outcome(
                            conn, locked_order['id'], 'expired', failure, market_evidence,
                        )
                        expired_count += 1
                        continue

                    pnl_delta = (
                        realized_pnl_delta(existing["avg_cost"], fill_price, qty)
                        - fee
                    )
                    new_qty = existing["qty"] - qty
                    new_realized = (existing["realized_pnl"] or 0.0) + pnl_delta
                    await conn.execute(
                        "UPDATE sim_position SET qty=$1, realized_pnl=$2, updated_at=now() "
                        "WHERE account_id=$3 AND cohort_id=$4 AND ticker=$5",
                        new_qty, new_realized, account_id, cohort_id, ticker,
                    )
                    # Credit cash
                    await conn.execute(
                        "UPDATE sim_account SET cash = cash + $1 WHERE id = $2",
                        float(fill_price) * int(qty) - fee, account_id,
                    )

                if market_evidence is not None:
                    market_evidence.update(status='filled', reason='exact_t1_close')
                await conn.execute(
                    "UPDATE sim_order SET status='filled',fill_date=$1,fill_price=$2,transaction_cost=$3,"
                    "filled_at=now(),fail_reason=NULL,execution_evidence=CASE WHEN $5::jsonb IS NULL "
                    "THEN execution_evidence ELSE COALESCE(execution_evidence,'{}'::jsonb) || $5::jsonb END "
                    "WHERE id=$4",
                    fill_date, fill_price, fee, locked_order['id'],
                    json.dumps(market_evidence) if market_evidence is not None else None,
                )
                filled_count += 1

    async with pool.acquire() as conn:
        await _write_paper_equity_snapshots(conn, today)
        remaining_pending = await conn.fetchval(
            "SELECT COUNT(*) FROM sim_order so JOIN sim_account sa ON sa.id=so.account_id "
            f"WHERE {pending_filter}"
        )

    return {
        "ok": True,
        "filled": filled_count,
        "expired": expired_count,
        "failed": failed_count,
        "skipped_locked": skipped_locked,
        "remaining_pending": int(remaining_pending or 0),
        "market_pending_policy": "exact_t1_close_one_session_review",
        "batch_limit": _PAPER_FILL_BATCH_SIZE,
        "batch_full": len(pending_orders) == _PAPER_FILL_BATCH_SIZE,
    }


async def _run_paper_fill(dsn: str, *, today: date | None = None) -> dict[str, Any]:
    """Run one non-blocking, bounded fill batch with a database-owned lease."""
    pool = await get_pool(dsn)
    from alpha_agent.market_session import latest_completed_xnys_session

    today = today or latest_completed_xnys_session(datetime.now(UTC))
    async with pool.acquire() as lock_conn, lock_conn.transaction():
        acquired = await lock_conn.fetchval(
            "SELECT pg_try_advisory_xact_lock(hashtext($1))",
            _PAPER_FILL_LOCK_NAME,
        )
        if not acquired:
            return {
                "ok": True,
                "skipped": True,
                "reason": "already_running",
                "filled": 0,
                "expired": 0,
                "failed": 0,
            }
        result = await _run_paper_fill_locked(pool, today)
        for _ in range(2):
            if not result['batch_full'] or result['skipped_locked']:
                break
            next_batch = await _run_paper_fill_locked(pool, today)
            for key in ('filled', 'expired', 'failed', 'skipped_locked'):
                next_batch[key] += result[key]
            result = next_batch
        return result


@router.post("/paper_fill")
@router.get("/paper_fill")
async def cron_paper_fill() -> dict[str, Any]:
    """Daily post-close fill simulation for all pending sim_orders.

    Runs after daily_prices cron (at 01:00 UTC = ~21:00 ET).
    Idempotent: re-running on the same day is safe (ON CONFLICT DO UPDATE
    on sim_equity_daily; already-filled orders are skipped by status='pending' filter).
    """
    dsn = os.environ["DATABASE_URL"]
    started_at = datetime.now(UTC)
    try:
        result = await _run_paper_fill(dsn)
        # The legacy fill lease is released before any provider I/O. Bot
        # marks/snapshots run independently of whether human orders existed.
        from alpha_agent.paper.bot_valuation import refresh_daily_valuations

        result['bot_valuation'] = await refresh_daily_valuations(await get_pool(dsn))
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        pool = await get_pool(dsn)
        await pool.execute(
            "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details) "
            "VALUES ('paper_fill', $1, now(), false, 1, $2::jsonb)",
            started_at, json.dumps({"error": err}),
        )
        raise RuntimeError(f"paper_fill cron failed: {err}") from exc
    pool = await get_pool(dsn)
    await pool.execute(
        "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details) "
        "VALUES ('paper_fill', $1, now(), true, 0, $2::jsonb)",
        started_at, json.dumps(result),
    )
    return result


@router.post("/daily_prices")
@router.get("/daily_prices")
async def cron_daily_prices(
    limit: int | None = Query(None, ge=1, le=600),
    offset: int | None = Query(None, ge=0, le=600),
    period: str = Query("5d"),
) -> dict[str, Any]:
    """Append daily closes for the universe into daily_prices (the
    forward-return source for the walk-forward IC engine). `period` defaults
    to the daily "5d" append; pass a longer period (e.g. 3y) over offset
    slices to backfill history from the production backend."""
    from api.cron.daily_prices import handler
    return await handler(limit=limit, offset=offset, period=period)


@router.post("/methodology_proposer")
@router.get("/methodology_proposer")
async def cron_methodology_proposer() -> dict[str, Any]:
    """Phase 2a: daily statistics-driven methodology proposer. Enumerates
    single-knob config candidates, validates each on purged walk-forward OOS
    folds with trial-count deflation, and queues survivors as pending
    config_change_log rows for human approval (Phase 2b). Stays dormant
    (proposes nothing) until enough daily_prices history accrues to validate.
    Nothing auto-applies."""
    from alpha_agent.evolution.proposer import run_proposer

    pool = await get_pool(os.environ["DATABASE_URL"])
    started_at = datetime.now(UTC)
    try:
        result = await run_proposer(pool)
    except Exception as exc:  # noqa: BLE001
        # A proposer failure must leave an ok=false row so it stays visible in
        # cron_runs (a swallowed failure would silently never propose).
        err = f"{type(exc).__name__}: {exc}"
        await pool.execute(
            "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details) "
            "VALUES ($1, $2, now(), false, 1, $3::jsonb)",
            "methodology_proposer",
            started_at,
            json.dumps({"error": err}),
        )
        raise
    details = json.dumps(
        {
            "evaluated": result.get("evaluated", 0),
            "proposed": result.get("proposed", 0),
            "dormant": result.get("dormant", False),
        }
    )
    await pool.execute(
        "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details) "
        "VALUES ($1, $2, now(), true, 0, $3::jsonb)",
        "methodology_proposer",
        started_at,
        details,
    )
    return {"ok": True, **result}


# Wall-clock budget for one runner invocation. Kept under Vercel's function
# limit so we mark_failed cleanly (a diagnosable terminal state) rather than
# getting hard-killed mid-run and leaving a job stuck 'running'. Only checked
# BETWEEN jobs, so a single in-flight job still runs to its natural length;
# this just stops the runner from starting a fresh job too late.
_RUN_PROPOSE_BUDGET_S = 270.0


@router.post("/run_propose_jobs")
@router.get("/run_propose_jobs")
async def cron_run_propose_jobs() -> dict[str, Any]:
    """Reliable execution path for the LLM factor proposer (the /evolution
    'propose factors' button).

    POST /api/factor-lab/propose only ENQUEUES a job. The old design ran the
    work in a FastAPI BackgroundTask after the 202 response, but Vercel freezes
    the function once the response is sent, so that task never completed and the
    button silently produced nothing after the 2026-05-26 async refactor. A
    GitHub Actions runner (triggered instantly on enqueue via workflow_dispatch,
    plus a fallback schedule) calls this endpoint instead; here the work runs
    INSIDE the request (server-to-server, no browser long-hold, completes within
    the function budget) so it always finishes and writes a terminal job state
    the frontend poll can read.

    Drains queued jobs oldest-first until the queue empties or the budget is
    hit. Each job's failure is persisted onto its row, never swallowed."""
    from alpha_agent.api.routes.factor_lab import _run_propose_work
    from alpha_agent.config_store import refresh_config
    from alpha_agent.evolution.diagnostics import compute_diagnostic
    from alpha_agent.storage import propose_jobs

    pool = await get_pool(os.environ["DATABASE_URL"])
    deadline = time.monotonic() + _RUN_PROPOSE_BUDGET_S
    drained: list[dict[str, Any]] = []
    while time.monotonic() < deadline - 90:
        job = await propose_jobs.claim_oldest_queued(pool)
        if job is None:
            break
        job_id = job["id"]
        try:
            # Mirror post_propose's pre-work so the LLM sees the live baseline.
            await refresh_config(pool)
            diagnostic = await compute_diagnostic(pool)
            result = await _run_propose_work(
                pool, job["user_id"], job["n"], diagnostic, deadline=deadline,
            )
            if result.get("ok") is False:
                raise RuntimeError(f"invalid_evaluation: {result.get('_diag')}")
            await propose_jobs.mark_done(pool, job_id, result)
            drained.append(
                {
                    "job_id": job_id,
                    "status": "done",
                    "proposed": result.get("proposed", 0),
                    "evaluated": result.get("evaluated", 0),
                }
            )
        except Exception as exc:  # noqa: BLE001 — terminal failure must be observable
            err = f"{type(exc).__name__}: {exc}"
            await propose_jobs.mark_failed(pool, job_id, err)
            drained.append({"job_id": job_id, "status": "failed", "error": err})
    return {"ok": all(j["status"] == "done" for j in drained),
            "drained": len(drained), "jobs": drained}


# GA search wall-clock inside the daily loop, under the Vercel function budget.
_GA_BUDGET_S = 45.0


@router.post("/research_validation")
async def research_validation() -> dict[str, Any]:
    """Read-only real-kernel canary. No LLM spend, proposals or config mutation."""
    import asyncio
    from alpha_agent.config_store import refresh_config
    from alpha_agent.evolution.diagnostics import compute_diagnostic
    from alpha_agent.evolution.factor_validation import evaluate_factor_candidate
    from alpha_agent.evolution.llm_factor_proposer import RawProposal
    from alpha_agent.evolution.research_panel import load_research_context
    from alpha_agent.evolution.sandbox import SandboxRunner

    pool = await get_pool(os.environ["DATABASE_URL"])
    await refresh_config(pool)
    diagnostic = await compute_diagnostic(pool)
    context = await asyncio.to_thread(load_research_context)
    runner = SandboxRunner()
    rejects, results = [], []
    try:
        for expr in dict.fromkeys([diagnostic.current_expression, "rank(ts_mean(returns, 20))"]):
            result = await evaluate_factor_candidate(
                pool, runner, RawProposal(expression=expr), rejects, context=context)
            results.append({"expression": expr, "valid": result is not None,
                            "sharpes": result.sharpes if result else None,
                            "ic_oos": result.ic_oos if result else None})
    finally:
        runner.close()
    return {"ok": all(r["valid"] for r in results), "validation": context.evidence(),
            "results": results, "rejects": rejects, "writes": 0}


@router.post("/daily_factor_loop")
@router.get("/daily_factor_loop")
async def cron_daily_factor_loop() -> dict[str, Any]:
    """Phase D daily autonomous loop: read memory -> generate -> validate ->
    journal, all through the shared eval/gate/insert/journal core.

    The GA arm ALWAYS runs — it needs no LLM key, so the miner keeps improving
    unattended (the key advantage of the non-LLM generator). The LLM arm runs
    only when SYSTEM_USER_ID is configured, since an unattended cron has no
    per-user BYOK key (see feedback_byok_cron_architectural_tension). Records a
    cron_runs audit row so a silent failure stays visible."""
    from alpha_agent.api.routes.factor_lab import _run_ga_work, _run_propose_work
    from alpha_agent.config_store import refresh_config
    from alpha_agent.evolution.diagnostics import compute_diagnostic

    pool = await get_pool(os.environ["DATABASE_URL"])
    started_at = datetime.now(UTC)
    deadline = time.monotonic() + 270
    await refresh_config(pool)
    diagnostic = await compute_diagnostic(pool)
    out: dict[str, Any] = {"ok": True}

    # GA arm — the non-LLM generator; always runs.
    try:
        out["ga"] = await _run_ga_work(pool, diagnostic, budget_s=_GA_BUDGET_S)
    except Exception as exc:  # noqa: BLE001 — surface + still try the LLM arm
        out["ga"] = {"error": f"{type(exc).__name__}: {exc}"}

    # LLM arm — best-effort, only with a configured system key.
    system_uid = os.environ.get("SYSTEM_USER_ID")
    if system_uid:
        try:
            from alpha_agent.auth.dependencies import is_admin
            if not is_admin(int(system_uid)):
                raise ValueError("SYSTEM_USER_ID must identify an authorized administrator")
            out["llm"] = await _run_propose_work(pool, int(system_uid), 5, diagnostic, deadline=deadline)
        except Exception as exc:  # noqa: BLE001 — surface, don't crash the loop
            out["llm"] = {"error": f"{type(exc).__name__}: {exc}"}
    else:
        out["llm"] = {"ok": False, "error": "SYSTEM_USER_ID missing; LLM research did not run"}

    ga_prop = (out.get("ga") or {}).get("proposed", 0)
    llm_prop = (out.get("llm") or {}).get("proposed", 0)
    errors = [arm for arm in (out.get("ga", {}), out.get("llm", {}))
              if arm.get("error") or arm.get("ok") is False]
    out["ok"] = not errors
    await pool.execute(
        "INSERT INTO cron_runs "
        "(cron_name, started_at, finished_at, ok, error_count, details) "
        "VALUES ($1, $2, now(), $4, $5, $3::jsonb)",
        "daily_factor_loop",
        started_at,
        json.dumps({"ga_proposed": ga_prop, "llm_proposed": llm_prop,
                    "llm": (out.get("llm") or {}).get("llm"),
                    "errors": errors, "validation": (out.get("ga") or {}).get("validation")}),
        not errors, len(errors),
    )
    return out


@router.post("/compute_ic_annotations")
@router.get("/compute_ic_annotations")
async def cron_compute_ic_annotations(
    window_days: int = Query(30, ge=1, le=365),
) -> dict[str, Any]:
    """Traceability (principle 11): recompute IC change annotations after the
    daily IC refresh so the /evolution chart markers stay current without a
    manual trigger. Idempotent upsert; deterministic, no LLM."""
    from alpha_agent.evolution.metric_annotations import compute_ic_annotations

    pool = await get_pool(os.environ["DATABASE_URL"])
    started_at = datetime.now(UTC)
    try:
        written = await compute_ic_annotations(pool, window_days)
    except Exception as exc:  # noqa: BLE001 — surface in cron_runs, don't swallow
        err = f"{type(exc).__name__}: {exc}"
        await pool.execute(
            "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details) "
            "VALUES ($1, $2, now(), false, 1, $3::jsonb)",
            "compute_ic_annotations",
            started_at,
            json.dumps({"error": err}),
        )
        raise
    await pool.execute(
        "INSERT INTO cron_runs (cron_name, started_at, finished_at, ok, error_count, details) "
        "VALUES ($1, $2, now(), true, 0, $3::jsonb)",
        "compute_ic_annotations",
        started_at,
        json.dumps({"written": written, "window_days": window_days}),
    )
    return {"ok": True, "written": written, "window_days": window_days}


# news_llm_enrich cron route removed 2026-05-17.
# The previous cron-side handler called get_settings() -> create_llm_client()
# which requires a global LLM key in the server env. That violates BYOK
# (the platform deliberately does not hold a global key; each user supplies
# their own). Read-time replacement: POST /api/news/enrich/{ticker} with
# Depends(get_llm_client), which sources the caller's stored BYOK key.
