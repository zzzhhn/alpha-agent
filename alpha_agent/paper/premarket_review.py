"""Forward-only timing experiment. No LLM, order writer or mutable signal inputs."""

from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import UTC, datetime, timedelta

from alpha_agent.data.security_identity import valid_research_symbol
from alpha_agent.market_session import _xnys_calendar
from alpha_agent.paper.event_shadow_policy import direction_for
from alpha_agent.paper.intraday import fetch_bars
from alpha_agent.paper.market_clock import NEW_YORK, as_utc, market_session

MIN = timedelta(minutes=1)
# One-way assumptions, matching the event shadow's fee and slippage rates.
FEE, SLIP = 0.001, 0.001
log = logging.getLogger(__name__)


def slot(now):
    session = market_session(now)
    day = now.astimezone(NEW_YORK).date()
    if day.isoformat() != session["session_date"]:
        return None
    opening, closing = (as_utc(session[k]) for k in ("open_at", "close_at"))
    for stage, cutoff in (
        ("premarket", opening - 10 * MIN),
        ("open_review", opening + 30 * MIN),
        ("evaluation", closing + 5 * MIN),
    ):
        if cutoff <= now < cutoff + 5 * MIN:
            return day, stage, cutoff, closing
    return None


def classify(ranked, holdings, events, complete):
    """At most two changed equal-weight slots. Other evidence remains visible."""
    baseline = ranked[:50]
    directions = {}
    for e in events:
        directions.setdefault(e["ticker"], set()).add(direction_for(e)[0])
    notes, changes = [], []
    for ticker, ds in directions.items():
        tag = "risk" if ds == {"short"} else "attention" if ds == {"long"} else "review"
        notes.append(
            dict(ticker=ticker, tag=tag, in_top=ticker in baseline, held=ticker in holdings)
        )
    if complete and len(baseline) == 50:
        risk = [t for t in baseline if directions.get(t) == {"short"}][:2]
        additions = [t for t in ranked[50:] if directions.get(t) == {"long"}][:2]
        # Prioritize risk cuts; don't remove another flagged name to fund an addition.
        outgoing = (
            risk
            + [t for t in reversed(baseline) if t not in directions][
                : max(0, len(additions) - len(risk))
            ]
        )
        changes = [
            dict(out=t, into=additions[i] if i < len(additions) else None)
            for i, t in enumerate(outgoing[:2])
        ]
    return notes, changes


async def source_coverage(db, cutoff, top):
    return await db.fetchrow(
        """WITH recent AS (
            SELECT DISTINCT ticker, source FROM official_source_coverage
            WHERE first_success_at <= $1 AND last_success_at >= $1::timestamptz - interval '20 minutes'
              AND (failed_at IS NULL OR failed_at > $1)
        )
        SELECT (SELECT count(*) FROM official_event_source WHERE tracked_since <= $1) AS tracked,
               count(*) AS recent,
               count(DISTINCT ticker) FILTER (WHERE ticker = ANY($2::text[])) AS top_covered
        FROM recent""",
        cutoff, top,
    )


