"""Forward-only, isolated equity event experiment. No real or legacy orders."""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable

from alpha_agent.data.security_identity import valid_research_symbol
from alpha_agent.market_session import xnys_sessions
from alpha_agent.paper import event_shadow_policy as p
from alpha_agent.paper.event_shadow_inputs import MAX_TICKERS, read_regular_bars
from alpha_agent.paper.market_clock import NEW_YORK, as_utc, market_session

_ACTIVE = "status IN ('pending','open') AND policy=$1"
_NOT_OPEN = 'regular_session_closed'
_SOURCE_MAX_LATENESS = timedelta(hours=36)


def _json(data: Any) -> str:
    return json.dumps(data, default=str, separators=(',', ':'), allow_nan=False)


def _decode(row: dict, col: str) -> dict:
    raw = row.get(col)
    return json.loads(raw) if isinstance(raw, str) else raw or {}


def _bounded(limit: int) -> int:
    return min(30, max(1, limit))


def _clock(now=None) -> datetime:
    return as_utc(now) if now is not None else datetime.now(UTC)


async def _isolate(conn, instant: datetime) -> datetime:
    await conn.execute('INSERT INTO event_shadow_runtime(singleton,activated_at) VALUES(true,$1) '
                       'ON CONFLICT(singleton) DO NOTHING', instant)
    return await conn.fetchval('SELECT activated_at FROM event_shadow_runtime WHERE singleton')


async def _books(conn) -> None:
    for sleeve in p.SLEEVES:
        await conn.execute('INSERT INTO event_shadow_book (sleeve,initial_cash,free_cash) VALUES($1,$2,$2) '
                           'ON CONFLICT(sleeve) DO NOTHING', sleeve, p.INITIAL_CASH)


def _event_evidence(row: dict, instant: datetime) -> tuple[dict, datetime, str | None, str] | None:
    ticker = row.get('ticker')
    if (type(row.get('id')) is not int or row['id'] <= 0 or not p.equity_ticker(ticker)
            or not valid_research_symbol(ticker, instant.astimezone(NEW_YORK).date())
            or row.get('source') not in {'sec_edgar', 'investor_relations'}
            or row.get('status') != 'observed' or not row.get('source_key')
            or not str(row.get('url') or '').startswith('https://')):
        return None
    try:
        first_seen = as_utc(row['first_seen_at'])
        published = as_utc(row['published_at']) if row.get('published_at') is not None else None
    except (KeyError, ValueError, AttributeError, TypeError):
        return None
    if max(first_seen, published or first_seen) > instant:
        return None
    direction, rule = p.direction_for(row)
    if direction is not None and (published is None or row.get('published_at_quality') != 'source_timestamp'):
        direction, rule = None, 'unverified_issuer_release_time'
    if direction is not None and published is not None and (
        first_seen - published > _SOURCE_MAX_LATENESS or instant - published > _SOURCE_MAX_LATENESS
    ):
        direction, rule = None, 'old_release_discovered_after_policy_window'
    evidence = {key: row.get(key) for key in ('id', 'ticker', 'source', 'source_key', 'title',
                                                 'url', 'status', 'kind', 'published_at_quality')}
    evidence.update(first_seen_at=first_seen, published_at=published)
    # Use registration time, not a printed date or first_seen, to start orders.
    return evidence, max(first_seen, published or first_seen), direction, rule


def _event_key(evidence: dict) -> str:
    headline = ' '.join(re.findall(r'\w+', str(evidence['title']).casefold()))
    if len(headline) < 12:
        headline = str(evidence['source_key'])
    day = as_utc(evidence['published_at'] or evidence['first_seen_at']).astimezone(NEW_YORK).date()
    value = f"{evidence['ticker']}|{day}|{headline}"
    return hashlib.sha256(value.encode()).hexdigest()


