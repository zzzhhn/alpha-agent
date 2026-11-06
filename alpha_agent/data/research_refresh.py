"""Read-only price readiness for the exact full-refresh research universe."""
from datetime import UTC, datetime

from alpha_agent.data.security_identity import valid_research_symbol
from alpha_agent.market_session import latest_completed_xnys_session
from alpha_agent.run_health import MIN_ELIGIBLE, MIN_PRICE_COVERAGE
from alpha_agent.storage.queries import get_priority_universe


async def research_tickers(pool, now: datetime) -> set[str]:
    # Same prior-UTC-day ranking and watchlist union as full shards / ledger.
    tickers = set(await get_priority_universe(pool, top_n=240, before_date=now.date()))
    tickers.update(row["ticker"] for row in await pool.fetch("SELECT DISTINCT ticker FROM user_watchlist"))
    return tickers


async def price_universe(pool, *, required: set[str] | None = None) -> list[str]:
    if required is None:
        required = await research_tickers(pool, datetime.now(UTC))
    rows = await pool.fetch("SELECT DISTINCT ticker FROM daily_signals_slow")
    return sorted(t for t in ({r["ticker"] for r in rows} | required | {"SPY"}) if valid_research_symbol(t))


async def research_price_readiness(pool, *, now: datetime | None = None) -> dict:
    instant = now or datetime.now(UTC)
    expected = latest_completed_xnys_session(instant)
    required = await research_tickers(pool, instant)
    rows = await pool.fetch(
        "SELECT ticker FROM daily_prices WHERE date=$1 AND ticker=ANY($2::text[]) AND close>0",
        expected, sorted(required | {"SPY"}),
    )
    fresh = {r["ticker"] for r in rows}
    coverage = len(required & fresh) / len(required) if required else 0.0
    benchmark_fresh = "SPY" in fresh
    missing = sorted(required - fresh)
    return {
        "ok": True,
        "ready": len(required & fresh) >= MIN_ELIGIBLE and coverage >= MIN_PRICE_COVERAGE and benchmark_fresh,
        "expected_market_date": expected.isoformat(),
        "required_count": len(required),
        "fresh_count": len(required & fresh),
        "coverage": round(coverage, 6),
        "minimum_coverage": MIN_PRICE_COVERAGE,
        "benchmark_fresh": benchmark_fresh,
        "missing_count": len(missing),
        "price_universe_count": len(await price_universe(pool, required=required)),
    }
