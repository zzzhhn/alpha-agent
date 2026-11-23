"""Store only the derived summary of an owner-scoped, fully priced paper replay."""

import argparse
import asyncio
from datetime import date
import json
import os
from pathlib import Path

import asyncpg

from alpha_agent.paper.turnover_attribution import load_turnover_attribution
from paper_turnover_attribution import _archival_quotes, _dsn


async def store(args):
    quotes = _archival_quotes(args.quote_receipt, args.start, args.end)
    conn = await asyncpg.connect(_dsn(args.env_file), timeout=8, command_timeout=15,
                                 statement_cache_size=0)
    try:
        async with conn.transaction(isolation="repeatable_read"):
            owner = os.environ["PAPER_ATTRIBUTION_OWNER_EMAIL"]
            a = await conn.fetchrow(
                "SELECT a.id,a.user_id,a.reset_count FROM sim_account a JOIN users u ON u.id=a.user_id "
                "WHERE lower(u.email)=lower($1) AND a.kind='bot' FOR SHARE OF a", owner)
            if not a:
                raise ValueError("No bot account for specified owner")
            r = await load_turnover_attribution(conn, a["user_id"], a["id"], args.start, args.end,
                                                archival_quotes=quotes)
            c, t, b = r["coverage"], r["totals"], r["scenarios"]
            if not (r["window"]["status"] == "complete" and c["ledger_complete"]
                    and c["filled"] == c["trade_attribution"] and c["terminal_marks"] == c["terminal_marks_required"]):
                raise ValueError("Refusing an incomplete replay")
            metrics = {"filled": c["filled"], "fees": t["fees"], "slippage": t["slippage_usd"],
                       **{k + "_nav": b[k]["nav"] for k in ("actual", "hold", "reduce_only")},
                       "actual_vs_hold": t["net_vs_hold_usd"],
                       "including_dividends_vs_hold": r["cash_dividend_sensitivity"]["net_vs_hold_usd"]["actual"]}
            key = (a["id"], a["reset_count"], args.start, args.end)
            await conn.execute(
                "INSERT INTO paper_turnover_receipt(account_id,cohort_id,start_date,end_date,metrics,provenance) "
                "VALUES($1,$2,$3,$4,$5,'post-hoc SIP raw last regular-session minute; excludes cash dividends') "
                "ON CONFLICT DO NOTHING", *key, json.dumps(metrics, allow_nan=False))
            actual = await conn.fetchval("SELECT metrics FROM paper_turnover_receipt WHERE "
                                         "(account_id,cohort_id,start_date,end_date)=($1,$2,$3,$4)", *key)
            if json.loads(actual) != metrics:
                raise ValueError("Existing immutable replay differs; no overwrite")
            print("Verified owner-scoped summary; fills:", c["filled"])
    finally:
        await conn.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--quote-receipt", type=Path, required=True)
    p.add_argument("--env-file", type=Path)
    p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--end", type=date.fromisoformat, required=True)
    asyncio.run(store(p.parse_args()))