async def _register(conn, candidates: Iterable[dict], instant: datetime, activated: datetime) -> int:
    registered = 0
    # Where equivalent records are known together, prefer the issuer's release
    # over a duplicate filing. Once registered, receipts are never rewritten.
    for row in sorted(candidates, key=lambda x: x.get('source') != 'investor_relations'):
        item = _event_evidence(row, instant)
        if item is None:
            continue
        evidence, visible, direction, rule = item
        if as_utc(evidence['first_seen_at']) < activated:
            continue
        event_key = _event_key(evidence)
        await conn.execute('INSERT INTO event_shadow_observation VALUES($1,$2,$3) ON CONFLICT DO NOTHING',
                           evidence['id'], event_key, instant)
        # Source equivalence remains visible for independent sample counts.
        duplicate = await conn.fetchval(
            'SELECT EXISTS(SELECT 1 FROM event_shadow_trial WHERE policy=$1 AND event_key=$2)',
            p.POLICY, event_key,
        )
        if duplicate:
            continue
        start, until = p.entry_window(max(instant, visible))
        for sleeve in p.SLEEVES:
            active = direction if sleeve == 'long_short' or sleeve == 'long_only' and direction == 'long' else None
            status = 'pending' if active else 'abstained'
            reason = ('no_trade_control' if sleeve == 'no_trade' else
                      'long_only_no_short' if direction == 'short' and sleeve == 'long_only' else rule)
            result = await conn.execute(
                'INSERT INTO event_shadow_trial (policy,event_id,event_key,sleeve,ticker,direction,rule,event_evidence,'
                'decision_at,entry_after,entry_until,status,reason,updated_at,realized_pnl) '
                "VALUES($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10,$11,$12,$13,$9,CASE WHEN $12='abstained' THEN 0 END) "
                'ON CONFLICT DO NOTHING',
                p.POLICY, evidence['id'], event_key, sleeve, evidence['ticker'], active, rule, _json(evidence),
                instant, start, until, status, reason,
            )
            registered += result.endswith(' 1')
    return registered


async def register_event_trials(pool, candidates, *, now=None) -> int:
    """Inject verified official inputs only; not a retail order API."""
    instant = _clock(now)
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute("SELECT pg_advisory_xact_lock(hashtext('event_shadow_tick_v1'))")
        activated = await _isolate(conn, instant)
        await _books(conn)
        return await _register(conn, list(candidates)[:30], instant, activated)


def _receipt(bar: dict) -> dict:
    return {key: bar.get(key) for key in (
        'ticker', 'start', 'end', 'fetched_at', 'source', 'close', 'volume', 'price_quality', 'price_basis',
    )}


def _sync_market(bar: dict, market: list[dict]) -> dict | None:
    item = next((item for item in market if item['start'] == bar['start'] and item['end'] == bar['end']), None)
    return _receipt(item) if item is not None else None


def _action_rows(bar: dict, supplied: Iterable[dict]) -> dict[str, dict]:
    """Current Yahoo action columns plus optional complete official session records."""
    day = bar['start'].astimezone(NEW_YORK).date().isoformat()
    known = {}
    if bar.get('corporate_actions_known') is True:
        actions = bar.get('corporate_actions') or []
        dividends = [p.number(item.get('dividends', 0)) for item in actions]
        splits = [p.number(item.get('stock_splits', 0)) for item in actions]
        if all(x is not None and x >= 0 for x in dividends + splits):
            known[day] = {'dividend_per_share': str(sum(dividends)), 'split': any(x > 0 for x in splits),
                          'source': bar['source'], 'observed_at': bar['fetched_at']}
    for item in supplied:
        try:
            observed = as_utc(item['observed_at'])
            session_day = date.fromisoformat(str(item['session_date'])).isoformat()
            dividend, split = p.number(item.get('dividend_per_share')), item['split']
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if (item.get('ticker') == bar['ticker'] and item.get('complete') is True and item.get('evidence_id')
                and item.get('source') and session_day <= day and observed <= bar['fetched_at']
                and dividend is not None and dividend >= 0 and type(split) is bool):
            known[session_day] = {'dividend_per_share': str(dividend), 'split': split,
                                  'source': item['source'], 'evidence_id': item['evidence_id'],
                                  'observed_at': observed}
    return known


