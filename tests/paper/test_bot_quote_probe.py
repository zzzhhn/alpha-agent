from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

from alpha_agent.api.routes.paper_bot import market_probe
from alpha_agent.paper import intraday


async def test_probe_reports_requested_symbol_and_only_complete_bars(monkeypatch):
    # Pin an open session. With the real calendar this passed during US
    # trading hours and failed outside them: a closed session cuts bars at the
    # previous close (CI failure 2026-11-13 05:49 UTC).
    from alpha_agent.paper import bot_valuation

    monkeypatch.setattr(bot_valuation, 'valuation_session', lambda instant: {
        'session_date': instant.date().isoformat(), 'is_open': True,
        'open_at': (instant - timedelta(hours=1)).isoformat(),
        'close_at': (instant + timedelta(hours=5)).isoformat()})
    now = datetime.now(UTC)
    old_end = (now - timedelta(minutes=10)).isoformat()
    fetch = AsyncMock(return_value=[
        {'end': old_end, 'volume': 100, 'price_basis': 'raw_unadjusted'},
        {'end': (now + timedelta(minutes=1)).isoformat(), 'volume': 20},
    ])
    monkeypatch.setattr(intraday, 'fetch_bars', fetch)
    result = await market_probe(ticker='ERIE')
    assert fetch.call_args.args[0] == 'ERIE'
    assert result['ticker'] == 'ERIE'
    assert result['last_bar'] == old_end
    assert result['last_bar_age_seconds'] >= 600
    assert result['recent_bars'] == [{'end': old_end, 'volume': 100}]


async def test_probe_error_never_exposes_provider_payload(monkeypatch):
    monkeypatch.setattr(intraday, 'fetch_bars', AsyncMock(side_effect=ValueError('private-response')))
    result = await market_probe(ticker='ERIE')
    assert result['ticker'] == 'ERIE'
    assert result['available'] is False
    assert result['reason'] == 'ValueError'
    assert 'private-response' not in str(result)
