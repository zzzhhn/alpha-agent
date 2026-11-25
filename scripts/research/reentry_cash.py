"""Owner-only paired replay. No provider call, model call, trading or database write."""

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import date, datetime, time
from decimal import Decimal
import json
import os
from pathlib import Path

import asyncpg

from alpha_agent.paper.market_clock import as_utc, market_session, NEW_YORK
from scripts.research.paper_turnover_attribution import _archival_quotes, _dsn
from alpha_agent.paper.turnover_attribution import _session_bounds


def D(value):
    return Decimal(str(value))


FORWARD_START = date(2026, 11, 25)
FORWARD_END = date(2026, 12, 23)
TIERS = ("SELL", "UW", "HOLD", "OW", "BUY")
POLICIES = ("actual", "skip_rank_rise", "skip_unchanged", "upgrades_only", "cash_after_sales")


def forward_open():
    midday = datetime.combine(FORWARD_START, time(12), NEW_YORK)
    return as_utc(market_session(midday)["open_at"])


def category(row):
    """Only facts in the order's frozen, preceding model packet; not prose inference."""
    ctx, result = row["context"], row["result"]
    if (
        not ctx.get("created_at")
        or not row["accepted_at"]
        or as_utc(ctx["created_at"]) > row["accepted_at"]
    ):
        return "unknown"
    actions = [
        a
        for a in (result.get("decision") or {}).get("actions", [])
        if a.get("action_id") == row["action_id"]
        and a.get("type") == "set_target_weight"
        and str(a.get("instrument_id")) == str(row["instrument_id"])
    ]
    r = next((i for i in ctx.get("recommendations", []) if i["ticker"] == row["ticker"]), {})
    if (
        len(actions) != 1
        or not r.get("evidence_id")
        or r.get("evidence_id") not in actions[0].get("evidence_ids", [])
    ):
        return "unknown"
    if set(actions[0]["evidence_ids"]) != {r["evidence_id"]}:
        return "other_evidence"
    old, new = r.get("previous_tier"), r.get("tier")
    if old not in TIERS or new not in TIERS:
        return "unknown"
    if old != new:
        return "upgrade" if TIERS.index(new) > TIERS.index(old) else "downgrade"
    if (
        r.get("previous_rank") is not None
        and r.get("rank") is not None
        and r["rank"] < r["previous_rank"]
    ):
        return "unchanged_rank_rise"
    return "unchanged_other"


def replay(policy, cash, holdings, fills, marks, dividends):
    pos = defaultdict(int, holdings)
    fees = divs = D(0)
    buys = clipped = 0
    events = iter(sorted(dividends, key=lambda d: d["date"]))
    nxt = next(events, None)

    def accrue(day):
        nonlocal nxt, divs
        while nxt and nxt["date"] <= day:
            divs += D(nxt["rate"]) * pos[nxt["ticker"]]
            nxt = next(events, None)

    for row in fills:
        accrue(row["fill_date"])
        t, qty, px, fee = (
            row["ticker"],
            row["qty"],
            D(row["fill_price"]),
            D(row["transaction_cost"]),
        )
        if qty <= 0 or px <= 0 or fee < 0 or row["side"] not in {"buy", "sell"}:
            raise ValueError("Invalid execution evidence")
        buy = row["side"] == "buy"
        if buy:
            tag = category(row)
            if (
                policy == "cash_after_sales"
                or policy == "upgrades_only"
                and tag != "upgrade"
                or policy == "skip_rank_rise"
                and tag == "unchanged_rank_rise"
                or policy == "skip_unchanged"
                and tag.startswith("unchanged_")
            ):
                continue
        n = min(qty, int(cash / (px + fee / qty))) if buy else min(qty, pos[t])
        if n != qty:
            if policy == "actual":
                raise ValueError("Recorded account did not reconcile")
            clipped += 1
            if n and (
                row["fee_bps"] is None
                or abs(px * qty * D(row["fee_bps"]) / 10000 - fee) > D("0.00001")
            ):
                raise ValueError("Partial order fee is not proportional")
        cost = fee * n / qty
        pos[t] += n if buy else -n
        cash += (-n if buy else n) * px - cost
        fees += cost
        buys += int(buy and n > 0)
    accrue(date.max)
    nav = cash + sum(n * D(marks[t]["price"]) for t, n in pos.items() if n)
    return {
        "nav": float(nav),
        "fees": float(fees),
        "buys": buys,
        "size_limited": clipped,
        "dividend_sensitivity": float(divs),
    }