def _carry(trial: dict, receipts: dict, bar: dict) -> tuple[Decimal, Decimal] | str:
    first_day, end_day = trial['entry_at'].astimezone(NEW_YORK).date(), bar['end'].astimezone(NEW_YORK).date()
    actions = receipts.get('actions', {})
    # Include entry day only for split eligibility, never collect its dividend.
    days = xnys_sessions(first_day, end_day)
    if len(days) > 30:
        return 'awaiting_manual_corporate_action_reconciliation'
    dividend = Decimal(0)
    for day in days:
        item = actions.get(day.isoformat())
        if item is None:
            return 'awaiting_corporate_action_evidence'
        if item.get('split'):
            return 'split_requires_reconciliation'
        if day > first_day:
            dividend += Decimal(item['dividend_per_share']) * trial['qty']
    if trial['direction'] != 'short':
        return Decimal(0), p.money(dividend)
    terms = receipts.get('borrow_terms') or {}
    try:
        valid_to = as_utc(terms['valid_until'])
        annual_rate = Decimal(terms['annual_rate'])
    except (KeyError, ValueError, TypeError):
        return 'awaiting_borrow_carry_evidence'
    if valid_to < bar['end']:
        return 'awaiting_borrow_carry_evidence'
    elapsed = Decimal(str((bar['end'] - trial['entry_at']).total_seconds()))
    # Fixed documented model: elapsed Actual/360 against original short notional.
    cost = annual_rate * trial['entry_price'] * trial['qty'] * elapsed / Decimal(360 * 86400)
    return p.money(cost), -p.money(dividend)


def _exposure(book, opened, sources, actions, fill_bar, instant) -> tuple[Decimal, Decimal, Decimal] | None:
    """PIT NAV, gross and short notional; never substitute entry cost for an absent mark."""
    nav = book['free_cash'] + book['restricted_cash']
    gross, short = Decimal(0), Decimal(0)
    for position in opened:
        usable = [bar for bar in sources.get(position['ticker'], [])
                  if position['entry_at'] <= bar['end'] <= fill_bar['end']
                  and bar['fetched_at'] <= instant
                  and fill_bar['end'] - bar['end'] <= p.MAX_QUOTE_AGE]
        if not usable:
            return None
        mark = usable[-1]
        receipts = _decode(position, 'receipts')
        receipts.setdefault('actions', {}).update(_action_rows(mark, actions))
        carry = _carry(position, receipts, mark)
        if isinstance(carry, str):
            return None
        notional = mark['close'] * position['qty']
        is_short = position['direction'] == 'short'
        gross += notional
        short += notional if is_short else 0
        nav += (-notional if is_short else notional) - carry[0] + carry[1]
    return nav, gross, short


