"""Dated XNYS closes and valuation for human daily-close books."""
from datetime import date, timedelta
from typing import Any

from alpha_agent.market_session import xnys_close, xnys_sessions


async def read_daily_closes(
    conn: Any, tickers: list[str], session: date, *, include_reference: bool = False,
) -> dict[str, dict]:
    """Read only valid completed-session closes at or before the valuation date."""
    if not tickers:
        return {}
    dates = xnys_sessions(session - timedelta(days=14), session)[-5:] if include_reference else [session]
    rows = await conn.fetch(
        "SELECT DISTINCT ON (ticker) ticker,date,close FROM daily_prices "
        "WHERE ticker=ANY($1::text[]) AND date=ANY($2::date[]) "
        "AND close>0 AND close<'Infinity'::double precision ORDER BY ticker,date DESC",
        list(set(tickers)), dates,
    )
    return {row['ticker']: dict(row) for row in rows}


def summarize_daily_closes(
    positions: list[dict], closes: dict[str, dict], cash: float, session: date,
) -> dict:
    """Require the session's close for every live position in a formal NAV."""
    closing = xnys_close(session)
    marks = {}
    basis = {}
    for position in positions:
        ticker = position['ticker']
        quote = closes.get(ticker)
        price = quote['close'] if quote is not None else None
        day = quote['date'] if quote is not None else None
        basis[ticker] = day
        marks[ticker] = {
            'price': price, 'as_of': closing if day == session else xnys_close(day) if day else None,
            'quality': 'missing' if day is None else 'session_close' if day == session else 'stale',
        }

    def amounts():
        value = cash + sum(marks[p['ticker']]['price'] * p['qty'] for p in positions)
        pnl = sum((marks[p['ticker']]['price'] - p['avg_cost']) * p['qty'] for p in positions)
        return value, pnl

    issues = [{'ticker': ticker, 'quality': mark['quality'],
               'as_of': mark['as_of'].isoformat() if mark['as_of'] else None}
              for ticker, mark in marks.items() if mark['quality'] != 'session_close']
    value, pnl = amounts() if not issues else (None, None)
    reference = None
    if issues and all(day is not None for day in basis.values()):
        ref_value, ref_pnl = amounts()
        oldest, newest = min(basis.values()), max(basis.values())
        reference = {
            'portfolio_value': ref_value, 'unrealized_pnl': ref_pnl, 'valuation_quality': 'indicative',
            'market_date': newest.isoformat(), 'valued_at': xnys_close(oldest).isoformat(),
            'newest_mark_at': xnys_close(newest).isoformat(),
        }
    return {
        'marks': marks, 'portfolio_value': value, 'unrealized_pnl': pnl,
        'valuation_quality': 'partial' if issues else 'session_close' if marks else 'cash_only',
        'valued_at': closing if not issues else None,
        'valuation_issues': issues, 'reference_valuation': reference,
    }
