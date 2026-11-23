from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alpha_agent.paper.turnover_attribution import (
    _mark,
    _session_bounds,
    load_turnover_attribution,
    replay_turnover,
)


def _fill(order_id, day, side, qty, price, reference, ticker='TEST'):
    at = datetime(2026, 11, day, 15, 31, tzinfo=UTC)
    return {
        'id': order_id, 'ticker': ticker, 'side': side, 'qty': qty,
        'fill_date': at.date(), 'filled_at': at, 'fill_price': price,
        'reference_price': reference, 'transaction_cost': price * qty / 1_000, 'fee_bps': 10,
        'execution_evidence': {
            'reference_price': reference, 'fill_price': price,
            'confirmed_at': (at + timedelta(minutes=2)).isoformat(),
            'bar': {
                'source': 'fixture:raw', 'price_basis': 'raw_unadjusted', 'open': reference,
                'start': at.isoformat(), 'end': (at + timedelta(minutes=1)).isoformat(),
                'fetched_at': (at + timedelta(minutes=2)).isoformat(), 'corporate_actions_known': True,
            },
        },
    }


def _args():
    start, end = date(2026, 11, 10), date(2026, 11, 20)
    opening, ending = _session_bounds(start, end)
    return {
        'start_date': start, 'end_date': end, 'starting_at': opening, 'ending_at': ending,
        'observed_at': ending + timedelta(hours=1),
        'cohort_started_at': datetime(2026, 11, 2, tzinfo=UTC), 'initial_cash': 10_000,
        'pre_fills': [_fill(1, 9, 'buy', 10, 100, 100)],
        'fills': [_fill(2, 10, 'buy', 5, 110.11, 110), _fill(3, 12, 'sell', 12, 119.88, 120)],
        'opening_prices': {'TEST': {'price': 100}},
        'terminal_prices': {'TEST': {'price': 130, 'source': 'fixture:raw_terminal'}},
    }


def test_common_initial_book_and_trade_bridge_charge_each_cost_once():
    report = replay_turnover(**_args())
    actual, hold, reduced = (report['scenarios'][key] for key in ('actual', 'hold', 'reduce_only'))
    assert report['window']['status'] == 'complete'
    assert report['opening']['cash'] == 8999
    assert report['opening']['nav'] == 9999
    assert hold['nav'] == 10299
    assert reduced['nav'] == pytest.approx(8999 + 10 * 119.88 * 0.999)
    assert report['trades'][1]['reduce_only_qty'] == 10  # no sale of the bought lot
    assert report['trades'][1]['reduce_only_fee'] == pytest.approx(10 * 119.88 / 1000)
    assert report['totals']['slippage_usd'] == pytest.approx(5 * 0.11 + 12 * 0.12)
    for row in report['trades']:
        assert row['net_vs_hold_usd'] == pytest.approx(row['gross_vs_hold_usd'] - row['slippage_usd'] - row['fee'])
    assert report['totals']['net_vs_hold_usd'] == pytest.approx(actual['nav'] - hold['nav'])
    assert report['totals']['actual_vs_reduce_only_usd'] == pytest.approx(actual['nav'] - reduced['nav'])


def test_missing_price_fee_and_unproven_slippage_are_independent_unknowns():
    args = _args()
    args['terminal_prices'] = {}
    args['fills'][0]['execution_evidence']['bar']['open'] += 1
    args['fills'][1]['transaction_cost'] = None
    report = replay_turnover(**args)
    assert report['window']['status'] == 'partial'
    assert report['coverage']['filled'] == 2
    assert report['coverage']['fees'] == 1
    assert report['coverage']['slippage'] == 1
    assert report['coverage']['trade_attribution'] == 0
    assert report['coverage']['terminal_marks'] == 0
    assert report['totals']['fees'] is None
    assert report['totals']['slippage_usd'] is None
    assert report['totals']['net_vs_hold_usd'] is None
    assert report['scenarios']['actual']['cash'] is None
    assert report['scenarios']['hold']['nav'] is None
    assert {'missing_terminal_marks', 'missing_fees', 'missing_slippage_evidence'} <= set(report['reasons'])


def test_pending_session_never_promotes_provided_quotes_or_fake_cash_only_nav():
    args = _args()
    args['observed_at'] = args['ending_at'] - timedelta(seconds=1)
    result = replay_turnover(**args)
    assert result['window']['status'] == 'pending_close'
    assert result['coverage']['filled'] == result['coverage']['fees'] == 2
    assert result['coverage']['trade_attribution'] == 0
    assert result['totals']['net_vs_hold_usd'] is None
    assert all(book['nav'] is None for book in result['scenarios'].values())


def test_dividend_sensitivity_uses_pre_ex_session_holdings_and_does_not_change_cash():
    args = _args()
    event = {'ticker': 'TEST', 'date': date(2026, 11, 12), 'rate': 0.5}  # sale occurs on ex-date
    before, report = replay_turnover(**args), replay_turnover(**args, ex_dividends=[event])
    assert report['scenarios'] == before['scenarios']
    sensitivity = report['cash_dividend_sensitivity']
    assert sensitivity['by_scenario_usd'] == {'actual': 7.5, 'hold': 5, 'reduce_only': 5}
    assert sensitivity['net_vs_hold_usd']['actual'] == pytest.approx(before['totals']['net_vs_hold_usd'] + 2.5)


def test_xnys_weekend_previous_close_and_shortened_session():
    opening, closing = _session_bounds(date(2026, 11, 21), date(2026, 11, 27))
    assert opening == datetime(2026, 11, 20, 21, tzinfo=UTC)
    assert closing == datetime(2026, 11, 27, 18, tzinfo=UTC)
    assert _mark({'mark_price': 100, 'mark_at': closing, 'price_quality': 'fresh'}, closing) is None
    assert _mark({'mark_price': 100, 'mark_at': opening, 'price_quality': 'session_close'}, closing) is None
    with pytest.raises(ValueError, match='contain an XNYS session'):
        _session_bounds(date(2026, 11, 21), date(2026, 11, 22))


async def test_unowned_account_fails_before_loading_any_trades():
    conn = type('Connection', (), {'fetchrow': AsyncMock(return_value=None), 'fetch': AsyncMock()})()
    from fastapi import HTTPException

    with pytest.raises(HTTPException, match='account not found'):
        await load_turnover_attribution(conn, 9, 2, date(2026, 11, 10), date(2026, 11, 20))
    assert conn.fetchrow.call_args.args[1:] == (2, 9)
    conn.fetch.assert_not_called()


def test_route_requires_auth_and_serves_only_private_results(monkeypatch):
    from alpha_agent.api.routes import paper_bot
    from alpha_agent.auth.dependencies import require_user
    from alpha_agent.paper import turnover_attribution

    conn = object()
    loader = AsyncMock(return_value={'window': {'status': 'partial'}})
    monkeypatch.setattr(paper_bot, 'get_db_pool', AsyncMock(return_value=conn))
    monkeypatch.setattr(turnover_attribution, 'read_turnover_attribution', loader)
    app = FastAPI()
    app.include_router(paper_bot.router)
    path = '/api/paper/accounts/7/bot/turnover-attribution?start_date=2026-11-10&end_date=2026-11-20'
    client = TestClient(app)
    assert client.get(path).status_code == 401
    loader.assert_not_called()
    app.dependency_overrides[require_user] = lambda: 42
    response = client.get(path)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'private, no-store'
    loader.assert_awaited_once_with(conn, 42, 7, date(2026, 11, 10), date(2026, 11, 20))