async def _pending(conn, trial, book, opened, bars, market, borrow, actions, instant, sources) -> str:
    if instant >= trial['entry_until']:
        await conn.execute("UPDATE event_shadow_trial SET status='expired',updated_at=$2,"
                           "reason='entry_window_expired:' || reason WHERE id=$1",
                           trial['id'], instant)
        return 'expired'
    latest = await conn.fetchrow(
        'SELECT latest.id,latest.status FROM official_event_watch original '
        'JOIN official_event_watch latest ON latest.ticker=original.ticker AND latest.source=original.source '
        'AND latest.source_key=original.source_key WHERE original.id=$1 AND latest.first_seen_at<=$2 '
        'ORDER BY latest.first_seen_at DESC,latest.id DESC LIMIT 1', trial['event_id'], instant,
    )
    if latest is None or latest['id'] != trial['event_id'] or latest['status'] != 'observed':
        await conn.execute("UPDATE event_shadow_trial SET status='expired',reason='official_event_not_current',"
                           'updated_at=$2 WHERE id=$1', trial['id'], instant)
        return 'expired'
    candidates = [bar for bar in bars if bar['start'] > trial['entry_after'] and bar['end'] < trial['entry_until']]
    first = candidates[0] if candidates else None
    reason, loan = 'awaiting_fresh_regular_bar', None
    if first is not None:
        day = first['start'].astimezone(NEW_YORK).date().isoformat()
        action_receipts = _action_rows(first, actions)
        corporate = action_receipts.get(day) or {}
        if not corporate:
            reason = 'awaiting_corporate_action_evidence'
        elif corporate.get('split'):
            reason = 'split_requires_reconciliation'
        elif len(opened) >= p.MAX_POSITIONS or any(x['ticker'] == trial['ticker'] for x in opened):
            reason = 'open_position_limit'
        elif trial['direction'] == 'short' and (
            loan := p.entry_loan(borrow, trial['ticker'], first['end'], instant)
        ) is None:
            reason = 'awaiting_borrow_evidence'
        elif loan is not None and loan['valid_until'] < first['end'] + p.HOLD + timedelta(minutes=6):
            reason = 'borrow_evidence_does_not_cover_planned_hold'
        else:
            exposures = _exposure(book, opened, sources, actions, first, instant)
            nav, gross, short = exposures or (Decimal(0), Decimal(0), Decimal(0))
            # Keep the cap valid after immediate mark-to-raw, slippage, fee and
            # cent rounding, not only immediately before accepting the trade.
            nav_after_cost_reserve = nav - p.MAX_TRADE * (p.FEE_RATE + p.SLIPPAGE) - Decimal('0.02')
            capacity = p.risk_capacity(trial['direction'], nav_after_cost_reserve, gross, short)
            fill = p.open_trade(trial['direction'], first, book['free_cash'], capacity, loan)
            if fill is not None:
                receipts = {'entry': _receipt(first), 'entry_market': _sync_market(first, market),
                            'mark': _receipt(first), 'actions': action_receipts, 'borrow_terms': loan,
                            'risk': {'nav': nav, 'gross': gross, 'short': short, 'capacity': capacity,
                                     'nav_after_cost_reserve': nav_after_cost_reserve}}
                await conn.execute(
                    "UPDATE event_shadow_trial SET status='open',reason='indicative_entry',qty=$2,held_cash=$3,"
                    'entry_price=$4,entry_at=$5,exit_after=$6,fees=$7,receipts=$8::jsonb,updated_at=$9 WHERE id=$1',
                    trial['id'], fill['qty'], fill['held'], fill['price'], first['end'], first['end'] + p.HOLD,
                    fill['fee'], _json(receipts), instant,
                )
                await _cash(conn, book, fill['free_delta'], fill['held'])
                opened.append(dict(trial, qty=fill['qty'], entry_price=fill['price'], entry_at=first['end'],
                                   receipts=receipts))
                return 'opened'
            reason = ('awaiting_complete_portfolio_marks' if exposures is None else
                      'exposure_limit' if capacity <= 0 else 'cash_margin_or_volume_limit')
    if trial['reason'] != reason:
        await conn.execute('UPDATE event_shadow_trial SET reason=$2,updated_at=$3 WHERE id=$1',
                           trial['id'], reason, instant)
    return 'pending'


async def _cash(conn, book, free_delta, held_delta):
    book['free_cash'] += free_delta
    book['restricted_cash'] += held_delta
    await conn.execute('UPDATE event_shadow_book SET free_cash=$2,restricted_cash=$3 WHERE sleeve=$1',
                       book['sleeve'], book['free_cash'], book['restricted_cash'])


