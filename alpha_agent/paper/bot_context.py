"""Small, timestamped research packets; no training or full-universe ingestion."""
from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime, timedelta

from alpha_agent.data.security_identity import valid_research_symbol
from alpha_agent.paper.bot_store import unpack
from alpha_agent.paper.bot_models import BotConfig
from alpha_agent.paper.bot_policy import research_age
from alpha_agent.paper.intraday import fetch_bars
from alpha_agent.paper.market_clock import as_utc, market_session
from alpha_agent.storage.product_ledger import get_latest_canonical_run


def recommendation_evidence(payload):
    """Read the published pick schema; attribution names are not detailed research."""
    def signals(name, legacy):
        value = payload.get(name, payload.get(legacy, []))
        return [item[:80] for item in value[:5] if isinstance(item, str)] if isinstance(value, list) else []

    horizon = payload.get('horizon_days')
    return {
        'drivers': signals('top_drivers', 'drivers'),
        'drags': signals('top_drags', 'drags'),
        'recommendation_policy_id': str(payload['policy_id'])[:80] if payload.get('policy_id') else None,
        'recommendation_horizon_days': horizon if type(horizon) is int and 0 < horizon <= 252 else None,
        'attribution_basis': 'signal_names_not_full_research',
    }


async def quotes_for(tickers, now=None):
    now = now or datetime.now(UTC)
    market = market_session(now)
    semaphore = asyncio.Semaphore(2)

    async def one(ticker):
        result = {'price': None, 'as_of': None, 'source': 'yfinance:history:1m',
                  'quality': 'unavailable', 'price_basis': 'raw_unadjusted', 'reason': 'no_complete_bar'}
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
                                  quality='fresh' if now-as_utc(bar['end']) <= timedelta(minutes=5) else 'stale',
                                  reason=None if now-as_utc(bar['end']) <= timedelta(minutes=5) else 'stale_quote')
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
    config = BotConfig.model_validate(unpack(run['config_snapshot']))
    age = research_age(source)
    research_usable = age is not None and age <= config.max_research_age_sessions
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
    notes = await pool.fetch('SELECT ticker,note,metadata,updated_at FROM sim_bot_position_note WHERE account_id=$1 ORDER BY updated_at DESC LIMIT 20', account['id'])
    orders = await pool.fetch("SELECT id,ticker,side,qty,status,accepted_at,expires_at FROM sim_order WHERE account_id=$1 AND status='pending' ORDER BY id LIMIT 40", account['id'])
    history = await pool.fetch(
        "SELECT id,created_at,status,summary,result FROM sim_bot_run WHERE account_id=$1 AND id<>$2 "
        "AND status NOT IN ('queued','running') ORDER BY created_at DESC LIMIT 3", account['id'], run['id'])
    prior = []
    if source and rows:
        prior = await pool.fetch(
            'SELECT ticker,tier,rank FROM rating_snapshot WHERE run_id=(SELECT id FROM research_run '
            "WHERE run_type='daily_close' AND status='complete' AND id<$1 ORDER BY finished_at DESC NULLS LAST,id DESC LIMIT 1) "
            'AND ticker=ANY($2::text[]) LIMIT 45', source['id'], [r['ticker'] for r in rows])
    previous = {r['ticker']: r for r in prior}
    recommendations = []
    for row in rows:
        payload = unpack(row['user_visible_payload_json'])
        recommendations.append({k: row[k] for k in ('ticker', 'tier', 'rank', 'composite_z', 'coverage')} | {
            'evidence_id': f"rating:{row['id']}",
            'as_of': str(source['data_asof']) if source and source['data_asof'] else None,
            'market_date': str(source['scheduled_for_date']) if source else None,
            'age_sessions': age, 'usable_for_new_buy': research_usable,
            'previous_tier': previous[row['ticker']]['tier'] if row['ticker'] in previous else None,
            'previous_rank': previous[row['ticker']]['rank'] if row['ticker'] in previous else None,
            **recommendation_evidence(payload)})
    quote_symbols = held + [t for t in requested if t in symbols] + [r['ticker'] for r in rows[:8]]
    quotes = await quotes_for(quote_symbols)
    evidence = {r['evidence_id']: {'ticker': r['ticker'], 'kind': 'research', 'usable_for_new_buy': research_usable}
                for r in recommendations}
    evidence.update({f"position:{p['ticker']}": {'ticker': p['ticker'], 'kind': 'position', 'usable_for_new_buy': False} for p in book['positions']})
    evidence.update({f"order:{o['id']}": {'ticker': o['ticker'], 'kind': 'order', 'usable_for_new_buy': False} for o in orders})
    missing_research = [t for t in (research_tickers or []) if t not in symbols]
    return {
        'schema_version': 2, 'context_id': str(run['id']), 'created_at': datetime.now(UTC).isoformat(),
        'config_version': run['config_version'], 'market': market_session(),
        'account': book, 'instruments': instruments, 'open_orders': [dict(o) for o in orders],
        'position_memory': [dict(n) for n in notes], 'recommendations': recommendations,
        'recent_decisions': [{'run_id': str(h['id']), 'created_at': h['created_at'], 'status': h['status'],
                              'summary': h['summary'][:400], 'outcome_reason': unpack(h['result']).get('outcome_reason')} for h in history],
        'evidence_ids': list(evidence), 'evidence_map': evidence, 'quotes': quotes,
        'quote_coverage': {'requested': len(quotes), 'fresh': sum(q['quality'] == 'fresh' for q in quotes.values()),
                           'unavailable': sum(q['quality'] != 'fresh' for q in quotes.values())},
        'research_run_id': source['id'] if source else None,
        'research_as_of': str(source['data_asof']) if source else None,
        'research_age_sessions': age, 'research_usable_for_new_buy': research_usable,
        'research_unavailable': missing_research,
        'warnings': ([] if source else ['no_complete_research_snapshot']) +
                    ([] if research_usable else ['research_unavailable_or_stale_no_new_buys']) +
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
