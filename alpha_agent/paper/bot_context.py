"""Small, timestamped research packets; no training or full-universe ingestion."""
from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime, timedelta

from alpha_agent.data.security_identity import valid_research_symbol
from alpha_agent.paper.bot_store import unpack
from alpha_agent.paper.intraday import fetch_bars
from alpha_agent.paper.market_clock import as_utc, market_session
from alpha_agent.storage.product_ledger import get_latest_canonical_run


async def quotes_for(tickers, now=None):
    now = now or datetime.now(UTC)
    market = market_session(now)
    semaphore = asyncio.Semaphore(2)

    async def one(ticker):
        result = {'price': None, 'as_of': None, 'source': 'yfinance:history:1m',
                  'quality': 'unavailable', 'price_basis': 'raw_unadjusted'}
        if not market['is_open']:
            return ticker, {**result, 'reason': 'market_closed'}
        if not valid_research_symbol(ticker, now.date()):
            return ticker, {**result, 'reason': 'instrument_identity_unresolved'}
        try:
            async with semaphore:
                bars = await asyncio.wait_for(fetch_bars(ticker, now), timeout=12)
            completed = [b for b in bars if as_utc(b['end']) <= now]
            if completed:
                bar = completed[-1]
                price = bar['close']
                if bar.get('corporate_actions') or not bar.get('corporate_actions_known'):
                    return ticker, {**result, 'reason': 'corporate_action_requires_reconciliation'}
                if price and math.isfinite(price) and price > 0:
                    result.update(price=price, as_of=bar['end'], source=bar['source'],
                                  quality='fresh' if now-as_utc(bar['end']) <= timedelta(minutes=5) else 'stale')
        except Exception as exc:
            # Provider messages can contain request details. Persist only class.
            result['reason'] = type(exc).__name__
        return ticker, result

    symbols = list(dict.fromkeys(tickers))
    if len(symbols) > 40:
        raise ValueError('本轮行情标的超过 40 个查询上限')
    return dict(await asyncio.gather(*(one(t) for t in symbols)))


async def build_context(pool, run, research_tickers=None):
    from alpha_agent.api.routes.paper import _read_account

    account = await pool.fetchrow('SELECT * FROM sim_account WHERE id=$1', run['account_id'])
    book = await _read_account(pool, account['user_id'], account['id'])
    book = book.model_dump()
    source = await get_latest_canonical_run(pool)
    held = [p['ticker'] for p in book['positions']]
    requested = list(dict.fromkeys(held + (research_tickers or [])))[:25]
    rows = []
    if source:
        rows = await pool.fetch(
            'SELECT id,ticker,tier,rank,composite_z,coverage,user_visible_payload_json '
            'FROM rating_snapshot WHERE run_id=$1 AND eligible=true AND in_universe=true '
            'AND (rank<=20 OR ticker=ANY($2::text[])) ORDER BY rank NULLS LAST,ticker LIMIT 45',
            source['id'], requested)
    rows = [r for r in rows if valid_research_symbol(r['ticker'])]
    symbols = list(dict.fromkeys([r['ticker'] for r in rows] + held))[:40]
    if symbols:
        await pool.execute('INSERT INTO sim_instrument(ticker) SELECT unnest($1::text[]) ON CONFLICT(ticker) DO NOTHING', symbols)
    instruments = await pool.fetch('SELECT id AS instrument_id,ticker,identity_status FROM sim_instrument WHERE ticker=ANY($1::text[]) ORDER BY id', symbols)
    instruments = [{**dict(i), 'instrument_id': str(i['instrument_id'])} for i in instruments]
    notes = await pool.fetch('SELECT ticker,note,updated_at FROM sim_bot_position_note WHERE account_id=$1 ORDER BY updated_at DESC LIMIT 20', account['id'])
    orders = await pool.fetch("SELECT id,ticker,side,qty,status,accepted_at,expires_at FROM sim_order WHERE account_id=$1 AND status='pending' ORDER BY id LIMIT 40", account['id'])
    recommendations = []
    for row in rows:
        payload = unpack(row['user_visible_payload_json'])
        recommendations.append({k: row[k] for k in ('ticker', 'tier', 'rank', 'composite_z', 'coverage')} | {
            'evidence_id': f"rating:{row['id']}",
            'drivers': str(payload.get('drivers', []))[:400],
            'drags': str(payload.get('drags', []))[:400]})
    quote_symbols = held + [t for t in requested if t in symbols] + [r['ticker'] for r in rows[:8]]
    quotes = await quotes_for(quote_symbols)
    missing_research = [t for t in (research_tickers or []) if t not in symbols]
    return {
        'context_id': str(run['id']), 'created_at': datetime.now(UTC).isoformat(),
        'config_version': run['config_version'], 'market': market_session(),
        'account': book, 'instruments': instruments, 'open_orders': [dict(o) for o in orders],
        'position_memory': [dict(n) for n in notes], 'recommendations': recommendations,
        'evidence_ids': [r['evidence_id'] for r in recommendations], 'quotes': quotes,
        'research_run_id': source['id'] if source else None,
        'research_as_of': str(source['data_asof']) if source else None,
        'research_unavailable': missing_research,
        'warnings': ([] if source else ['no_complete_research_snapshot']) +
                    ['recommendations_are_not_return_guarantees', 'unquoted_symbols_require_research_before_trading'],
    }


async def execution_context(pool, run, context, decision):
    """Refresh execution prices and balances without rewriting the model's input."""
    from alpha_agent.api.routes.paper import _read_account
    account = await pool.fetchrow('SELECT user_id FROM sim_account WHERE id=$1', run['account_id'])
    book = (await _read_account(pool, account['user_id'], run['account_id'])).model_dump()
    ids = {a.instrument_id for a in decision.actions if a.instrument_id}
    tickers = [p['ticker'] for p in book['positions']] + [i['ticker'] for i in context['instruments'] if i['instrument_id'] in ids]
    quotes = await quotes_for(tickers)
    held = book['positions']
    if any(quotes.get(p['ticker'], {}).get('quality') != 'fresh' for p in held):
        raise ValueError('持仓缺少新鲜原始行情，不能可靠计算目标权重')
    book['portfolio_value'] = book['cash'] + sum(quotes[p['ticker']]['price'] * p['qty'] for p in held)
    return {**context, 'account': book, 'quotes': quotes}
