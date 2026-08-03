"""L2 driver: advance the paper book over the ledger (roadmap step 6 follow-on).

The L2 engine (backtest/l2.py) is stateless — it generates/fills/marks one batch
at a time. This driver is the scheduler that walks the COMPLETE gated ledger
runs in date order and builds a weekly-rebalanced book:

  - rebalance on a cadence (>= rebalance_days trading days since the last batch),
  - generate orders from that day's snapshot, fill at the next trusted close,
  - mark each completed holding period (a batch's exit = the NEXT batch's fill).

So l2_equity_daily accumulates one forward-return point per completed period.
Idempotent: re-running catches up + extends and never double-books (the engine's
generate/fill/mark are each idempotent). A daily cron calls run_driver().
"""
from __future__ import annotations

from datetime import date

from alpha_agent.backtest import l2
from alpha_agent.backtest import l2_continuous

CANONICAL_STRATEGY = "canonical_top50"
DEFAULT_REBALANCE_DAYS = 5


async def ensure_strategy(
    pool, *, rebalance_days: int = DEFAULT_REBALANCE_DAYS, top_n: int = 50
) -> int:
    """Register (idempotently) the one canonical user-facing book."""
    return await l2.register_strategy(
        pool,
        name=CANONICAL_STRATEGY,
        params={"top_n": top_n, "rebalance_days": rebalance_days},
    )


async def _complete_runs(pool) -> list[tuple[date, int]]:
    """(market date, run_id) for the canonical complete run of each date."""
    rows = await pool.fetch(
        """
        SELECT DISTINCT ON (scheduled_for_date) scheduled_for_date, id
        FROM research_run
        WHERE status = 'complete' AND run_type = 'daily_close'
        ORDER BY scheduled_for_date, finished_at DESC NULLS LAST, id DESC
        """
    )
    return [(r["scheduled_for_date"], r["id"]) for r in rows]


async def _trading_dates(pool) -> list[date]:
    rows = await pool.fetch("SELECT DISTINCT date FROM daily_prices ORDER BY date")
    return [r["date"] for r in rows]


def _next_price_date(trading: list[date], after: date) -> date | None:
    for d in trading:
        if d > after:
            return d
    return None


def _trading_days_between(trading: list[date], a: date, b: date) -> int:
    return sum(1 for d in trading if a < d <= b)


def _select_rebalance_dates(
    run_dates: list[date], trading: list[date], rebalance_days: int
) -> list[date]:
    """The first run, then every run >= rebalance_days trading days after the
    previous chosen rebalance."""
    chosen: list[date] = []
    for d in run_dates:
        if not chosen or _trading_days_between(trading, chosen[-1], d) >= rebalance_days:
            chosen.append(d)
    return chosen


async def run_driver(
    pool, *, strategy_id: int, rebalance_days: int = DEFAULT_REBALANCE_DAYS
) -> dict:
    """Advance the book: generate+fill every due rebalance batch, then mark each
    completed holding period. Idempotent. Returns a run summary."""
    runs = await _complete_runs(pool)
    run_by_date = {d: rid for d, rid in runs}
    run_dates = [d for d, _ in runs]
    trading = await _trading_dates(pool)

    rebal_dates = _select_rebalance_dates(run_dates, trading, rebalance_days)

    generated = filled = 0
    for d in rebal_dates:
        generated += await l2.generate_orders(
            pool, strategy_id=strategy_id, run_id=run_by_date[d]
        )
        fill_date = _next_price_date(trading, d)
        if fill_date is not None:
            res = await l2.fill_orders(
                pool, strategy_id=strategy_id, signal_date=d, fill_date=fill_date
            )
            filled += res["filled"]

    # Mark each completed period: batch P exits at the next batch N's fill date.
    equity_points = 0
    for prev, nxt in zip(rebal_dates, rebal_dates[1:]):
        nxt_fill = await pool.fetchval(
            "SELECT min(fill_date) FROM l2_order "
            "WHERE strategy_id=$1 AND signal_date=$2 AND fill_date IS NOT NULL",
            strategy_id, nxt,
        )
        if nxt_fill is None:
            continue
        await l2.mark_equity(
            pool, strategy_id=strategy_id, signal_date=prev, mark_date=nxt_fill
        )
        equity_points += 1

    return {
        "rebalances": len(rebal_dates),
        "generated": generated,
        "filled": filled,
        "equity_points": equity_points,
    }


async def run_continuous_driver(
    pool, *, strategy_id: int, rebalance_days: int = DEFAULT_REBALANCE_DAYS
) -> dict:
    """Advance the forward-only cash-and-shares book without legacy backfill."""
    trading = await _trading_dates(pool)
    account = await pool.fetchrow(
        "SELECT start_after_run_id FROM l2_account WHERE strategy_id=$1",
        strategy_id,
    )
    if account is None:
        return {"generated": 0, "filled": 0, "unfilled": 0, "pending": 0}

    # Fill only intents written by an earlier invocation.  The fill engine also
    # enforces fill_date > generated wall date as a second causal guard.
    pending_dates = await pool.fetch(
        "SELECT DISTINCT signal_date FROM l2_order "
        "WHERE strategy_id=$1 AND status='pending' ORDER BY signal_date",
        strategy_id,
    )
    filled = unfilled = 0
    for row in pending_dates:
        fill_date = _next_price_date(trading, row["signal_date"])
        if fill_date is None:
            continue
        # A rebalance mutates orders, positions, cash and the equity curve.  Keep
        # those writes atomic so a server interruption cannot leave a partial
        # portfolio transition behind.
        async with pool.acquire() as fill_conn, fill_conn.transaction():
            result = await l2_continuous.fill_target_intent(
                fill_conn,
                strategy_id=strategy_id,
                signal_date=row["signal_date"],
                fill_date=fill_date,
            )
        filled += int(result.get("filled", 0))
        unfilled += int(result.get("unfilled", 0))

    rows = await pool.fetch(
        """
        SELECT DISTINCT ON (scheduled_for_date) scheduled_for_date, id
        FROM research_run
        WHERE status='complete' AND run_type='daily_close' AND id>$1
        ORDER BY scheduled_for_date, finished_at DESC NULLS LAST, id DESC
        """,
        int(account["start_after_run_id"]),
    )
    last_signal = await pool.fetchval(
        "SELECT max(signal_date) FROM l2_order WHERE strategy_id=$1",
        strategy_id,
    )
    generated = 0
    for row in rows:
        signal_date = row["scheduled_for_date"]
        if last_signal is not None and _trading_days_between(
            trading, last_signal, signal_date
        ) < rebalance_days:
            continue
        created = await l2_continuous.generate_target_intent(
            pool, strategy_id=strategy_id, run_id=int(row["id"])
        )
        if created:
            generated += created
            last_signal = signal_date
    pending = int(await pool.fetchval(
        "SELECT count(*) FROM l2_order WHERE strategy_id=$1 AND status='pending'",
        strategy_id,
    ) or 0)
    return {
        "generated": generated,
        "filled": filled,
        "unfilled": unfilled,
        "pending": pending,
    }