async def capture(db, owner, day, cutoff, anchor):
    cal = _xnys_calendar()
    previous = cal.previous_session(day)
    since = as_utc(cal.session_close(previous).to_pydatetime())
    baseline_run = await db.fetchrow(
        """SELECT id,input_data_cutoff,finished_at FROM research_run WHERE run_type='daily_close' AND
        status='complete' AND scheduled_for_date=$1 AND finished_at<=$2
        ORDER BY finished_at DESC,id DESC LIMIT 1""",
        previous.date(),
        anchor,
    )
    run = baseline_run["id"] if baseline_run else None
    if baseline_run:
        # If the close job consumed post-close inputs, don't present the same
        # information again as an advantage of computing later.
        since = max(since, baseline_run["input_data_cutoff"] or baseline_run["finished_at"])
    ranked = [
        r["ticker"]
        for r in await db.fetch(
            """SELECT ticker FROM rating_snapshot
        WHERE run_id=$1 AND eligible AND in_universe AND rank IS NOT NULL
        ORDER BY composite_z DESC NULLS LAST,rank,ticker""",
            run,
        )
        if valid_research_symbol(r["ticker"], previous.date())
    ]
    holdings = {
        r["ticker"]
        for r in await db.fetch(
            """SELECT o.ticker FROM sim_order o
        JOIN sim_account a ON a.id=o.account_id WHERE a.user_id=$1 AND a.kind='bot'
        AND o.status='filled' AND o.filled_at<=$2 AND o.cohort_id=a.reset_count
        GROUP BY o.ticker HAVING SUM(CASE WHEN o.side='buy' THEN o.qty ELSE -o.qty END)>0""",
            owner,
            cutoff,
        )
    }
    rows = await db.fetch(
        """SELECT * FROM (SELECT DISTINCT ON (ticker,source,source_key)
        ticker,source,source_key,id,title,url,status,published_at,published_at_quality,first_seen_at
        FROM official_event_watch WHERE first_seen_at>$1 AND first_seen_at<=$2
        ORDER BY ticker,source,source_key,first_seen_at DESC,id DESC) v
        ORDER BY first_seen_at DESC,id DESC LIMIT 201""",
        since,
        cutoff,
    )
    events = [
        dict(r)
        for r in rows[:200]
        if r["published_at_quality"] in ("source_timestamp", "sec_accepted")
        and r["published_at"]
        and since < r["published_at"] <= cutoff
    ]
    # No sentiment, later LLM enrichments or late backfills. Press and broad
    # market context can flag a risk for human review but cannot move a slot.
    news = await db.fetch(
        """(SELECT ticker,headline AS title,url,published_at,fetched_at,source
        FROM news_items WHERE ticker=ANY($3::text[]) AND published_at>$1 AND published_at<=$2
        AND fetched_at<=$2 ORDER BY published_at DESC,id DESC LIMIT 8)
        UNION ALL (SELECT NULL,title,url,published_at,fetched_at,source FROM macro_events
        WHERE published_at>$1 AND published_at<=$2 AND fetched_at<=$2
        ORDER BY published_at DESC,id DESC LIMIT 4)""",
        since,
        cutoff,
        list(set(ranked) | holdings),
    )
    sources = await source_coverage(db, cutoff, ranked[:50])
    complete = len(rows) <= 200 and len(ranked) >= 50 and sources["recent"] > 0
    notes, changes = classify(ranked, holdings, events, complete)
    return dict(
        policy="premarket_guidance_v1",
        run_id=run,
        baseline=ranked[:50],
        cutoff=cutoff.isoformat(),
        since=since.isoformat(),
        tracked=sources["tracked"],
        recent=sources["recent"],
        top_covered=sources["top_covered"],
        context=[
            dict(
                ticker=r["ticker"],
                title=r["title"],
                url=r["url"],
                source=r["source"],
                at=r["published_at"].isoformat(),
                new=r["fetched_at"] > anchor,
            )
            for r in news
        ],
        truncated=len(rows) > 200,
        comparable=complete,
        notes=notes,
        changes=changes,
        events=[
            {
                k: str(v) if k in ("published_at", "first_seen_at") else v
                for k, v in e.items()
                if k not in ("source_key", "published_at_quality")
            }
            for e in events
        ],
    )


def paired_return(bars, entry, close):
    """Exact regular minute after decision -> session close, two adverse fills."""
    by_time = {as_utc(b["start"]): b for b in bars}
    a, b = by_time.get(entry), by_time.get(close - MIN)
    if (
        not a
        or not b
        or entry >= close
        or any(
            x.get("price_basis") != "raw_unadjusted"
            or not x.get("corporate_actions_known")
            or x.get("corporate_actions")
            or not (x.get("volume") or 0) > 0
            for x in (a, b)
        )
    ):
        return None
    p, q = a.get("open"), b.get("close")
    if not all(isinstance(x, (int, float)) and math.isfinite(x) and x > 0 for x in (p, q)):
        return None
    return q * (1 - SLIP) * (1 - FEE) / (p * (1 + SLIP) * (1 + FEE)) - 1


def unpack(value):
    return json.loads(value) if isinstance(value, str) else value


async def bars_for(ticker, now):
    try:
        return await fetch_bars(ticker, now)
    except Exception as exc:
        # Provider-specific failures are evidence gaps, never zero returns.
        log.warning("Premarket review missing bars: %s %s", ticker, type(exc).__name__)
        return []