async def _open(conn, trial, book, bars, market, borrow, actions, instant) -> str:
    receipts = _decode(trial, 'receipts')
    if not bars:
        return 'open'
    mark = bars[-1]
    last_mark = receipts.get('mark')
    chosen_exit, exit_after = receipts.get('exit_trigger'), trial['exit_after']
    if last_mark is None or mark['end'] > as_utc(last_mark['end']):
        receipts['mark'] = _receipt(mark)
    receipts.setdefault('actions', {}).update(_action_rows(mark, actions))
    if trial['direction'] == 'short':
        updates = [row for row in p.loan_updates(borrow, trial['ticker'], instant)
                   if row['observed_at'] > trial['entry_at']]
        recalled = next((row for row in updates if row.get('recalled') is True), None)
        if recalled is not None and not chosen_exit and recalled['observed_at'] < exit_after:
            chosen_exit = {'reason': 'borrow_recall', 'known_at': recalled['observed_at'],
                           'evidence_id': recalled['evidence_id'], 'source': recalled['source']}
            exit_after = min(exit_after, recalled['observed_at'])
        if p.required_cover(trial, mark['close']) and not chosen_exit and mark['fetched_at'] < exit_after:
            chosen_exit = {'reason': 'maintenance_margin', 'known_at': mark['fetched_at'], 'mark': _receipt(mark)}
            exit_after = min(exit_after, mark['fetched_at'])
        if chosen_exit:
            receipts['exit_trigger'] = chosen_exit
        # Permit a continuous extension at the contracted rate, never guess a
        # missing rate or overwrite an earlier entered economic assumption.
        terms = receipts.get('borrow_terms') or {}
        for update in updates:
            if (not terms or update.get('loan_id') is None or update.get('loan_id') != terms.get('loan_id')
                    or update['source'] != terms['source'] or p.number(update.get('annual_rate')) != p.number(terms['annual_rate'])
                    or update['observed_at'] > as_utc(terms['valid_until'])
                    or update['valid_until'] <= as_utc(terms['valid_until'])):
                continue
            receipts['borrow_extension'] = update
            terms = dict(terms, valid_until=update['valid_until'])
            receipts['borrow_terms'] = terms
    first = next((bar for bar in bars if bar['start'] > exit_after), None)
    reason = 'held_until_planned_exit' if not chosen_exit else 'awaiting_regular_cover_' + chosen_exit['reason']
    if first is not None:
        carry = _carry(trial, receipts, first)
        if isinstance(carry, str):
            reason = carry
        else:
            borrow_cost, dividend_cash = carry
            fill = p.close_trade(trial, first, borrow_cost, dividend_cash)
            if fill is not None:
                receipts.update(exit=_receipt(first), exit_market=_sync_market(first, market))
                await conn.execute(
                    "UPDATE event_shadow_trial SET status='closed',reason=$2,exit_price=$3,exit_at=$4,"
                    'realized_pnl=$5,fees=fees+$6,borrow_cost=$7,dividend_cash=$8,receipts=$9::jsonb,updated_at=$10 '
                    'WHERE id=$1', trial['id'], chosen_exit['reason'] if chosen_exit else 'planned_exit',
                    fill['price'], first['end'], fill['realized'], fill['fee'], borrow_cost, dividend_cash,
                    _json(receipts), instant,
                )
                await _cash(conn, book, fill['free_delta'], -trial['held_cash'])
                return 'closed'
            reason = 'awaiting_exit_volume'
    await conn.execute('UPDATE event_shadow_trial SET reason=$2,exit_after=$3,receipts=$4::jsonb,updated_at=$5 WHERE id=$1',
                       trial['id'], reason, exit_after, _json(receipts), instant)
    return 'open'


