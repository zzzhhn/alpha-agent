"""Minimal causal L2 forward paper-trading (roadmap step 6).

Built ON TOP of the product ledger: orders are generated from a PRIOR immutable
rating_snapshot and persisted BEFORE any execution price is read, then filled at
the next trusted close, then marked against a benchmark. No real money, no
broker, free data. The value is an honest, look-ahead-free forward equity curve
(council: "make it boring").

Canonical book (params, overridable per strategy): top-N by rank with BUY/OW
preferred, equal weight, weekly rebalance, signal after close D filled at D+1
close, 10 bps/side, SPY benchmark, hold-cash for unfilled slots. A held position
whose feed dies produces an explicit exit event, never a silent disappearance.

Light module (no numpy): the arithmetic is plain weighted sums so the equity is
trivially reproducible from l2_order + daily_prices.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime

from alpha_agent.storage.product_ledger import get_run_snapshots

BENCHMARK = "SPY"

DEFAULT_PARAMS: dict = {
    "top_n": 50,
    "weighting": "equal",
    "max_position": 0.02,
    "rebalance": "weekly",
    "execution": "d1_close",
    "cost_bps": 10.0,
    "benchmark": BENCHMARK,
    "cash_policy": "hold_cash",
}

_PREFERRED_TIERS = frozenset({"BUY", "OW"})


def select_holdings(snapshots, *, top_n: int) -> list[dict]:
    """Pick the book from a run's snapshots: eligible names, BUY/OW preferred,
    then by rank; take top_n; equal-weight across the selected (cash fills any
    shortfall vs top_n, so a full top_n book is each name at 1/top_n)."""
    eligible = [s for s in snapshots if s["eligible"]]

    def _key(s):
        pref = 0 if (s["tier"] in _PREFERRED_TIERS) else 1
        rank = s["rank"] if s["rank"] is not None else 10**9
        return (pref, rank)

    chosen = sorted(eligible, key=_key)[:top_n]
    if not chosen:
        return []
    w = 1.0 / len(chosen)
    return [
        {"ticker": s["ticker"], "target_weight": w, "rank": s["rank"], "tier": s["tier"]}
        for s in chosen
    ]


async def register_strategy(
    pool, *, name: str, params: dict | None = None, version: int = 1
) -> int:
    """Persist (or fetch) the frozen, versioned ruleset. Returns its id."""
    merged = {**DEFAULT_PARAMS, **(params or {})}
    return await pool.fetchval(
        """
        INSERT INTO l2_strategy (name, version, params_json)
        VALUES ($1, $2, $3::jsonb)
        ON CONFLICT (name, version) DO UPDATE SET params_json = EXCLUDED.params_json
        RETURNING id
        """,
        name, version, json.dumps(merged),
    )


async def _params(pool, strategy_id: int) -> dict:
    row = await pool.fetchval("SELECT params_json FROM l2_strategy WHERE id=$1", strategy_id)
    return {**DEFAULT_PARAMS, **(json.loads(row) if row else {})}


async def generate_orders(pool, *, strategy_id: int, run_id: int) -> int:
    """Generate the target book from a COMPLETE (gated) ledger run and persist it
    as pending orders. CAUSAL: reads only the immutable snapshot, never a price;
    each order records source_run_id + generated_at. Idempotent per signal_date.
    Returns the number of orders created (0 if already generated)."""
    run = await pool.fetchrow(
        "SELECT scheduled_for_date, status FROM research_run WHERE id=$1", run_id
    )
    if run is None or run["status"] != "complete":
        # Only complete, gated runs are tradable (step 2 gate enforcement).
        return 0
    signal_date = run["scheduled_for_date"]

    existing = await pool.fetchval(
        "SELECT count(*) FROM l2_order WHERE strategy_id=$1 AND signal_date=$2",
        strategy_id, signal_date,
    )
    if existing:
        return 0

    params = await _params(pool, strategy_id)
    snaps = await get_run_snapshots(pool, run_id)
    holdings = select_holdings(snaps, top_n=int(params["top_n"]))
    if not holdings:
        return 0

    now = datetime.now(UTC)
    cost_bps = float(params["cost_bps"])
    await pool.executemany(
        """
        INSERT INTO l2_order
            (strategy_id, source_run_id, signal_date, ticker, target_weight,
             rank, tier, generated_at, cost_bps, status)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'pending')
        """,
        [
            (strategy_id, run_id, signal_date, h["ticker"], h["target_weight"],
             h["rank"], h["tier"], now, cost_bps)
            for h in holdings
        ],
    )
    return len(holdings)


async def _close(pool, ticker: str, d: date) -> float | None:
    return await pool.fetchval(
        "SELECT close FROM daily_prices WHERE ticker=$1 AND date=$2", ticker, d
    )


async def fill_orders(
    pool, *, strategy_id: int, signal_date: date, fill_date: date
) -> dict:
    """Fill pending orders at fill_date's close (D+1 by default). A name with no
    close on fill_date cannot be entered -> status='unfilled' with an explicit
    reason (never silently dropped). Returns {filled, unfilled}."""
    pending = await pool.fetch(
        "SELECT id, ticker FROM l2_order "
        "WHERE strategy_id=$1 AND signal_date=$2 AND status='pending'",
        strategy_id, signal_date,
    )
    filled = unfilled = 0
    for o in pending:
        px = await _close(pool, o["ticker"], fill_date)
        if px is None:
            await pool.execute(
                "UPDATE l2_order SET status='unfilled', exit_reason='dead_feed_at_fill' "
                "WHERE id=$1",
                o["id"],
            )
            unfilled += 1
        else:
            await pool.execute(
                "UPDATE l2_order SET status='filled', fill_date=$2, fill_price=$3 WHERE id=$1",
                o["id"], fill_date, float(px),
            )
            filled += 1
    return {"filled": filled, "unfilled": unfilled}


async def mark_equity(
    pool, *, strategy_id: int, signal_date: date, mark_date: date
) -> dict:
    """Mark the filled book at mark_date's close vs the benchmark, persist one
    l2_equity_daily row, and return it. Deterministic: gross/net reproduce from
    l2_order.fill_price + daily_prices. A filled name with no close at mark_date
    is exited (status='exited', reason) and counted as missing (conservative:
    contributes 0 return, not a fabricated gain)."""
    params = await _params(pool, strategy_id)
    cost_bps = float(params["cost_bps"])
    benchmark = params.get("benchmark", BENCHMARK)

    filled = await pool.fetch(
        "SELECT id, ticker, target_weight, fill_price FROM l2_order "
        "WHERE strategy_id=$1 AND signal_date=$2 AND status IN ('filled','exited')",
        strategy_id, signal_date,
    )
    gross = 0.0
    turnover = 0.0
    missing = 0
    n_positions = 0
    for o in filled:
        turnover += float(o["target_weight"])
        mp = await _close(pool, o["ticker"], mark_date)
        if mp is None or o["fill_price"] is None:
            # Feed died between fill and mark: explicit exit + conservative 0.
            await pool.execute(
                "UPDATE l2_order SET status='exited', exit_reason='dead_feed_at_mark' "
                "WHERE id=$1",
                o["id"],
            )
            missing += 1
            continue
        ret = float(mp) / float(o["fill_price"]) - 1.0
        gross += float(o["target_weight"]) * ret
        n_positions += 1

    # Round-trip cost: enter + exit, charged on the traded weight (turnover).
    net = gross - 2.0 * (cost_bps / 10000.0) * turnover

    # benchmark return measured over the same hold: fill_date close -> mark close.
    bench_ret = await _benchmark_return(pool, benchmark, strategy_id, signal_date, mark_date)

    row = await pool.fetchrow(
        """
        INSERT INTO l2_equity_daily
            (strategy_id, as_of_date, gross_return, net_return, benchmark_return,
             turnover, n_positions, stale_count, missing_count, cost_bps)
        VALUES ($1, $2, $3, $4, $5, $6, $7, 0, $8, $9)
        ON CONFLICT (strategy_id, as_of_date) DO UPDATE SET
            gross_return=EXCLUDED.gross_return, net_return=EXCLUDED.net_return,
            benchmark_return=EXCLUDED.benchmark_return, turnover=EXCLUDED.turnover,
            n_positions=EXCLUDED.n_positions, missing_count=EXCLUDED.missing_count,
            cost_bps=EXCLUDED.cost_bps, marked_at=now()
        RETURNING gross_return, net_return, benchmark_return, turnover,
                  n_positions, missing_count
        """,
        strategy_id, mark_date, gross, net, bench_ret, turnover,
        n_positions, missing, cost_bps,
    )
    return dict(row)


async def _benchmark_return(
    pool, benchmark: str, strategy_id: int, signal_date: date, mark_date: date
) -> float | None:
    """Benchmark return over the hold: benchmark close at the book's fill_date ->
    its close at mark_date. Uses the actual fill_date stored on the orders."""
    fill_date = await pool.fetchval(
        "SELECT min(fill_date) FROM l2_order "
        "WHERE strategy_id=$1 AND signal_date=$2 AND fill_date IS NOT NULL",
        strategy_id, signal_date,
    )
    if fill_date is None:
        return None
    bf = await _close(pool, benchmark, fill_date)
    bm = await _close(pool, benchmark, mark_date)
    if bf is None or bm is None or bf == 0:
        return None
    return float(bm) / float(bf) - 1.0
