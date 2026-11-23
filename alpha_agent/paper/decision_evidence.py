"""Read-only shadow review of the *frozen* bot context, never an execution dependency."""

from datetime import timedelta

from fastapi import HTTPException

from alpha_agent.paper.bot_store import bot_account, unpack
from alpha_agent.paper.market_clock import as_utc


def screen_actions(context, result):
    """A rating/rank is not a forecast. Reductions are kept separate from proposed buys."""
    symbols = {str(i.get("instrument_id")): i.get("ticker") for i in context.get("instruments", [])}
    recs = {r.get("ticker"): r for r in context.get("recommendations", [])}
    positions = {p.get("ticker"): p for p in context.get("account", {}).get("positions", [])}
    nav = context.get("account", {}).get("portfolio_value")
    actions = []
    for a in (result.get("decision") or {}).get("actions") or []:
        if a.get("type") != "set_target_weight":
            continue
        ticker = symbols.get(str(a.get("instrument_id")))
        rec = recs.get(ticker, {})
        quote = (context.get("quotes") or {}).get(ticker) or {}
        qty = positions.get(ticker, {}).get("qty", 0)
        target = a.get("target_weight")
        known_weight = (
            0
            if not qty
            else (
                qty * quote["price"] / nav
                if nav and quote.get("price") and quote.get("quality") == "fresh"
                else None
            )
        )
        if ticker is None or target is None:
            reason = "insufficient_evidence"
        elif qty and (target == 0 or (known_weight is not None and target < known_weight)):
            reason = "review_risk_reduction"
        elif known_weight is None:
            reason = "insufficient_evidence"
        elif target == known_weight:
            reason = "unchanged"
        else:
            used = {i for i in a.get("evidence_ids", []) if isinstance(i, str)}
            tier_change = bool(
                rec.get("previous_tier")
                and rec.get("tier")
                and rec["previous_tier"] != rec["tier"]
                and rec.get("evidence_id") in used
            )
            reason = "review_rating_change" if tier_change else "withhold_unproven_replacement"
        actions.append({"ticker": ticker, "disposition": reason})
    return actions


async def decision_evidence(pool, user_id, account_id, run_id):
    await bot_account(pool, user_id, account_id)
    row = await pool.fetchrow(
        "SELECT context,result FROM sim_bot_run WHERE id=$1 AND account_id=$2", run_id, account_id
    )
    if row is None:
        raise HTTPException(404, "Run not found")
    context, result = unpack(row["context"]), unpack(row["result"])
    cutoff = context.get("created_at")
    # Only IDs explicitly present in model input count as actually seen.
    seen = [
        key
        for key in (context.get("evidence_ids") or [])
        if isinstance(key, str) and key.startswith("official:")
    ]
    comparable = []
    if cutoff:
        at = as_utc(cutoff)
        tickers = [i["ticker"] for i in context.get("instruments", []) if i.get("ticker")]
        comparable = await pool.fetch(
            "SELECT ticker,title,first_seen_at FROM official_event_watch WHERE ticker=ANY($1::text[]) "
            "AND first_seen_at BETWEEN $2 AND $3 ORDER BY first_seen_at DESC,id DESC LIMIT 8",
            tickers,
            at - timedelta(days=2),
            at,
        )
    return {
        "context_at": cutoff,
        "seen_event_ids": seen,
        "shadow_events_known_by_then": [dict(x) for x in comparable],
        "actions": screen_actions(context, result),
        "context_available": bool(cutoff),
    }
