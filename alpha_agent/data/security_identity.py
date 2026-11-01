"""Known ticker reuse boundaries for this project's historical equity universe.

PARA in the historical S&P panel means Paramount Global, not the unrelated
issuer that reused PARA in August 2026. Do not automatically relabel it PSKY:
the 2025 merger offered cash/stock elections, and our 2026 fills were invalid.
"""
from datetime import date

RETIRED_RESEARCH_SYMBOLS = {"PARA": date(2025, 8, 6)}


def valid_research_symbol(ticker: str, as_of: date | None = None) -> bool:
    boundary = RETIRED_RESEARCH_SYMBOLS.get(ticker)
    return boundary is None or (as_of or date.today()) <= boundary


async def book_identity_issues(pool, strategy_id: int) -> list[dict]:
    rows = await pool.fetch(
        "SELECT DISTINCT ticker FROM l2_order WHERE strategy_id=$1 "
        "AND ticker=ANY($2::text[]) AND status='filled' AND signal_date>$3",
        strategy_id, list(RETIRED_RESEARCH_SYMBOLS), date(2025, 8, 6))
    return [{"ticker": r["ticker"], "reason": "reused_ticker_wrong_issuer",
             "action": "archive_without_rewriting_history"} for r in rows]
