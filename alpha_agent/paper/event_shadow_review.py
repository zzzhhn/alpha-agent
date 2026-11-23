"""First-review gate. Never selects or enables a strategy based on its backtest."""

from datetime import UTC, datetime

from alpha_agent.market_session import xnys_sessions
from alpha_agent.paper.market_clock import NEW_YORK, as_utc, market_session
from alpha_agent.paper.event_shadow_policy import POLICY


async def record_session_sample(pool, now=None):
    now = now or datetime.now(UTC)
    session = market_session(now)
    if not session["is_open"]:
        return
    # Last 10 regular minutes only (also on shortened sessions). These are NOT
    # official closing marks. Don't drag yesterday's price through an open leg.
    if (as_utc(session["close_at"]) - now).total_seconds() > 600:
        return
    await pool.execute(
        """
        INSERT INTO event_shadow_session_sample(policy,session_date,sleeve,sampled_at,nav,open_positions)
        SELECT $1,$2,b.sleeve,$3,CASE WHEN count(t.id)=0 THEN b.free_cash+b.restricted_cash END,count(t.id)
        FROM event_shadow_book b LEFT JOIN event_shadow_trial t
          ON t.sleeve=b.sleeve AND t.policy=$1 AND t.status='open'
        GROUP BY b.sleeve,b.free_cash,b.restricted_cash
        ON CONFLICT(policy,session_date,sleeve) DO UPDATE SET sampled_at=EXCLUDED.sampled_at,
           nav=EXCLUDED.nav,open_positions=EXCLUDED.open_positions
        WHERE event_shadow_session_sample.sampled_at < EXCLUDED.sampled_at
        """,
        POLICY,
        now.astimezone(NEW_YORK).date(),
        now,
    )


async def review_gate(pool):
    rows = await pool.fetch(
        """
        SELECT session_date,sleeve,nav,initial_cash FROM event_shadow_session_sample
        JOIN event_shadow_book USING(sleeve) WHERE policy=$1 ORDER BY session_date,sleeve
        """,
        POLICY,
    )
    by_day = {}
    initial = {}
    for r in rows:
        by_day.setdefault(r["session_date"], {})[r["sleeve"]] = r["nav"]
        initial[r["sleeve"]] = float(r["initial_cash"])
    days = list(by_day)
    expected = xnys_sessions(days[0], days[-1]) if days else []
    comparable = [
        d for d in days if len(by_day[d]) == 3 and all(v is not None for v in by_day[d].values())
    ]
    complete = bool(expected) and len(comparable) == len(expected)
    performance = {}
    metrics = await pool.fetch(
        """
        SELECT sleeve,count(*) FILTER(WHERE status='closed') AS closed,
           sum(abs(qty*entry_price)+coalesce(abs(qty*exit_price),0)) traded,
           sum(fees) fees,min(realized_pnl) worst_trade_usd
        FROM event_shadow_trial WHERE policy=$1 GROUP BY sleeve""",
        POLICY,
    )
    for r in metrics:
        sleeve = r["sleeve"]
        drawdown = total = None
        if complete:
            peak = initial[sleeve]
            drawdown = 0.0
            for d in comparable:
                nav = float(by_day[d][sleeve])
                peak = max(peak, nav)
                drawdown = min(drawdown, nav / peak - 1)
            total = nav / initial[sleeve] - 1
        performance[sleeve] = {
            "return": total,
            "max_sampled_drawdown": drawdown,
            "fees": r["fees"],
            "two_sided_notional": r["traded"],
            "worst_trade_usd": r["worst_trade_usd"],
        }
    # Conservative clustering: multiple filings/headlines for one issuer in a
    # session are at most one observation. Abstentions alone are not evidence
    # of tradable alpha. An expired/unknown alternative is never scored zero.
    paired = await pool.fetchval(
        """
       SELECT count(*) FROM (
        SELECT DISTINCT ticker,(entry_after AT TIME ZONE 'America/New_York')::date
        FROM (SELECT event_id,ticker,entry_after FROM event_shadow_trial WHERE policy=$1
              GROUP BY event_id,ticker,entry_after HAVING count(DISTINCT sleeve)=3
              AND bool_and(status IN ('closed','abstained')) AND bool_or(status='closed')
              AND count(DISTINCT entry_at) <= 1 AND count(DISTINCT exit_at) <= 1) e
       ) clusters""",
        POLICY,
    )
    return {
        "observed_sessions": len(comparable),
        "scheduled_sessions_in_span": len(expected),
        "paired_event_clusters": paired,
        "session_target": 20,
        "event_target": 30,
        "review_eligible": complete and len(comparable) >= 20 and paired >= 30,
        "policy": POLICY,
        "metrics": performance,
        "auto_promote": False,
    }
