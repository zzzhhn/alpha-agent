"""Daily marks of already executed L2 shares. No retrospective target creation.

Catch up at most 65 sessions per call, carrying missing quotes visibly as stale.
Only changed sessions are written; two sleeves require about 504 rows/year.
"""
from __future__ import annotations

import math
from datetime import date

from alpha_agent.market_session import xnys_sessions


async def mark_daily(pool, *, strategy_id: int, through: date) -> dict:
    async with pool.acquire() as conn, conn.transaction():
        account = await conn.fetchrow("SELECT * FROM l2_account WHERE strategy_id=$1 FOR UPDATE", strategy_id)
        previous = await conn.fetchrow(
            "SELECT as_of_date,nav FROM l2_equity_daily WHERE strategy_id=$1 "
            "ORDER BY as_of_date DESC LIMIT 1", strategy_id)
        if not account or not account["last_fill_date"] or not previous:
            return {"marked": 0, "reason": "awaiting_first_execution"}
        start = previous["as_of_date"]
        if start >= through:
            return {"marked": 0, "as_of": start.isoformat()}
        if start < account["last_fill_date"]:
            raise ValueError("position_history_mismatch: cannot backfill across an unmarked trade")
        all_sessions = [d for d in xnys_sessions(start, through) if d > start]
        sessions = all_sessions[:65]
        if not sessions:
            return {"marked": 0, "as_of": start.isoformat()}
        positions = await conn.fetch(
            "SELECT ticker,qty,last_price,last_price_date FROM l2_position "
            "WHERE strategy_id=$1 AND qty>0", strategy_id)
        tickers = sorted({p["ticker"] for p in positions} | {"SPY", "RSP"})
        rows = await conn.fetch(
            "SELECT ticker,date,close FROM daily_prices "
            "WHERE ticker=ANY($1::text[]) AND date BETWEEN $2 AND $3",
            tickers, start, sessions[-1])
        prices = {(r["date"], r["ticker"]): float(r["close"]) for r in rows
                  if r["close"] is not None and math.isfinite(r["close"]) and r["close"] > 0}
        last = {p["ticker"]: float(p["last_price"]) for p in positions
                if p["last_price"] is not None and p["last_price"] > 0}
        cash, nav = float(account["cash"]), float(previous["nav"])
        records = []
        for day in sessions:
            stale = 0
            for p in positions:
                ticker = p["ticker"]
                value = prices.get((day, ticker))
                if value is not None:
                    last[ticker] = value
                else:
                    stale += 1
                if ticker not in last:
                    raise ValueError(f"unvalued_position: {ticker}")
            market_value = sum(int(p["qty"]) * last[p["ticker"]] for p in positions)
            next_nav = cash + market_value
            ret = next_nav / nav - 1
            benchmarks = []
            for ticker in ("SPY", "RSP"):
                a, b = prices.get((start, ticker)), prices.get((day, ticker))
                benchmarks.append(b / a - 1 if a and b else None)
            records.append((strategy_id, day, ret, benchmarks[0], benchmarks[1],
                            len(positions), stale, next_nav, cash, market_value,
                            next_nav / float(account["initial_cash"]) - 1))
            start, nav = day, next_nav
        await conn.executemany(
            "INSERT INTO l2_equity_daily "
            "(strategy_id,as_of_date,gross_return,net_return,benchmark_return,rsp_return,"
            "turnover,n_positions,stale_count,missing_count,cost_bps,nav,cash,market_value,cumulative_return) "
            "VALUES ($1,$2,$3,$3,$4,$5,0,$6,$7,0,0,$8,$9,$10,$11) "
            "ON CONFLICT (strategy_id,as_of_date) DO NOTHING", records)
        await conn.execute("UPDATE l2_account SET nav=$2,updated_at=now() WHERE strategy_id=$1",
                           strategy_id, nav)
        # Preserve last_fill_date: a valuation is not a trade.
        await conn.executemany(
            "UPDATE l2_position SET last_price=$3,last_price_date=$4,updated_at=now() "
            "WHERE strategy_id=$1 AND ticker=$2",
            [(strategy_id, p["ticker"], last[p["ticker"]],
              max((d for d in sessions if (d, p["ticker"]) in prices), default=p["last_price_date"]))
             for p in positions])
        return {"marked": len(records), "as_of": start.isoformat(),
                "stale_marks": sum(r[6] for r in records), "nav": nav,
                "caught_up": start == all_sessions[-1]}