async def open_quotes(payload, cutoff, now):
    # Check actionable names first, then at most four symbols in total. Prices
    # are regular-session observations for context, never order authorizations.
    names = list(
        dict.fromkeys(
            [t for c in payload["changes"] for t in c.values() if t]
            + [n["ticker"] for n in payload["notes"]]
        )
    )[:4]

    async def quote(t):
        bars = await bars_for(t, now)
        candidates = [
            b
            for b in bars
            if cutoff - 5 * MIN < as_utc(b["end"]) <= cutoff
            and b["price_basis"] == "raw_unadjusted"
            and (b["close"] or 0) > 0
            and (b["volume"] or 0) > 0
        ]
        bar = max(candidates, key=lambda b: b["end"], default=None)
        return (t, {"price": bar["close"], "at": bar["end"]} if bar else None)

    return dict(await asyncio.gather(*(quote(t) for t in names)))


async def evaluate(db, owner, day, close, now):
    action = await db.fetchval(
        """SELECT min(r.finished_at) FROM sim_bot_run r JOIN sim_account a
        ON a.id=r.account_id WHERE a.user_id=$1 AND a.kind='bot' AND r.trading_session=$2
        AND r.trigger='open_after' AND r.status IN ('completed','no_trade','partial')
        AND r.llm_calls>0 AND r.result->'decision'->>'decision' IN ('rebalance','no_trade')""",
        owner,
        day,
    )
    rows = await db.fetch(
        """SELECT stage,captured_at,payload FROM premarket_review WHERE
        user_id=$1 AND session_date=$2 AND stage!='evaluation' ORDER BY captured_at""",
        owner,
        day,
    )
    result, cache = {}, {}
    for r in rows:
        p = unpack(r["payload"])
        if not action or not p["comparable"]:
            result[r["stage"]] = {"status": "no_decision" if not action else "incomplete"}
            continue
        entry = max(action, r["captured_at"]).replace(second=0, microsecond=0) + MIN
        delta = 0.0
        legs = []
        if entry >= close:
            result[r["stage"]] = {"status": "too_late"}
            continue
        for change in p["changes"]:
            returns = []
            for t in (change["out"], change["into"]):
                if t and t not in cache:
                    cache[t] = await bars_for(t, now)
                returns.append(paired_return(cache[t], entry, close) if t else 0.0)
            legs.append({**change, "baseline_net": returns[0], "variant_net": returns[1]})
            if None in returns:
                delta = None
                break
            delta += (returns[1] - returns[0]) / 50
        result[r["stage"]] = dict(
            status="missing_bars" if delta is None else "measured",
            entry=entry.isoformat(),
            close=close.isoformat(),
            legs=legs,
            delta_bps=None if delta is None else round(delta * 10000, 3),
        )
    return dict(
        results=result,
        decision_at=action.isoformat() if action else None,
        execution="paired_raw_minute_v1",
        fee_bps=10,
        slippage_bps=10,
    )


async def tick(pool, owner, clock=lambda: datetime.now(UTC)):
    now = clock()
    target = slot(now)
    if not target:
        return {"status": "outside_window"}
    day, stage, cutoff, close = target
    async with pool.acquire() as db:
        async with db.transaction(isolation="repeatable_read", readonly=True):
            if await db.fetchval(
                """SELECT 1 FROM premarket_review WHERE user_id=$1
                                  AND session_date=$2 AND stage=$3""",
                owner,
                day,
                stage,
            ):
                return {"status": "already_recorded"}
            if stage != "evaluation":
                # Require one complete prospective window after the schema ships.
                # This also keeps rolling deployments usable before the migration.
                ready = await db.fetchval(
                    "SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version=$1 "
                    "AND applied_at <= $2::timestamptz - interval '20 minutes')",
                    "V065__official_source_coverage", cutoff,
                )
                if not ready:
                    return {"status": "source_history_warming", "stage": stage}
                anchor = cutoff if stage == "premarket" else cutoff - 40 * MIN
                payload = await capture(db, owner, day, cutoff, anchor)
    if stage == "evaluation":
        payload = await evaluate(pool, owner, day, close, now)
    elif stage == "open_review":
        payload["quotes"] = await open_quotes(payload, cutoff, now)
        payload["new_event_ids"] = [
            e["id"] for e in payload["events"] if as_utc(e["first_seen_at"]) > anchor
        ]
    captured = clock()
    if captured >= cutoff + 5 * MIN and stage != "evaluation":
        return {"status": "missed_window"}
    inserted = await pool.fetchval(
        """INSERT INTO premarket_review(user_id,session_date,stage,captured_at,payload)
            VALUES ($1,$2,$3,$4,$5::jsonb) ON CONFLICT DO NOTHING RETURNING 1""",
        owner,
        day,
        stage,
        captured,
        json.dumps(payload),
    )
    return {"status": "recorded" if inserted else "already_recorded", "stage": stage}