async def run(args):
    quotes = _archival_quotes(args.receipt, args.start, args.end)
    begin, end = _session_bounds(args.start, args.end)
    db = await asyncpg.connect(_dsn(args.env_file), statement_cache_size=0, command_timeout=20)
    try:
        async with db.transaction(isolation="repeatable_read", readonly=True):
            a = await db.fetchrow(
                "SELECT a.id,a.reset_count,a.reset_at,a.created_at,a.initial_cash FROM sim_account a JOIN users u ON u.id=a.user_id "
                "WHERE lower(u.email)=lower($1) AND kind='bot'",
                os.environ["PAPER_ATTRIBUTION_OWNER_EMAIL"],
            )
            if not a or (a["reset_at"] or a["created_at"]) > begin:
                raise ValueError("Incomplete opening cohort")
            rows = await db.fetch(
                """SELECT o.ticker,o.id,o.bot_run_id,o.qty,o.side,o.fill_date,o.filled_at,o.fee_bps,
               o.fill_price,o.transaction_cost,o.instrument_id,o.action_id,o.accepted_at,r.context,r.result,r.created_at AS run_at
               FROM sim_order o LEFT JOIN sim_bot_run r ON r.id=o.bot_run_id AND r.account_id=o.account_id AND o.fill_date >= $4
               WHERE o.account_id=$1 AND o.cohort_id=$2 AND o.status='filled'
               AND (o.fill_date IS NULL OR o.fill_date<=$3) ORDER BY o.filled_at,o.id LIMIT 5001""",
                a["id"],
                a["reset_count"],
                args.end,
                args.start,
            )
    finally:
        await db.close()
    if len(rows) > 5000:
        raise ValueError("Ledger exceeds bounded study")
    cash, pos = D(a["initial_cash"]), defaultdict(int)
    fills = []
    for o in rows:
        if not o["fill_date"] or not o["filled_at"] or o["filled_at"] > end:
            raise ValueError("Uncertain execution time")
        if o["fill_date"] < args.start:
            n = o["qty"] if o["side"] == "buy" else -o["qty"]
            pos[o["ticker"]] += n
            cash -= n * D(o["fill_price"]) + D(o["transaction_cost"])
        else:
            if args.start == FORWARD_START and (not o["run_at"] or o["run_at"] < forward_open()):
                raise ValueError("Carry-in decision requires opening book reconciliation")
            fills.append(
                dict(
                    o,
                    context=json.loads(o["context"] or "{}"),
                    result=json.loads(o["result"] or "{}"),
                )
            )
    initial = cash + sum(n * D(quotes["opening"][begin][t]["price"]) for t, n in pos.items() if n)
    return {
        "start": str(args.start),
        "end": str(args.end),
        "opening_nav": float(initial),
        "primary_decision_runs": len(
            {
                o["bot_run_id"]
                for o in fills
                if o["side"] == "buy" and category(o) == "unchanged_rank_rise"
            }
        ),
        "buy_categories": dict(Counter(category(o) for o in fills if o["side"] == "buy")),
        "books": {
            p: replay(p, cash, pos, fills, quotes["terminal"][end], quotes["ex_dividends"])
            for p in POLICIES
        },
    }


async def forward_status(args):
    """Read actionable fills and abstentions without waiting for endpoint prices."""
    db = await asyncpg.connect(_dsn(args.env_file), statement_cache_size=0, command_timeout=12)
    try:
        async with db.transaction(isolation="repeatable_read", readonly=True):
            acct = await db.fetchrow(
                "SELECT a.id,a.reset_count,coalesce(a.reset_at,a.created_at) AS cohort_start FROM sim_account a JOIN users u ON u.id=a.user_id "
                "WHERE lower(u.email)=lower($1) AND a.kind='bot'",
                os.environ["PAPER_ATTRIBUTION_OWNER_EMAIL"],
            )
            if not acct:
                raise ValueError("Owner account not found")
            begin, end = _session_bounds(FORWARD_START, FORWARD_END)
            if acct["cohort_start"] > begin:
                raise ValueError("Account cohort changed during forward study")
            first_open = forward_open()
            runs = await db.fetch(
                "SELECT status,count(*) n FROM sim_bot_run WHERE account_id=$1 "
                "AND created_at BETWEEN $2 AND least(now(),$3) GROUP BY status",
                acct["id"],
                first_open,
                end,
            )
            orders = await db.fetch(
                """SELECT o.*,r.context,r.result FROM sim_order o
                JOIN sim_bot_run r ON r.account_id=o.account_id AND r.id=o.bot_run_id WHERE
                o.account_id=$1 AND o.cohort_id=$2 AND r.created_at >= $3 AND o.filled_at BETWEEN $3 AND least(now(),$4)
                AND o.side='buy' AND o.status='filled' ORDER BY o.filled_at,o.id""",
                acct["id"],
                acct["reset_count"],
                first_open,
                end,
            )
            labeled = [
                (
                    o["bot_run_id"],
                    category(
                        dict(
                            o,
                            context=json.loads(o["context"] or "{}"),
                            result=json.loads(o["result"] or "{}"),
                        )
                    ),
                )
                for o in orders
            ]
            cats = Counter(tag for _, tag in labeled)
            return {
                "first_decision_after": first_open.isoformat(),
                "end": end.isoformat(),
                "runtime_status_counts": {r["status"]: r["n"] for r in runs},
                "buy_fill_categories": dict(cats),
                "withheld_by_primary_rule": cats["unchanged_rank_rise"],
                "primary_decision_runs": len(
                    {k for k, tag in labeled if tag == "unchanged_rank_rise"}
                ),
            }
    finally:
        await db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--start", type=date.fromisoformat)
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--forward-status", action="store_true")
    args = parser.parse_args()
    if not args.forward_status and not all((args.start, args.end, args.receipt)):
        parser.error("replay requires --start --end and --receipt")
    print(
        json.dumps(
            asyncio.run(forward_status(args) if args.forward_status else run(args)), indent=2
        )
    )