async def run_event_shadow_cycle(pool, *, now=None, quotes=None, borrow=(), corporate_actions=(),
                                 borrow_provider=None, limit=20) -> dict:
    """Fetch bounded recent equity bars by default; no credentials or broker order calls."""
    instant, limit = _clock(now), _bounded(limit)
    async with pool.acquire() as conn, conn.transaction():
        locked = await conn.fetchval("SELECT pg_try_advisory_xact_lock(hashtext('event_shadow_tick_v1'))")
        if not locked:
            return {'status': 'busy'}
        activated = await _isolate(conn, instant)
        await _books(conn)
        candidates = await conn.fetch(
            "SELECT * FROM official_event_watch e WHERE e.first_seen_at >= $1 AND e.first_seen_at <= $2 "
            "AND e.status='observed' AND NOT EXISTS (SELECT 1 FROM event_shadow_observation t "
            'WHERE t.event_id=e.id) AND NOT EXISTS (SELECT 1 FROM official_event_watch superseding '
            'WHERE superseding.ticker=e.ticker AND superseding.source=e.source AND superseding.source_key=e.source_key '
            'AND superseding.first_seen_at<=$2 AND (superseding.first_seen_at,superseding.id)>(e.first_seen_at,e.id)) '
            'ORDER BY e.first_seen_at,e.id LIMIT $3',
            activated, instant, limit,
        )
        new_trials = await _register(conn, [dict(row) for row in candidates], instant, activated)
        active = await conn.fetch(
            f"SELECT ticker,status FROM event_shadow_trial WHERE {_ACTIVE} AND (status='open' OR "
            'entry_after < $2 AND $2 < entry_until) ORDER BY status,decision_at,id LIMIT $3',
            p.POLICY, instant, limit,
        )
    tickers = list(dict.fromkeys(row['ticker'] for row in active))[:MAX_TICKERS - 1]
    faults = []
    live = market_session(instant)['is_open']
    raw = list(quotes) if quotes is not None else []
    if quotes is None and live and tickers:
        raw, faults = await read_regular_bars(tickers + ([p.MARKET] if p.MARKET not in tickers else []), instant)
    loan_rows, corporate_actions = list(borrow), tuple(corporate_actions)
    if live and tickers and borrow_provider is not None:
        try:
            loan_rows += list(await asyncio.wait_for(borrow_provider(tickers, instant), timeout=8))
        except Exception:  # no credentials or vendor exception body in receipts
            faults.append('borrow_provider_unavailable')
    instant = _clock(now)
    sources = {ticker: p.eligible_bars(raw, instant, ticker) for ticker in {*tickers, p.MARKET}}
    result: dict[str, Any] = {'status': 'ok' if market_session(instant)['is_open'] else _NOT_OPEN,
                              'registered_trials': new_trials, 'quoted_tickers': sum(bool(x) for x in sources.values()),
                              'source_unavailable': faults, 'as_of': instant.isoformat()}
    async with pool.acquire() as conn, conn.transaction():
        locked = await conn.fetchval("SELECT pg_try_advisory_xact_lock(hashtext('event_shadow_tick_v1'))")
        if not locked:
            return dict(result, status='busy')
        books = {row['sleeve']: dict(row) for row in await conn.fetch('SELECT * FROM event_shadow_book')}
        rows = await conn.fetch(f'SELECT * FROM event_shadow_trial WHERE {_ACTIVE} AND '
                                "(status='open' OR entry_after<$2) ORDER BY status,decision_at,id LIMIT $3",
                                p.POLICY, instant, limit)
        positions = {key: [] for key in p.SLEEVES}
        for row in await conn.fetch("SELECT * FROM event_shadow_trial WHERE status='open' AND policy=$1", p.POLICY):
            positions[row['sleeve']].append(dict(row))
        for row in rows:
            trial = dict(row)
            sleeve, book, bars = trial['sleeve'], books[trial['sleeve']], sources.get(trial['ticker'], [])
            if trial['status'] == 'open':
                outcome = await _open(conn, trial, book, bars, sources[p.MARKET], loan_rows, corporate_actions, instant)
                if outcome == 'closed':
                    positions[sleeve] = [item for item in positions[sleeve] if item['id'] != trial['id']]
            else:
                outcome = await _pending(conn, trial, book, positions[sleeve], bars, sources[p.MARKET],
                                         loan_rows, corporate_actions, instant, sources)
            result[outcome] = result.get(outcome, 0) + 1
    return result


def _trial_view(record: Any) -> dict:
    row = dict(record)
    receipts = _decode(row, 'receipts')
    cash_fields = ('entry_price', 'exit_price', 'held_cash', 'realized_pnl', 'fees', 'borrow_cost', 'dividend_cash')
    row.update({key: float(row[key]) for key in cash_fields if row.get(key) is not None})
    row['event_evidence'] = _decode(row, 'event_evidence')
    row['receipts'] = {key: receipts.get(key) for key in ('entry', 'exit', 'mark', 'entry_market', 'exit_market',
                                                         'borrow_terms', 'borrow_extension', 'exit_trigger', 'risk')}
    for label, left, right in (('stock', 'entry', 'exit'), ('market', 'entry_market', 'exit_market')):
        before, after = receipts.get(left), receipts.get(right)
        row[f'{label}_return_pct'] = (float((Decimal(after['close']) / Decimal(before['close']) - 1) * 100)
                                     if before and after else None)
    return row


async def read_event_shadow(pool, *, limit=20) -> dict:
    """Small read-only payload. No simulated or user account mutation on a GET."""
    async with pool.acquire() as conn, conn.transaction(isolation='repeatable_read', readonly=True):
        return await _read_snapshot(conn, limit)


