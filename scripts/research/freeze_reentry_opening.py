"""Private pre-open checkpoint. Reads paper ledger and one SIP minute, never places orders."""

import argparse
import asyncio
from collections import defaultdict
from datetime import UTC, datetime, timedelta
import json
import os
from pathlib import Path

import asyncpg
import httpx
from dotenv import dotenv_values

from scripts.research.reentry_cash import D, FORWARD_START, FORWARD_END, forward_open
from scripts.research.paper_turnover_attribution import _dsn, _private_write, _session_bounds
from alpha_agent.paper.market_clock import NEW_YORK, as_utc


async def freeze(args):
    cutoff, _ = _session_bounds(FORWARD_START, FORWARD_END)
    if not cutoff <= datetime.now(UTC) < forward_open():
        raise ValueError("Only capture after the prior close and before the first open")
    db = await asyncpg.connect(_dsn(args.env_file), statement_cache_size=0, command_timeout=12)
    try:
        async with db.transaction(readonly=True, isolation="repeatable_read"):
            a = await db.fetchrow(
                "SELECT a.id,a.reset_count,a.initial_cash,coalesce(a.reset_at,a.created_at) AS born "
                "FROM sim_account a JOIN users u ON u.id=a.user_id WHERE lower(u.email)=lower($1) AND a.kind='bot'",
                os.environ["PAPER_ATTRIBUTION_OWNER_EMAIL"],
            )
            if not a or a["born"] > cutoff:
                raise ValueError("Missing opening cohort")
            rows = await db.fetch(
                "SELECT ticker,side,qty,fill_price,transaction_cost,filled_at,fill_date FROM sim_order "
                "WHERE account_id=$1 AND cohort_id=$2 AND status='filled' ORDER BY filled_at,id LIMIT 5001",
                a["id"],
                a["reset_count"],
            )
            if len(rows) > 5000:
                raise ValueError("Ledger exceeds bounded study")
            anchor = await db.fetchval(
                "SELECT cash FROM sim_equity_daily WHERE account_id=$1 AND cohort_id=$2 AND as_of_date=$3",
                a["id"],
                a["reset_count"],
                cutoff.astimezone(NEW_YORK).date(),
            )
    finally:
        await db.close()
    cash, positions = D(a["initial_cash"]), defaultdict(int)
    for row in rows:
        if (
            not row["filled_at"]
            or row["filled_at"] > cutoff
            or row["filled_at"].astimezone(NEW_YORK).date() != row["fill_date"]
            or row["side"] not in ("buy", "sell")
            or row["qty"] <= 0
        ):
            raise ValueError("Unreconciled or intervening fill")
        n = row["qty"] if row["side"] == "buy" else -row["qty"]
        cash -= n * D(row["fill_price"]) + D(row["transaction_cost"])
        positions[row["ticker"]] += n
    pos = {s: n for s, n in positions.items() if n}
    if any(n < 0 for n in pos.values()) or anchor is None or abs(cash - D(anchor)) > D(".01"):
        raise ValueError("Opening position or ledger cash mismatch")
    prices = {}
    start = cutoff - timedelta(minutes=1)
    if pos:
        keys = {**dotenv_values(".env"), **dotenv_values(".env.local"), **os.environ}
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(
                "https://data.alpaca.markets/v2/stocks/bars",
                headers={
                    "APCA-API-KEY-ID": keys["ALPACA_API_KEY"],
                    "APCA-API-SECRET-KEY": keys["ALPACA_API_SECRET"],
                },
                params={
                    "symbols": ",".join(sorted(pos)),
                    "feed": "sip",
                    "adjustment": "raw",
                    "timeframe": "1Min",
                    "start": start.isoformat(),
                    "end": (cutoff - timedelta(microseconds=1)).isoformat(),
                },
            )
            resp.raise_for_status()
            data = resp.json()
        if data.get("next_page_token") or set(data["bars"]) != set(pos):
            raise ValueError("Incomplete price coverage")
        for sym, bars in data["bars"].items():
            if (
                len(bars) != 1
                or as_utc(bars[0]["t"]) != start
                or not 0 < bars[0]["l"] <= bars[0]["c"] <= bars[0]["h"]
                or bars[0]["v"] <= 0
            ):
                raise ValueError("Invalid price minute")
            prices[sym] = str(bars[0]["c"])
    nav = cash + sum(n * D(prices[s]) for s, n in pos.items())
    stamp = datetime.now(UTC)
    if stamp >= forward_open():
        raise ValueError("Capture missed pre-open deadline")
    payload = dict(
        account=a["id"],
        cohort=a["reset_count"],
        cutoff=cutoff.isoformat(),
        captured_at=stamp.isoformat(),
        cash=str(cash),
        positions=pos,
        prices=prices,
        opening_nav=str(nav),
        price_basis="sip:1Min:raw",
        bar_start=start.isoformat(),
    )
    _private_write(args.out, json.dumps(payload, indent=2) + "\n")
    print("Frozen pre-open: %d symbols; reconciled cash %.2f; NAV %.2f." % (len(pos), cash, nav))


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env-file", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    asyncio.run(freeze(p.parse_args()))
