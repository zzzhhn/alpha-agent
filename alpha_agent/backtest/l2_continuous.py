"""Continuous, causal L2 paper account with share-level delta rebalancing.

Target weights are persisted before any execution price is read.  On D+1 the
book converts those targets to integer shares against the then-current NAV,
sells first, buys only with available cash, charges explicit costs, and carries
cash and positions forward.  It intentionally starts after the run that exists
when the account is created, so deployment can never manufacture a historical
"forward" curve from prices already known to the code.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, date, datetime

from alpha_agent.backtest.l2 import DEFAULT_PARAMS, select_holdings
from alpha_agent.fusion.policy import get_policy
from alpha_agent.storage.product_ledger import get_run_snapshots

STRATEGY_VERSION = 2
INITIAL_CASH = 1_000_000.0


async def ensure_book(
    pool,
    *,
    sleeve: str = "tactical",
    initial_cash: float = INITIAL_CASH,
    start_after_run_id: int | None = None,
) -> int:
    """Register the continuous strategy and initialize its forward-only book."""
    policy = get_policy(sleeve)
    strategy_name = (
        "canonical_top50_continuous"
        if sleeve == "tactical"
        else f"canonical_top50_continuous_{sleeve}"
    )
    params = {
        **DEFAULT_PARAMS,
        "accounting": "continuous_share_delta",
        "sleeve": sleeve,
        "policy_id": policy.policy_id,
        "initial_cash": initial_cash,
    }
    strategy_id = await pool.fetchval(
        """
        INSERT INTO l2_strategy (name, version, params_json)
        VALUES ($1, $2, $3::jsonb)
        ON CONFLICT (name, version) DO UPDATE SET params_json=EXCLUDED.params_json
        RETURNING id
        """,
        strategy_name,
        STRATEGY_VERSION,
        json.dumps(params),
    )
    boundary = start_after_run_id
    if boundary is None:
        boundary = int(await pool.fetchval(
            "SELECT COALESCE(max(id), 0) FROM research_run WHERE status='complete'"
        ) or 0)
    await pool.execute(
        """
        INSERT INTO l2_account
            (strategy_id, initial_cash, cash, nav, start_after_run_id)
        VALUES ($1, $2, $2, $2, $3)
        ON CONFLICT (strategy_id) DO NOTHING
        """,
        strategy_id,
        float(initial_cash),
        boundary,
    )
    return int(strategy_id)


async def generate_target_intent(pool, *, strategy_id: int, run_id: int) -> int:
    """Persist a full target, including explicit zero targets for removals."""
    run = await pool.fetchrow(
        "SELECT scheduled_for_date, status, weight_policy_id FROM research_run WHERE id=$1",
        run_id,
    )
    account = await pool.fetchrow(
        "SELECT start_after_run_id FROM l2_account WHERE strategy_id=$1",
        strategy_id,
    )
    if (
        run is None
        or account is None
        or run["status"] != "complete"
        or run_id <= int(account["start_after_run_id"])
    ):
        return 0
    signal_date = run["scheduled_for_date"]
    if await pool.fetchval(
        "SELECT 1 FROM l2_order WHERE strategy_id=$1 AND signal_date=$2 LIMIT 1",
        strategy_id,
        signal_date,
    ):
        return 0

    params_raw = await pool.fetchval(
        "SELECT params_json FROM l2_strategy WHERE id=$1", strategy_id
    )
    params = {**DEFAULT_PARAMS, **(json.loads(params_raw) if params_raw else {})}
    snapshots = await get_run_snapshots(pool, run_id)
    sleeve = str(params.get("sleeve") or "tactical")
    if sleeve == "strategic":
        strategic_policy_id = str(params.get("policy_id") or "")
        projected = []
        for snapshot in snapshots:
            raw_payload = snapshot["user_visible_payload_json"]
            payload = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
            long_payload = ((payload or {}).get("_mode_payloads") or {}).get("long") or {}
            if long_payload.get("policy_id") != strategic_policy_id:
                continue
            projected.append({
                "ticker": snapshot["ticker"],
                "eligible": bool(snapshot["eligible"]),
                "rank": long_payload.get("policy_rank"),
                "tier": long_payload.get("rating"),
            })
        snapshots = projected
    holdings = select_holdings(
        snapshots,
        top_n=int(params["top_n"]),
        max_position=float(params["max_position"]),
    )
    targets = {h["ticker"]: h for h in holdings}
    positions = await pool.fetch(
        "SELECT ticker, qty FROM l2_position WHERE strategy_id=$1 AND qty>0",
        strategy_id,
    )
    for position in positions:
        targets.setdefault(
            position["ticker"],
            {"ticker": position["ticker"], "target_weight": 0.0, "rank": None, "tier": None},
        )
    if not targets:
        return 0

    now = datetime.now(UTC)
    policy_id = params.get("policy_id") or run["weight_policy_id"]
    await pool.executemany(
        """
        INSERT INTO l2_order
            (strategy_id, source_run_id, signal_date, ticker, target_weight,
             rank, tier, generated_at, cost_bps, status, pre_qty,
             source_policy_id, source_sleeve)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'pending',$10,$11,$12)
        """,
        [
            (
                strategy_id,
                run_id,
                signal_date,
                item["ticker"],
                float(item["target_weight"]),
                item["rank"],
                item["tier"],
                now,
                float(params["cost_bps"]),
                next((int(p["qty"]) for p in positions if p["ticker"] == item["ticker"]), 0),
                policy_id,
                sleeve,
            )
            for item in targets.values()
        ],
    )
    return len(targets)


async def fill_target_intent(
    pool, *, strategy_id: int, signal_date: date, fill_date: date
) -> dict:
    """Convert one persisted target to share deltas and update the account."""
    pending = await pool.fetch(
        "SELECT * FROM l2_order WHERE strategy_id=$1 AND signal_date=$2 "
        "AND status='pending' ORDER BY ticker",
        strategy_id,
        signal_date,
    )
    if not pending:
        return {"filled": 0, "unfilled": 0, "turnover": 0.0}
    # Never consume a price that was already historical when the target intent
    # was written.  Wall-date comparison is conservative and observable.
    if any(fill_date <= order["generated_at"].date() for order in pending):
        return {"filled": 0, "unfilled": 0, "turnover": 0.0, "deferred": True}

    account = await pool.fetchrow(
        "SELECT * FROM l2_account WHERE strategy_id=$1", strategy_id
    )
    positions_rows = await pool.fetch(
        "SELECT * FROM l2_position WHERE strategy_id=$1", strategy_id
    )
    positions = {row["ticker"]: dict(row) for row in positions_rows}
    tickers = sorted(set(positions) | {row["ticker"] for row in pending})
    price_rows = await pool.fetch(
        "SELECT ticker, close FROM daily_prices WHERE date=$1 AND ticker=ANY($2::text[])",
        fill_date,
        tickers,
    )
    prices = {row["ticker"]: float(row["close"]) for row in price_rows}
    cash = float(account["cash"])
    previous_nav = float(account["nav"])
    nav_before = cash + sum(
        int(pos["qty"]) * float(prices.get(ticker) or pos.get("last_price") or 0.0)
        for ticker, pos in positions.items()
    )
    if nav_before <= 0:
        nav_before = previous_nav

    plans: list[dict] = []
    unfilled = 0
    for order in pending:
        ticker = order["ticker"]
        current = int(positions.get(ticker, {}).get("qty", 0))
        price = prices.get(ticker)
        if price is None or price <= 0:
            await pool.execute(
                "UPDATE l2_order SET status='unfilled', exit_reason='dead_feed_at_fill' WHERE id=$1",
                order["id"],
            )
            unfilled += 1
            continue
        target_qty = max(0, math.floor(nav_before * float(order["target_weight"]) / price))
        plans.append({"order": order, "ticker": ticker, "price": price, "current": current, "target": target_qty, "delta": target_qty - current})

    # Sell first so rebalance proceeds without leverage or hidden cash credit.
    plans.sort(key=lambda plan: (plan["delta"] >= 0, plan["ticker"]))
    gross_traded = fees = 0.0
    filled = 0
    for plan in plans:
        order = plan["order"]
        ticker = plan["ticker"]
        price = float(plan["price"])
        current = int(plan["current"])
        delta = int(plan["delta"])
        fee_rate = float(order["cost_bps"] or 0.0) / 10000.0
        if delta > 0:
            affordable = max(0, math.floor(cash / (price * (1.0 + fee_rate))))
            delta = min(delta, affordable)
        side = "buy" if delta > 0 else "sell" if delta < 0 else "hold"
        notional = abs(delta) * price
        fee = notional * fee_rate
        pos = positions.setdefault(ticker, {"qty": 0, "avg_cost": 0.0, "realized_pnl": 0.0, "last_price": None})
        old_qty = int(pos.get("qty", 0))
        avg_cost = float(pos.get("avg_cost", 0.0))
        realized = float(pos.get("realized_pnl", 0.0))
        if delta < 0:
            sold = min(-delta, old_qty)
            delta = -sold
            notional = sold * price
            fee = notional * fee_rate
            cash += notional - fee
            realized += sold * (price - avg_cost) - fee
        elif delta > 0:
            cash -= notional + fee
            avg_cost = ((old_qty * avg_cost) + notional + fee) / (old_qty + delta)
        new_qty = old_qty + delta
        if new_qty == 0:
            avg_cost = 0.0
        pos.update(qty=new_qty, avg_cost=avg_cost, realized_pnl=realized, last_price=price)
        gross_traded += notional
        fees += fee
        await pool.execute(
            """
            INSERT INTO l2_position
                (strategy_id,ticker,qty,avg_cost,realized_pnl,last_price,last_price_date,updated_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7,now())
            ON CONFLICT (strategy_id,ticker) DO UPDATE SET
                qty=EXCLUDED.qty, avg_cost=EXCLUDED.avg_cost,
                realized_pnl=EXCLUDED.realized_pnl, last_price=EXCLUDED.last_price,
                last_price_date=EXCLUDED.last_price_date, updated_at=now()
            """,
            strategy_id, ticker, new_qty, avg_cost, realized, price, fill_date,
        )
        await pool.execute(
            """
            UPDATE l2_order SET status='filled', fill_date=$2, fill_price=$3,
                pre_qty=$4, target_qty=$5, delta_qty=$6, side=$7,
                gross_notional=$8, transaction_cost=$9
            WHERE id=$1
            """,
            order["id"], fill_date, price, current, new_qty, delta, side, notional, fee,
        )
        filled += 1

    market_value = sum(int(pos["qty"]) * float(pos.get("last_price") or 0.0) for pos in positions.values())
    nav = cash + market_value
    period_return = nav / previous_nav - 1.0 if previous_nav else 0.0
    turnover = gross_traded / previous_nav if previous_nav else 0.0
    benchmark_return = await _benchmark_period(pool, "SPY", account["last_fill_date"], fill_date)
    rsp_return = await _benchmark_period(pool, "RSP", account["last_fill_date"], fill_date)
    await pool.execute(
        "UPDATE l2_account SET cash=$2, nav=$3, last_fill_date=$4, updated_at=now() WHERE strategy_id=$1",
        strategy_id, cash, nav, fill_date,
    )
    await pool.execute(
        """
        INSERT INTO l2_equity_daily
            (strategy_id,as_of_date,gross_return,net_return,benchmark_return,rsp_return,
             turnover,n_positions,stale_count,missing_count,cost_bps,nav,cash,
             market_value,cumulative_return)
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,0,$9,$10,$11,$12,$13,$14)
        ON CONFLICT (strategy_id,as_of_date) DO UPDATE SET
             gross_return=EXCLUDED.gross_return, net_return=EXCLUDED.net_return,
             benchmark_return=EXCLUDED.benchmark_return, rsp_return=EXCLUDED.rsp_return,
             turnover=EXCLUDED.turnover, n_positions=EXCLUDED.n_positions,
             missing_count=EXCLUDED.missing_count, nav=EXCLUDED.nav,
             cash=EXCLUDED.cash, market_value=EXCLUDED.market_value,
             cumulative_return=EXCLUDED.cumulative_return, marked_at=now()
        """,
        strategy_id, fill_date, period_return + fees / previous_nav if previous_nav else period_return,
        period_return, benchmark_return, rsp_return, turnover,
        sum(1 for pos in positions.values() if int(pos["qty"]) > 0), unfilled,
        float(pending[0]["cost_bps"] or 0.0), nav, cash, market_value,
        nav / float(account["initial_cash"]) - 1.0,
    )
    return {"filled": filled, "unfilled": unfilled, "turnover": turnover, "nav": nav, "fees": fees}


async def _benchmark_period(pool, ticker: str, previous: date | None, current: date) -> float | None:
    if previous is None:
        return None
    rows = await pool.fetch(
        "SELECT date, close FROM daily_prices WHERE ticker=$1 AND date=ANY($2::date[])",
        ticker,
        [previous, current],
    )
    prices = {row["date"]: float(row["close"]) for row in rows}
    if previous not in prices or current not in prices or prices[previous] == 0:
        return None
    return prices[current] / prices[previous] - 1.0