async def _read_snapshot(conn, limit) -> dict:
    active = await conn.fetchval('SELECT activated_at FROM event_shadow_runtime WHERE singleton')
    books = await conn.fetch(
        "SELECT b.*, count(t.id) FILTER(WHERE t.status='open') AS open_count, "
        "count(t.id) FILTER(WHERE t.status='closed') AS closed_count, "
        "count(t.id) FILTER(WHERE t.status='pending') AS pending_count, "
        "count(t.id) FILTER(WHERE t.status='expired') AS expired_count, "
        "count(t.id) FILTER(WHERE t.status='abstained') AS abstained_count "
        'FROM event_shadow_book b LEFT JOIN event_shadow_trial t ON b.sleeve=t.sleeve AND t.policy=$1 GROUP BY b.sleeve',
        p.POLICY,
    )
    rows = await conn.fetch(
        'SELECT * FROM event_shadow_trial WHERE policy=$1 AND event_id IN (SELECT event_id '
        'FROM event_shadow_trial WHERE policy=$1 GROUP BY event_id ORDER BY max(decision_at) DESC,event_id DESC '
        'LIMIT $2) ORDER BY decision_at DESC,event_id DESC,sleeve', p.POLICY, _bounded(limit),
    )
    compare = await conn.fetchrow(
        'WITH paired AS (SELECT event_id, '
        "max(realized_pnl) FILTER(WHERE sleeve='long_only') AS long_only, "
        "max(realized_pnl) FILTER(WHERE sleeve='long_short') AS long_short, "
        "max(entry_at) FILTER(WHERE sleeve='long_only') AS long_at, "
        "max(entry_at) FILTER(WHERE sleeve='long_short') AS ls_at, "
        "max(exit_at) FILTER(WHERE sleeve='long_only') AS long_exit, "
        "max(exit_at) FILTER(WHERE sleeve='long_short') AS ls_exit, "
        "bool_or(direction IS NOT NULL) AS eligible, bool_or(status='closed') AS executed "
        'FROM event_shadow_trial WHERE policy=$1 GROUP BY event_id), '
        'matched AS (SELECT *, (long_only IS NOT NULL AND long_short IS NOT NULL '
        'AND (long_at IS NULL OR ls_at IS NULL OR (long_at=ls_at AND long_exit=ls_exit))) AS comparable FROM paired) '
        'SELECT count(*) AS total_events, count(long_only) AS long_only_observed, '
        'count(long_short) AS long_short_observed, count(*) FILTER(WHERE eligible) AS eligible_events, '
        'count(*) FILTER(WHERE executed) AS executed_events, count(*) FILTER(WHERE comparable) AS paired_events, '
        'count(*) FILTER(WHERE comparable AND executed) AS paired_trade_events, '
        'avg(long_short-long_only) FILTER(WHERE comparable) AS paired_difference_usd, '
        'avg(long_short-long_only) FILTER(WHERE comparable AND executed) AS paired_trade_difference_usd, '
        'avg(long_short) FILTER(WHERE comparable) AS paired_long_short_usd, '
        'avg(long_only) FILTER(WHERE comparable) AS paired_long_only_usd FROM matched', p.POLICY,
    )
    return {'status': 'collecting' if active else 'not_activated', 'activated_at': active,
            'policy': {'id': p.POLICY, 'execution_model': p.EXECUTION,
                       'benchmark': p.MARKET, 'holding_minutes': int(p.HOLD.total_seconds() // 60),
                       'direction_source': 'explicit_issuer_guidance_revision_only',
                       'trade_scope': 'research_only_no_broker_orders',
                       'max_single_short_weight': float(p.MAX_SINGLE_SHORT_WEIGHT),
                       'max_short_weight': float(p.MAX_SHORT_WEIGHT),
                       'max_gross_weight': float(p.MAX_GROSS_WEIGHT)},
            'books': {row['sleeve']: {k: float(v) if isinstance(v, Decimal) else v
                                      for k, v in dict(row).items()} for row in books},
            'trials': [_trial_view(row) for row in rows],
            'comparison': {k: float(v) if isinstance(v, Decimal) else v for k, v in dict(compare).items()}}
