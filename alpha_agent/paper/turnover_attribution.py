"""Owner-scoped paper ledger replay and terminal-price turnover attribution.

Actual means recorded simulated fills. Hold and reduce_only start at the same
cash and positions, are accounting controls, and are not strategy backtests.
No provider calls, portfolio writes, or adjusted/stale quote substitutions.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from math import fsum, isclose, isfinite
from typing import Any

from alpha_agent.market_session import _xnys_calendar, xnys_close, xnys_sessions
from alpha_agent.paper.bot_store import bot_account
from alpha_agent.paper.market_clock import NEW_YORK, as_utc

MAX_WINDOW_DAYS = 31
MAX_LEDGER_FILLS = 5_000


def _num(value: Any, *, positive: bool = False) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) and (not positive or number > 0) else None


def _nonnegative(value: Any) -> float | None:
    number = _num(value)
    return number if number is not None and number >= 0 else None


def _instant(value: Any) -> datetime | None:
    try:
        return as_utc(value)
    except (TypeError, ValueError):
        return None


def _sum(values: Any) -> float | None:
    items = list(values)
    return fsum(items) if all(value is not None for value in items) else None


def _evidence(value: Any) -> dict:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return {}
    return value if isinstance(value, dict) else {}


def _qty(row: dict) -> int | None:
    value = row.get('qty')
    return value if type(value) is int and value > 0 else None


def _direction(row: dict) -> int | None:
    return {'buy': 1, 'sell': -1}.get(row.get('side'))


def _timing_ok(row: dict) -> bool:
    stamp = _instant(row.get('filled_at'))
    return stamp is not None and stamp.astimezone(NEW_YORK).date() == row.get('fill_date')


def _slippage(row: dict) -> tuple[float | None, float | None, str | None]:
    """Observed simulator reference, never today’s configured slippage rate."""
    evidence = _evidence(row.get('execution_evidence'))
    bar = _evidence(evidence.get('bar'))
    reference = _num(row.get('reference_price'), positive=True)
    price = _num(row.get('fill_price'), positive=True)
    raw_open = _num(bar.get('open'), positive=True)
    proven_reference = _num(evidence.get('reference_price'), positive=True)
    proven_fill = _num(evidence.get('fill_price'), positive=True)
    qty, direction = _qty(row), _direction(row)
    stamp = _instant(row.get('filled_at'))
    start, end = _instant(bar.get('start')), _instant(bar.get('end'))
    fetched, confirmed = _instant(bar.get('fetched_at')), _instant(evidence.get('confirmed_at'))
    if (reference is None or price is None or raw_open is None or proven_reference is None
            or proven_fill is None or qty is None or direction is None
            or not _timing_ok(row) or start is None or end is None or start != stamp
            or end - start != timedelta(minutes=1) or fetched is None or confirmed is None
            or not end <= fetched <= confirmed
            or bar.get('price_basis') != 'raw_unadjusted' or not bar.get('source')
            or bar.get('corporate_actions')
            or bar.get('corporate_actions_known') is not True
            or not isclose(reference, raw_open, rel_tol=1e-9)
            or not isclose(reference, proven_reference, rel_tol=1e-9)
            or not isclose(price, proven_fill, rel_tol=1e-9)):
        return None, None, None
    return direction * qty * (price - reference), reference, str(bar['source'])


def _apply(cash: float | None, positions: dict | None, row: dict, qty: int | None,
           fee: float | None) -> tuple[float | None, dict | None]:
    direction = _direction(row)
    price = _num(row.get('fill_price'), positive=True)
    if qty is None or direction is None:
        return None, None
    if not qty:
        return cash, positions
    if positions is not None:
        ticker = row['ticker']
        new_qty = positions.get(ticker, 0) + direction * qty
        if new_qty < 0:
            positions = None
        elif new_qty:
            positions[ticker] = new_qty
        else:
            positions.pop(ticker, None)
    if cash is None or price is None or fee is None:
        cash = None
    else:
        cash -= direction * qty * price + fee
    return cash, positions


def _eligible_fee(row: dict, actual_qty: int | None, eligible_qty: int | None,
                  recorded_fee: float | None) -> float | None:
    if eligible_qty is None:
        return None
    if not eligible_qty:
        return 0.0
    if eligible_qty == actual_qty:
        return recorded_fee
    fee_bps = _nonnegative(row.get('fee_bps'))
    price = _num(row.get('fill_price'), positive=True)
    if actual_qty is None or fee_bps is None or price is None or recorded_fee is None:
        return None
    expected = price * actual_qty * fee_bps / 10_000
    if not isclose(recorded_fee, expected, rel_tol=1e-9, abs_tol=1e-8):
        return None
    return price * eligible_qty * fee_bps / 10_000


def _difference(left: float | None, right: float | None) -> float | None:
    return left - right if left is not None and right is not None else None


def _matching_ledger_nav(sample: dict | None, cash: float | None, stamp: datetime) -> float | None:
    if not sample or cash is None:
        return None
    sample_cash = _num(sample.get('cash'))
    valued_at = _instant(sample.get('valued_at'))
    quality = sample.get('valuation_quality')
    if (sample_cash is None or not isclose(sample_cash, cash, rel_tol=1e-10, abs_tol=0.01)
            or valued_at is None or valued_at < stamp
            or quality not in {'session_close', 'cash_only'}):
        return None
    return _num(sample.get('portfolio_value'), positive=True)


def _scenario(cash: float | None, positions: dict | None, prices: dict,
              opening_nav: float | None, endpoint_ready: bool, ledger_nav: float | None) -> dict:
    required = len(positions) if positions is not None else None
    marked = sum(ticker in prices for ticker in positions) if positions is not None else None
    nav = None
    source = None
    if endpoint_ready and cash is not None and positions is not None:
        if marked == required:
            nav = cash + fsum(qty * prices[ticker]['price'] for ticker, qty in positions.items())
            source = 'matched_raw_marks'
        elif ledger_nav is not None:
            nav, source = ledger_nav, 'verified_ledger_nav'
    return {
        'cash': cash, 'nav': nav, 'nav_source': source,
        'return_pct': 100 * (nav / opening_nav - 1) if nav is not None and opening_nav else None,
        'marked_positions': marked, 'required_positions': required,
    }


def _mark(row: dict, cutoff: datetime) -> dict | None:
    price = _num(row.get('mark_price'), positive=True)
    if (price is None or _instant(row.get('mark_at')) != cutoff
            or row.get('price_quality') != 'session_close'):
        return None
    return {'price': price, 'as_of': cutoff.isoformat(), 'source': 'sim_position.raw_session_close'}


def replay_turnover(
    *, start_date: date, end_date: date, starting_at: datetime, ending_at: datetime,
    observed_at: datetime, cohort_started_at: datetime, initial_cash: float,
    pre_fills: list[dict], fills: list[dict], terminal_prices: dict,
    opening_sample: dict | None = None, ending_sample: dict | None = None,
    opening_prices: dict | None = None, ex_dividends: list[dict] | None = None,
    ledger_complete: bool = True, unassigned_fills: int = 0,
) -> dict:
    """Compute three paper books from recorded fills, chronologically and fee-aware.

    ``terminal_prices`` is keyed by ticker and must already be validated for the
    exact same raw regular-session close. No old last trade carries forward.
    """
    reasons = []
    endpoint_ready = ending_at <= observed_at
    if not endpoint_ready:
        reasons.append('end_session_not_closed')
        terminal_prices = {}
    if unassigned_fills:
        reasons.append('unassigned_fill_date')
    if not ledger_complete:
        reasons.append('ledger_limit_exceeded')
    if cohort_started_at > starting_at:
        reasons.append('window_starts_before_cohort')
    has_ledger = ledger_complete and not unassigned_fills and cohort_started_at <= ending_at
    opening_cash = _nonnegative(initial_cash) if has_ledger else None
    opening_positions = {} if has_ledger else None
    for row in pre_fills:
        if not _timing_ok(row):
            opening_cash, opening_positions = None, None
            break
        opening_cash, opening_positions = _apply(
            opening_cash, opening_positions, row, _qty(row), _nonnegative(row.get('transaction_cost')),
        )
    start_stamp = max(starting_at, cohort_started_at)
    ledger_open_nav = _matching_ledger_nav(opening_sample, opening_cash, starting_at)
    opening_nav = None
    opening_source = None
    if opening_positions is not None and not opening_positions:
        opening_nav, opening_source = opening_cash, 'cash_only'
    elif (opening_positions is not None and opening_cash is not None and opening_prices is not None
          and opening_positions.keys() <= opening_prices.keys()):
        opening_nav = opening_cash + fsum(qty * opening_prices[ticker]['price']
                                         for ticker, qty in opening_positions.items())
        opening_source = 'matched_raw_marks'
    elif opening_positions is not None and ledger_open_nav is not None:
        opening_nav, opening_source = ledger_open_nav, 'verified_ledger_nav'
    if opening_nav is None:
        reasons.append('opening_nav_unavailable')

    actual_cash, reduce_cash = opening_cash, opening_cash
    actual_pos = opening_positions.copy() if opening_positions is not None else None
    reduce_pos = opening_positions.copy() if opening_positions is not None else None
    required_prices = set(opening_positions or {})
    trades = []
    events = iter(sorted(ex_dividends or [], key=lambda item: (item['date'], item['ticker'])))
    next_event = next(events, None)
    dividends: dict[str, float | None] = dict.fromkeys(('actual', 'hold', 'reduce_only'), 0.0)
    dividend_rows = []

    def before_ex_session(day: date) -> None:
        nonlocal next_event
        while next_event and next_event['date'] <= day:
            ticker, rate = next_event['ticker'], next_event['rate']
            item = {'ticker': ticker, 'ex_date': next_event['date'].isoformat(), 'rate': rate}
            for key, book in (('actual', actual_pos), ('hold', opening_positions), ('reduce_only', reduce_pos)):
                amount = book.get(ticker, 0) * rate if book is not None else None
                item[key] = amount
                dividends[key] = _sum((dividends[key], amount))
            dividend_rows.append(item)
            next_event = next(events, None)

    for row in fills:
        before_ex_session(row['fill_date'])
        ticker, qty, direction = row['ticker'], _qty(row), _direction(row)
        required_prices.add(ticker)
        timeline_ok = _timing_ok(row)
        px, fee = _num(row.get('fill_price'), positive=True), _nonnegative(row.get('transaction_cost'))
        slip, ref, slip_source = _slippage(row)
        mark = terminal_prices.get(ticker, {})
        terminal = mark.get('price')
        actual_notional = qty * px if qty is not None and px is not None else None
        gross = (direction * qty * (terminal - ref) if timeline_ok and None not in
                 (direction, qty, terminal, ref) else None)
        trade_net = (direction * qty * (terminal - px) - fee if timeline_ok and None not in
                     (direction, qty, terminal, px, fee) else None)
        if direction == 1:
            eligible = 0
        elif direction == -1 and qty is not None and reduce_pos is not None and timeline_ok:
            eligible = min(qty, reduce_pos.get(ticker, 0))
        else:
            eligible = None
        reduced_fee = _eligible_fee(row, qty, eligible, fee)
        reduced_net = (0.0 if eligible == 0 else
                       eligible * (px - terminal) - reduced_fee if timeline_ok and None not in
                       (eligible, terminal, px, reduced_fee) else None)
        if timeline_ok:
            actual_cash, actual_pos = _apply(actual_cash, actual_pos, row, qty, fee)
            reduce_cash, reduce_pos = _apply(reduce_cash, reduce_pos, row, eligible, reduced_fee)
        else:
            actual_cash, actual_pos = None, None
            if direction != 1:
                reduce_cash, reduce_pos = None, None
        trades.append({
            'order_id': row['id'], 'ticker': ticker, 'side': row['side'], 'qty': qty,
            'filled_at': stamp.isoformat() if (stamp := _instant(row.get('filled_at'))) else None,
            'fill_date': row['fill_date'].isoformat(), 'fill_price': px, 'notional': actual_notional,
            'reference_price': ref, 'slippage_source': slip_source, 'slippage_usd': slip, 'fee': fee,
            'terminal_price': terminal, 'terminal_source': mark.get('source'),
            'gross_vs_hold_usd': gross, 'net_vs_hold_usd': trade_net,
            'reduce_only_qty': eligible, 'reduce_only_fee': reduced_fee,
            'reduce_only_net_vs_hold_usd': reduced_net,
        })
    before_ex_session(ending_at.astimezone(NEW_YORK).date())

    ledger_close_nav = _matching_ledger_nav(ending_sample, actual_cash, ending_at)
    actual = _scenario(actual_cash, actual_pos, terminal_prices, opening_nav, endpoint_ready, ledger_close_nav)
    hold = _scenario(opening_cash, opening_positions, terminal_prices, opening_nav, endpoint_ready, None)
    reduce = _scenario(reduce_cash, reduce_pos, terminal_prices, opening_nav, endpoint_ready, None)
    for item in (actual, hold, reduce):
        item['delta_vs_hold_usd'] = _difference(item['nav'], hold['nav'])
    net_total = _sum(trade['net_vs_hold_usd'] for trade in trades)
    if not endpoint_ready or not has_ledger or actual_pos is None:
        net_total = None
    if required_prices - terminal_prices.keys():
        reasons.append('missing_terminal_marks')
    if actual_pos is None or opening_positions is None:
        reasons.append('positions_not_reconciled')
    if any(not _timing_ok(row) for row in fills):
        reasons.append('fill_timestamp_unavailable')
    if any(trade['fee'] is None for trade in trades):
        reasons.append('missing_fees')
    if any(trade['slippage_usd'] is None for trade in trades):
        reasons.append('missing_slippage_evidence')
    if any(trade['reduce_only_qty'] and trade['reduce_only_fee'] is None for trade in trades):
        reasons.append('missing_reduce_only_fee')
    if net_total is not None and actual['delta_vs_hold_usd'] is not None and not isclose(
        net_total, actual['delta_vs_hold_usd'], rel_tol=1e-9, abs_tol=0.01,
    ):
        reasons.append('terminal_book_mismatch')
        actual['delta_vs_hold_usd'] = None
        net_total = None

    status = ('pending_close' if not endpoint_ready else 'complete'
              if not reasons and all(book['nav'] is not None for book in (actual, hold, reduce))
              else 'partial')
    result = {
        'window': {'start_date': start_date.isoformat(), 'end_date': end_date.isoformat(),
                   'start_as_of': start_stamp.isoformat(), 'end_as_of': ending_at.isoformat(),
                   'observed_at': observed_at.isoformat(), 'status': status},
        'opening': {'cash': opening_cash, 'nav': opening_nav, 'nav_source': opening_source,
                    'position_count': len(opening_positions) if opening_positions is not None else None},
        'scenarios': {'actual': actual, 'hold': hold, 'reduce_only': reduce},
        'coverage': {'filled': len(trades), 'fees': sum(t['fee'] is not None for t in trades),
                     'slippage': sum(t['slippage_usd'] is not None for t in trades),
                     'terminal_marks': len(required_prices & terminal_prices.keys()),
                     'terminal_marks_required': len(required_prices),
                     'trade_attribution': sum(t['net_vs_hold_usd'] is not None for t in trades),
                     'unassigned_fills': unassigned_fills,
                     'ledger_complete': has_ledger},
        'totals': {'notional': _sum(t['notional'] for t in trades) if ledger_complete and not unassigned_fills else None,
                   'fees': _sum(t['fee'] for t in trades) if ledger_complete and not unassigned_fills else None,
                   'slippage_usd': _sum(t['slippage_usd'] for t in trades) if ledger_complete and not unassigned_fills else None,
                   'net_vs_hold_usd': net_total,
                   'actual_vs_reduce_only_usd': _difference(actual['nav'], reduce['nav'])},
        'trades': trades, 'reasons': reasons,
    }
    if opening_prices is not None:
        result['nav_reconciliation'] = {
            'opening_book_nav': ledger_open_nav, 'ending_book_nav': ledger_close_nav,
            'opening_replay_minus_book_usd': _difference(opening_nav, ledger_open_nav),
            'ending_replay_minus_book_usd': _difference(actual['nav'], ledger_close_nav),
        }
    if ex_dividends is not None:
        result['cash_dividend_sensitivity'] = {
            'basis': 'hypothetical_ex_date_entitlement_not_simulated_ledger_cash',
            'events': dividend_rows, 'by_scenario_usd': dividends,
            'net_vs_hold_usd': {key: _sum((book['delta_vs_hold_usd'],
                                          _difference(dividends[key], dividends['hold'])))
                               for key, book in result['scenarios'].items()},
        }
    return result


def _session_bounds(start_date: date, end_date: date) -> tuple[datetime, datetime]:
    if not timedelta(0) <= end_date - start_date < timedelta(days=MAX_WINDOW_DAYS):
        raise ValueError(f'date range must contain 1–{MAX_WINDOW_DAYS} calendar days')
    sessions = xnys_sessions(start_date, end_date)
    if not sessions:
        raise ValueError('date range must contain an XNYS session')
    calendar = _xnys_calendar()
    prior = calendar.previous_session(calendar.date_to_session(sessions[0])).date()
    return xnys_close(prior), xnys_close(sessions[-1])


async def load_turnover_attribution(
    conn: Any, user_id: int, account_id: int, start_date: date, end_date: date,
    *, observed_at: datetime | None = None, archival_quotes: dict | None = None,
) -> dict:
    """Read from an existing read-only, repeatable-read transaction."""
    account = await bot_account(conn, user_id, account_id)
    now = observed_at or datetime.now(UTC)
    opening, ending = _session_bounds(start_date, end_date)
    history = await conn.fetch(
        "SELECT id,ticker,side,qty,fill_date,filled_at,fill_price,transaction_cost,"
        "reference_price,fee_bps,execution_evidence FROM sim_order "
        "WHERE account_id=$1 AND cohort_id=$2 AND status='filled' "
        "AND (fill_date<=$3 OR fill_date IS NULL) ORDER BY fill_date,filled_at,id LIMIT $4",
        account_id, account['reset_count'], ending.astimezone(NEW_YORK).date(), MAX_LEDGER_FILLS + 1,
    )
    pre, fills, unassigned = [], [], 0
    for row in history[:MAX_LEDGER_FILLS]:
        fill = dict(row)
        if (_instant(fill['filled_at']) or now) > now:
            continue
        if fill['fill_date'] is None:
            unassigned += 1
        else:
            (pre if fill['fill_date'] < start_date else fills).append(fill)

    anchors = await conn.fetch(
        'SELECT as_of_date,portfolio_value,cash,valuation_quality,valued_at FROM sim_equity_daily '
        'WHERE account_id=$1 AND cohort_id=$2 AND as_of_date=ANY($3::date[]) AND valued_at<=$4',
        account_id, account['reset_count'],
        [stamp.astimezone(NEW_YORK).date() for stamp in (opening, ending)], now,
    )
    samples = {row['as_of_date']: dict(row) for row in anchors}
    marks = {}
    if ending <= now and archival_quotes is None:
        rows = await conn.fetch(
            'SELECT ticker,mark_price,mark_at,price_quality FROM sim_position '
            'WHERE account_id=$1 AND cohort_id=$2 AND mark_at=$3',
            account_id, account['reset_count'], ending,
        )
        marks = {row['ticker']: quote for row in rows if (quote := _mark(dict(row), ending)) is not None}
    archived_opening, ex_dividends = None, None
    if archival_quotes is not None:
        archived_opening = archival_quotes['opening'].get(opening, {})
        marks = archival_quotes['terminal'].get(ending, {})
        ex_dividends = [item for item in archival_quotes['ex_dividends']
                        if opening.astimezone(NEW_YORK).date() < item['date'] <= ending.astimezone(NEW_YORK).date()]
    return replay_turnover(
        start_date=start_date, end_date=end_date, starting_at=opening, ending_at=ending,
        observed_at=now, cohort_started_at=account['reset_at'] or account['created_at'],
        initial_cash=account['initial_cash'], pre_fills=pre, fills=fills, terminal_prices=marks,
        opening_sample=samples.get(opening.astimezone(NEW_YORK).date()),
        ending_sample=samples.get(ending.astimezone(NEW_YORK).date()),
        opening_prices=archived_opening, ex_dividends=ex_dividends,
        ledger_complete=len(history) <= MAX_LEDGER_FILLS, unassigned_fills=unassigned,
    )


async def read_turnover_attribution(
    pool: Any, user_id: int, account_id: int, start_date: date, end_date: date,
) -> dict:
    async with pool.acquire() as conn:
        async with conn.transaction(readonly=True, isolation='repeatable_read'):
            return await load_turnover_attribution(conn, user_id, account_id, start_date, end_date)
