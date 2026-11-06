"""Owner-scoped, read-only paper-bot evidence. No quotes or provider calls.

Returns are bounded, close-to-close observations, not an account-lifetime
performance claim. Persisted NAV already includes transaction costs.
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from math import isfinite
from typing import Any

from alpha_agent.market_session import xnys_close, xnys_sessions
from alpha_agent.paper import bot_store as store
from alpha_agent.paper.bot_valuation import summarize_marks
from alpha_agent.paper.market_clock import as_utc

DAILY_LIMIT = 366
RUN_LIMIT = 20
POSITION_LIMIT = 20


def _number(value: Any, *, positive: bool = False) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) and (not positive or number > 0) else None


def _iso(value: Any) -> str | None:
    try:
        return as_utc(value).isoformat()
    except (ValueError, TypeError):
        return None


def calculate_history(
    rows: list[dict], session_closes: dict[date, datetime], now: datetime, *,
    truncated: bool = False,
) -> dict:
    """Pure calculations with an explicit exchange calendar supplied by caller.

    A numeric intraday NAV is not a valid close sample. Cash-only rows also
    need a post-close acquisition time because their SPY may be intraday.
    Sparse/missing NAV or SPY does not invalidate endpoint returns, but cannot
    establish the path's full daily maximum drawdown or turnover denominator.
    """
    rows = sorted(rows, key=lambda row: row['as_of_date'])
    valid, common = [], []
    for row in rows:
        closing = session_closes.get(row['as_of_date'])
        try:
            valued_at = as_utc(row.get('valued_at'))
        except (ValueError, TypeError):
            valued_at = None
        nav = _number(row.get('portfolio_value'), positive=True)
        if (nav is not None and closing is not None and closing <= now
                and valued_at is not None and closing <= valued_at <= now
                and row.get('valuation_quality') in {'cash_only', 'session_close'}):
            valid.append((row['as_of_date'], nav))
            spy = _number(row.get('benchmark_close'), positive=True)
            if spy is not None:
                common.append((row['as_of_date'], nav, spy))

    window = {
        'start_date': None, 'end_date': None, 'sample_count': len(common),
        'expected_sessions': None, 'missing_sessions': None, 'complete': False,
        'bot_return_pct': None, 'spy_return_pct': None, 'cash_return_pct': None,
        'bot_max_drawdown_pct': None, 'reason': 'insufficient_common_observations',
    }
    average_nav = None
    if len(common) >= 2:
        first, last = common[0], common[-1]
        expected = {day for day in session_closes if first[0] <= day <= last[0]}
        observed = {point[0] for point in common}
        missing = len(expected - observed)
        complete = missing == 0 and len(expected) == len(common)
        window.update(
            start_date=first[0].isoformat(), end_date=last[0].isoformat(),
            expected_sessions=len(expected), missing_sessions=missing,
            complete=complete, bot_return_pct=_number((last[1] / first[1] - 1) * 100),
            spy_return_pct=_number((last[2] / first[2] - 1) * 100),
            cash_return_pct=0.0, reason=None if complete else 'incomplete_daily_path',
        )
        if complete:
            peak, drawdown = common[0][1], 0.0
            for _, nav, _ in common:
                peak = max(peak, nav)
                drawdown = max(drawdown, (1 - nav / peak) * 100)
            window['bot_max_drawdown_pct'] = drawdown
            average_nav = _number(sum(point[1] / len(common) for point in common), positive=True)

    return {
        'history': {
            'scope': 'current_cohort_recent_366', 'sample_count': len(rows),
            'valid_nav_count': len(valid),
            'null_nav_count': sum(row.get('portfolio_value') is None for row in rows),
            'incomplete_nav_count': len(rows) - len(valid),
            'first_date': rows[0]['as_of_date'].isoformat() if rows else None,
            'last_date': rows[-1]['as_of_date'].isoformat() if rows else None,
            'truncated': truncated,
        },
        'matched_window': window,
        'average_nav': average_nav,
    }


def _current_valuation(account: dict, positions: list[dict], now: datetime) -> dict:
    cash = _number(account.get('cash'))
    summary = None
    if cash is not None and len(positions) <= POSITION_LIMIT:
        summary = summarize_marks(positions, cash, now)
    nav = _number(summary['portfolio_value']) if summary else None
    invested = _number(nav - cash) if nav is not None and cash is not None else None
    return {
        'cash': cash, 'portfolio_value': nav, 'invested_value': invested,
        'exposure_pct': _number(invested / nav * 100) if invested is not None and nav > 0 else None,
        'quality': summary['valuation_quality'] if summary else 'partial',
        'valued_at': _iso(summary['valued_at']) if summary else None,
    }


def _usage(runs: list[dict]) -> dict:
    def total(key):
        values = [_number(row.get(key)) for row in runs]
        return int(sum(values)) if all(value is not None and value >= 0 for value in values) else None

    return {
        'scope': 'recent_20_runs_account_lifetime', 'run_count': len(runs),
        'first_run_at': _iso(runs[-1].get('created_at')) if runs else None,
        'last_run_at': _iso(runs[0].get('created_at')) if runs else None,
        'prompt_tokens': total('prompt_tokens'),
        'completion_tokens': total('completion_tokens'), 'llm_calls': total('llm_calls'),
        'cost_usd': None, 'cost_reason': 'provider_pricing_unavailable',
        'usage_basis': 'persisted_counts_may_omit_unreported_usage',
    }


async def read_performance(pool: Any, user_id: int, account_id: int) -> dict:
    """Read one coherent MVCC snapshot without locks, writes, or network calls.

    Output size is bounded: 366 daily rows, 20 run rows, 20 position rows plus
    one guard, and one aggregate order row. Aggregate costs/counts cover only
    the current reset cohort; recent-run usage explicitly has lifetime scope.
    """
    now = datetime.now(UTC)
    async with pool.acquire() as conn:
        async with conn.transaction(isolation='repeatable_read', readonly=True):
            account = await store.bot_account(conn, user_id, account_id)
            cohort = int(account['reset_count'] or 0)
            rows = await conn.fetch(
                'SELECT as_of_date,portfolio_value,benchmark_close,valuation_quality,valued_at '
                'FROM sim_equity_daily WHERE account_id=$1 AND cohort_id=$2 '
                "AND valuation_quality IS DISTINCT FROM 'pre_account_invalid' "
                'ORDER BY as_of_date DESC LIMIT $3', account_id, cohort, DAILY_LIMIT + 1,
            )
            truncated = len(rows) > DAILY_LIMIT
            rows = [dict(row) for row in rows[:DAILY_LIMIT]]
            # This is a local exchange calendar, not an external price source.
            closes = {}
            if rows:
                first, last = min(row['as_of_date'] for row in rows), max(row['as_of_date'] for row in rows)
                try:
                    closes = {day: xnys_close(day) for day in xnys_sessions(first, last)}
                except (ValueError, OverflowError):
                    # Unknown/out-of-calendar dates cannot prove a daily path.
                    closes = {}
            history = calculate_history(rows, closes, now, truncated=truncated)
            window = history['matched_window']
            if rows and not closes:
                window['reason'] = 'exchange_calendar_unavailable'
            start = closes.get(date.fromisoformat(window['start_date'])) if window['start_date'] else None
            end = closes.get(date.fromisoformat(window['end_date'])) if window['end_date'] else None
            positions = await conn.fetch(
                'SELECT ticker,qty,avg_cost,mark_price,mark_at,price_quality '
                'FROM sim_position WHERE account_id=$1 AND cohort_id=$2 AND qty>0 '
                'ORDER BY ticker LIMIT $3', account_id, cohort, POSITION_LIMIT + 1,
            )
            orders = dict(await conn.fetchrow(
                "SELECT count(*) FILTER (WHERE status='filled') AS filled, "
                "count(*) FILTER (WHERE status='pending') AS pending, "
                "count(*) FILTER (WHERE status='failed') AS failed, "
                "count(*) FILTER (WHERE status='expired') AS expired, "
                "count(*) FILTER (WHERE status='cancelled') AS cancelled, "
                "COALESCE(sum(transaction_cost) FILTER (WHERE status='filled'),0) AS paid_fees, "
                "count(*) FILTER (WHERE status='filled' AND transaction_cost IS NULL) AS missing_fees, "
                "count(*) FILTER (WHERE status='filled' AND filled_at IS NULL) AS undated_fills, "
                "count(*) FILTER (WHERE status='filled' AND filled_at>$3 AND filled_at<=$4 "
                "AND (fill_price IS NULL OR fill_price<=0 OR qty<=0)) AS invalid_window_fills, "
                "COALESCE(sum(abs(qty*fill_price)) FILTER (WHERE status='filled' "
                'AND filled_at>$3 AND filled_at<=$4),0) AS window_gross_notional '
                'FROM sim_order WHERE account_id=$1 AND cohort_id=$2',
                account_id, cohort, start, end,
            ))
            runs = await conn.fetch(
                'SELECT created_at,prompt_tokens,completion_tokens,llm_calls FROM sim_bot_run '
                'WHERE account_id=$1 ORDER BY created_at DESC,id DESC LIMIT $2', account_id, RUN_LIMIT,
            )

    average_nav = history['average_nav']
    window_gross = orders.pop('window_gross_notional')
    gross = _number(window_gross) if start is not None else None
    undated, invalid = orders.pop('undated_fills'), orders.pop('invalid_window_fills')
    turnover_reason = (
        'insufficient_common_observations' if start is None else
        'incomplete_daily_path' if not window['complete'] else
        'undated_or_invalid_fills' if undated or invalid or gross is None else
        'invalid_average_nav' if average_nav is None else None
    )
    turnover = {
        'window_start': _iso(start), 'window_end': _iso(end),
        'gross_filled_notional': gross if not undated and not invalid else None,
        'average_nav': average_nav,
        'ratio_pct': _number(gross / average_nav * 100) if turnover_reason is None else None,
        'reason': turnover_reason,
        'basis': 'two_sided_gross_notional_over_mean_daily_nav_start_exclusive_end_inclusive',
    }
    orders['paid_fees'] = None if orders.pop('missing_fees', 0) else _number(orders['paid_fees'])
    return {
        'account_id': account_id, 'cohort_id': cohort, 'as_of': now.isoformat(),
        'history': history['history'], 'matched_window': window,
        'valuation': _current_valuation(account, [dict(row) for row in positions], now),
        'orders': {'scope': 'current_cohort', **orders, 'rejected': None,
                   'rejection_reason': 'no_rejected_order_status'},
        'turnover': turnover, 'llm': _usage([dict(row) for row in runs]),
        'comparators': {
            'spy': {'basis': 'raw_price_no_dividends_no_trading_costs',
                    'caveat': 'price_only_reference_not_a_simulated_tradable_ledger'},
            'cash': {'basis': 'zero_interest_no_fees'},
            'deterministic': {'available': False, 'return_pct': None,
                              'reason': 'no_simulated_ledger'},
        },
    }
