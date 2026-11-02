"""Bounded, atomic simulated ledger execution for trusted bot run identities.

The model supplies targets, never cash movements or prices. Market I/O happens
outside transactions; settlement rechecks the durable book under short locks.
"""
from __future__ import annotations

import asyncio
import json
import math
from datetime import UTC, datetime, timedelta
from typing import Any

from alpha_agent.paper.bot_models import BotConfig, BotDecision
from alpha_agent.paper.intraday import EXECUTION_MODEL, fetch_bars, select_fill
from alpha_agent.paper.market_clock import as_utc, market_session

MAX_SETTLEMENT_ORDERS = 40


def _json(value: Any) -> dict:
    return json.loads(value) if isinstance(value, str) else dict(value or {})


def _quote(context: dict, ticker: str, instant: datetime, session: dict) -> float:
    quote = context.get('quotes', {}).get(ticker, {})
    if quote.get('quality') != 'fresh' or quote.get('price_basis') != 'raw_unadjusted':
        raise ValueError('fresh_raw_quote_required')
    price = float(quote.get('price', 0))
    at = as_utc(quote.get('as_of'))
    if not math.isfinite(price) or price <= 0 or not quote.get('source'):
        raise ValueError('invalid_quote')
    if not (as_utc(session['open_at']) < at <= instant and instant - at <= timedelta(minutes=5)):
        raise ValueError('stale_quote')
    return price


def _result(action_id: str, status: str, **values: Any) -> dict:
    return {'action_id': action_id, 'status': status, **values}


async def submit_targets(
    pool: Any, run: dict, decision: BotDecision, context: dict,
    config: BotConfig, now: datetime | str | None = None,
) -> list[dict]:
    """Submit idempotent targets using only current, already-settled cash.

    Deferred actions have no order yet and may be retried with the same action
    identity and refreshed context after sell settlement. Existing orders are
    always returned, never recreated. A cancelled run cannot submit new work.
    """
    instant = as_utc(now) if now is not None else datetime.now(UTC)
    session = market_session(instant)
    if not session['is_open']:
        raise ValueError('market_closed')
    if decision.context_id != str(context.get('context_id')):
        raise ValueError('context_id_mismatch')
    if decision.context_id != str(run['id']):
        raise ValueError('context_run_mismatch')
    deadline = min(as_utc(run['expires_at']), as_utc(session['close_at']))
    if instant >= deadline:
        raise ValueError('run_expired')
    instruments = {str(item['instrument_id']): item for item in context.get('instruments', [])}
    evidence = set(context.get('evidence_ids', []))

    async with pool.acquire() as conn:
        async with conn.transaction():
            account = await conn.fetchrow(
                "SELECT * FROM sim_account WHERE id=$1 FOR UPDATE", run['account_id'],
            )
            if account is None or account['kind'] != 'bot' or account['status'] != 'active':
                raise ValueError('active_bot_account_required')
            locked_run = await conn.fetchrow(
                "SELECT * FROM sim_bot_run WHERE id=$1 AND account_id=$2 FOR UPDATE",
                run['id'], account['id'],
            )
            current_config = await conn.fetchrow(
                "SELECT * FROM sim_bot_config WHERE account_id=$1 FOR UPDATE", account['id'],
            )
            if locked_run is None or locked_run['status'] != 'running':
                raise ValueError('active_run_required')
            if current_config is None or not (
                int(current_config['config_version']) == int(locked_run['config_version'])
                == int(run['config_version'])
            ):
                raise ValueError('config_version_changed')
            if BotConfig.model_validate(_json(current_config['config'])) != config:
                raise ValueError('config_snapshot_mismatch')
            # Waiting for another short ledger transaction must not backdate
            # acceptance or permit a submission after the closing deadline.
            if now is None:
                instant = datetime.now(UTC)
                session = market_session(instant)
                if not session['is_open']:
                    raise ValueError('market_closed')
            if 'lease_token' in run:
                # A reclaimed run may still be "running" with the same config.
                # Fence its old worker using the durable lease, inside the same
                # transaction as every order/cancellation submission.
                lease_until = locked_run.get('lease_until')
                if (run['lease_token'] is None
                        or str(locked_run.get('lease_token')) != str(run['lease_token'])
                        or lease_until is None or as_utc(lease_until) <= instant):
                    raise ValueError('run_lease_lost')
            deadline = min(deadline, as_utc(locked_run['expires_at']))
            if instant >= deadline:
                raise ValueError('run_expired')
            if (locked_run.get('trading_session') is not None
                    and str(locked_run['trading_session']) != session['session_date']):
                raise ValueError('run_session_changed')
            saved_context = _json(locked_run.get('context'))
            if saved_context and str(saved_context.get('context_id')) != decision.context_id:
                raise ValueError('context_id_mismatch')
            cohort = int(account['reset_count'] or 0)
            if int(context.get('account', {}).get('reset_count', -1)) != cohort:
                raise ValueError('account_cohort_changed')
            positions = await conn.fetch(
                "SELECT * FROM sim_position WHERE account_id=$1 AND cohort_id=$2 AND qty>0",
                account['id'], cohort,
            )
            pending = await conn.fetch(
                "SELECT * FROM sim_order WHERE account_id=$1 AND cohort_id=$2 AND status='pending'",
                account['id'], cohort,
            )
            previous = await conn.fetch(
                "SELECT * FROM sim_order WHERE bot_run_id=$1", run['id'],
            )
            by_action = {row['action_id']: row for row in previous}
            held = {row['ticker']: int(row['qty']) for row in positions}
            pending_tickers = {row['ticker'] for row in pending}
            reserved = sum(float(row['reserved_notional'] or 0) for row in pending if row['side'] == 'buy')
            available = max(0.0, float(account['cash']) - reserved)
            results: dict[str, dict] = {}
            plans: list[dict] = []
            marks: dict[str, float] = {}
            mark_error = None
            for ticker in held:
                try:
                    marks[ticker] = _quote(context, ticker, instant, session)
                except (TypeError, ValueError, KeyError) as exc:
                    mark_error = str(exc)
            nav = float(account['cash']) + sum(held[t] * marks.get(t, 0) for t in held)
            desired = dict(held)
            for action in decision.actions:
                aid = action.action_id
                if aid in by_action:
                    order = by_action[aid]
                    results[aid] = _result(aid, 'existing', order_id=order['id'], order_status=order['status'])
                    continue
                if action.type == 'cancel_order':
                    order = await conn.fetchrow(
                        "SELECT * FROM sim_order WHERE id=$1 AND account_id=$2 "
                        "AND execution_model=$3 AND bot_run_id IS NOT NULL FOR UPDATE",
                        action.order_id, account['id'], EXECUTION_MODEL,
                    )
                    if order is None:
                        results[aid] = _result(aid, 'rejected', reason='bot_order_not_found')
                    elif order['status'] != 'pending':
                        results[aid] = _result(aid, 'existing', order_id=order['id'], order_status=order['status'])
                    else:
                        await conn.execute(
                            "UPDATE sim_order SET cancel_requested_at=COALESCE(cancel_requested_at,$1) WHERE id=$2",
                            instant, order['id'],
                        )
                        results[aid] = _result(aid, 'cancel_requested', order_id=order['id'])
                    continue
                instrument = instruments.get(str(action.instrument_id))
                try:
                    if instrument is None:
                        raise ValueError('instrument_not_in_context')
                    instrument_id = int(instrument['instrument_id'])
                    if instrument_id <= 0:
                        raise ValueError('invalid_instrument_id')
                    ticker = instrument['ticker']
                    if not set(action.evidence_ids).issubset(evidence):
                        raise ValueError('unknown_evidence')
                    if action.target_weight > config.max_position_weight:
                        raise ValueError('max_position_weight_exceeded')
                    if mark_error or not math.isfinite(nav) or nav <= 0:
                        raise ValueError('portfolio_mark_unavailable')
                    price = _quote(context, ticker, instant, session)
                    marks[ticker] = price
                    target_qty = math.floor(nav * action.target_weight / price)
                    if ticker in pending_tickers:
                        results[aid] = _result(aid, 'deferred', reason='ticker_has_pending_order')
                        continue
                    delta = target_qty - held.get(ticker, 0)
                    if delta == 0:
                        desired[ticker] = target_qty
                        results[aid] = _result(aid, 'held', ticker=ticker)
                        continue
                    first_end = instant.replace(second=0, microsecond=0) + timedelta(minutes=2)
                    if first_end > deadline:
                        raise ValueError('no_complete_bar_before_expiry')
                    desired[ticker] = target_qty
                    plans.append({
                        'action_id': aid, 'ticker': ticker, 'instrument_id': instrument_id,
                        'side': 'buy' if delta > 0 else 'sell', 'qty': abs(delta), 'price': price,
                    })
                except (TypeError, ValueError, KeyError) as exc:
                    results[aid] = _result(aid, 'rejected', reason=str(exc))
            desired_value = sum(qty * marks.get(ticker, 0) for ticker, qty in desired.items())
            budget_error = (
                'max_positions_exceeded' if len(
                    {ticker for ticker, qty in desired.items() if qty > 0}
                    | {row['ticker'] for row in pending if row['side'] == 'buy'}
                ) > config.max_positions
                else 'targets_exceed_total_capital' if desired_value > nav + 0.000001 else None
            )
            for plan in sorted(plans, key=lambda item: item['side'] == 'buy'):
                aid = plan['action_id']
                if budget_error:
                    results[aid] = _result(aid, 'rejected', reason=budget_error)
                    continue
                reservation = 0.0
                if plan['side'] == 'buy':
                    occupied = set(held) | {row['ticker'] for row in pending if row['side'] == 'buy'}
                    if plan['ticker'] not in occupied and len(occupied) >= config.max_positions:
                        results[aid] = _result(aid, 'deferred', reason='awaiting_settled_position_slot')
                        continue
                    reservation = (plan['qty'] * plan['price'] * (1 + config.slippage_bps / 10000)
                                   * (1 + config.fee_bps / 10000) * 1.01)
                    if reservation > available + 0.000001:
                        results[aid] = _result(aid, 'deferred', reason='awaiting_settled_cash')
                        continue
                order_id = await conn.fetchval(
                    "INSERT INTO sim_order (account_id,ticker,side,order_type,qty,signal_date,"
                    "cohort_id,reserved_notional,fee_bps,bot_run_id,action_id,instrument_id,"
                    "execution_model,accepted_at,expires_at,reference_price,slippage_bps) "
                    "VALUES ($1,$2,$3,'market',$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16) "
                    "RETURNING id",
                    account['id'], plan['ticker'], plan['side'], plan['qty'],
                    datetime.fromisoformat(session['session_date']).date(), cohort, reservation,
                    config.fee_bps, run['id'], aid, plan['instrument_id'], EXECUTION_MODEL,
                    instant, deadline, plan['price'], config.slippage_bps,
                )
                available -= reservation
                pending_tickers.add(plan['ticker'])
                if plan['side'] == 'buy':
                    # A second new ticker in this batch must see this newly
                    # accepted position commitment before it is allowed in.
                    pending.append({'ticker': plan['ticker'], 'side': 'buy'})
                results[aid] = _result(aid, 'accepted', order_id=order_id, ticker=plan['ticker'],
                                       side=plan['side'], qty=plan['qty'])
            return [results[action.action_id] for action in decision.actions]


async def _settle_one(
    pool: Any, candidate: dict, bars: list[dict], instant: datetime, *, refresh_now: bool = False,
) -> str:
    async with pool.acquire() as conn:
        async with conn.transaction():
            account = await conn.fetchrow(
                "SELECT * FROM sim_account WHERE id=$1 AND kind='bot' FOR UPDATE", candidate['account_id'],
            )
            order = await conn.fetchrow(
                "SELECT * FROM sim_order WHERE id=$1 AND account_id=$2 AND status='pending' "
                "AND execution_model=$3 AND bot_run_id IS NOT NULL FOR UPDATE",
                candidate['id'], candidate['account_id'], EXECUTION_MODEL,
            )
            if order is None:
                return 'unchanged'
            if account is None or int(account['reset_count'] or 0) != int(order['cohort_id'] or 0):
                await conn.execute(
                    "UPDATE sim_order SET status='failed',fail_reason='account_cohort_changed' WHERE id=$1",
                    order['id'],
                )
                return 'failed'
            if refresh_now:
                # A concurrent cancel or a closing deadline can occur while we
                # wait for locks. Confirmation is now, never the fetch cutoff.
                instant = datetime.now(UTC)
            result = select_fill(
                order['side'], order['accepted_at'], order['expires_at'], bars, instant,
                cancel_requested_at=order['cancel_requested_at'], slippage_bps=order['slippage_bps'],
            )
            status = result['status']
            if status != 'filled':
                await conn.execute(
                    "UPDATE sim_order SET status=$1,fail_reason=$2,execution_evidence=$3::jsonb WHERE id=$4",
                    status, result.get('reason'), json.dumps(result), order['id'],
                )
                return status
            qty = int(order['qty'])
            price = float(result['fill_price'])
            fee = price * qty * float(order['fee_bps']) / 10000
            position = await conn.fetchrow(
                "SELECT * FROM sim_position WHERE account_id=$1 AND cohort_id=$2 AND ticker=$3 FOR UPDATE",
                account['id'], order['cohort_id'], order['ticker'],
            )
            old_qty = int(position['qty']) if position else 0
            old_cost = float(position['avg_cost']) if position else 0.0
            realized = float(position['realized_pnl'] or 0) if position else 0.0
            failure = None
            if order['side'] == 'buy':
                other_reserved = await conn.fetchval(
                    "SELECT COALESCE(SUM(reserved_notional),0) FROM sim_order WHERE account_id=$1 "
                    "AND cohort_id=$2 AND status='pending' AND side='buy' AND id<>$3",
                    account['id'], order['cohort_id'], order['id'],
                ) or 0
                cost = price * qty + fee
                if cost > float(account['cash']) - float(other_reserved) + 0.000001:
                    failure = 'fill_price_exceeds_available_cash'
                new_qty = old_qty + qty
                avg_cost = (old_qty * old_cost + cost) / new_qty
                cash = float(account['cash']) - cost
            else:
                if old_qty < qty:
                    failure = 'insufficient_position_at_fill'
                new_qty = old_qty - qty
                avg_cost = old_cost
                realized += (price - old_cost) * qty - fee
                cash = float(account['cash']) + price * qty - fee
            if failure:
                await conn.execute(
                    "UPDATE sim_order SET status='failed',fail_reason=$1,execution_evidence=$2::jsonb WHERE id=$3",
                    failure, json.dumps(result | {'ledger_error': failure}), order['id'],
                )
                return 'failed'
            mark_at = as_utc(result['bar']['end'])
            quality = 'fresh' if instant - mark_at <= timedelta(minutes=5) else 'stale'
            await conn.execute(
                "INSERT INTO sim_position (account_id,cohort_id,ticker,qty,avg_cost,realized_pnl,"
                "instrument_id,mark_price,mark_at,price_quality) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) "
                "ON CONFLICT (account_id,cohort_id,ticker) DO UPDATE SET qty=EXCLUDED.qty,"
                "avg_cost=EXCLUDED.avg_cost,realized_pnl=EXCLUDED.realized_pnl,"
                "instrument_id=EXCLUDED.instrument_id,mark_price=EXCLUDED.mark_price,"
                "mark_at=EXCLUDED.mark_at,price_quality=EXCLUDED.price_quality,updated_at=now()",
                account['id'], order['cohort_id'], order['ticker'], new_qty, avg_cost, realized,
                order['instrument_id'], float(result['bar']['close']), mark_at, quality,
            )
            await conn.execute("UPDATE sim_account SET cash=$1 WHERE id=$2", cash, account['id'])
            evidence = result | {'qty': qty, 'fee_bps': float(order['fee_bps']), 'transaction_cost': fee}
            await conn.execute(
                "UPDATE sim_order SET status='filled',fill_date=$1,fill_price=$2,transaction_cost=$3,"
                "filled_at=$4,reference_price=$5,execution_evidence=$6::jsonb,fail_reason=NULL WHERE id=$7",
                datetime.fromisoformat(result['session_date']).date(), price, fee,
                as_utc(result['filled_at']), result['reference_price'], json.dumps(evidence), order['id'],
            )
            return 'filled'


async def settle_orders(
    pool: Any, account_id: int | None = None, now: datetime | str | None = None,
) -> dict:
    """Settle at most 40 bot orders, with at most two simultaneous raw fetches."""
    instant = as_utc(now) if now is not None else datetime.now(UTC)
    rows = await pool.fetch(
        "SELECT so.* FROM sim_order so JOIN sim_account sa ON sa.id=so.account_id "
        "WHERE sa.kind='bot' AND so.execution_model=$1 AND so.bot_run_id IS NOT NULL "
        "AND so.status='pending' AND ($2::bigint IS NULL OR so.account_id=$2) "
        "ORDER BY CASE so.side WHEN 'sell' THEN 0 ELSE 1 END,so.accepted_at,so.id LIMIT $3",
        EXECUTION_MODEL, account_id, MAX_SETTLEMENT_ORDERS,
    )
    orders = [dict(row) for row in rows]
    semaphore = asyncio.Semaphore(2)
    quotes: dict[str, list[dict]] = {}
    errors: list[dict] = []

    async def load(ticker: str) -> None:
        async with semaphore:
            try:
                quotes[ticker] = await fetch_bars(ticker, instant)
            except Exception as exc:
                quotes[ticker] = []
                errors.append({'ticker': ticker, 'error': f'{type(exc).__name__}: {str(exc)[:200]}'})

    await asyncio.gather(*(load(ticker) for ticker in sorted({row['ticker'] for row in orders})))
    if now is None:
        # fetch_bars timestamps evidence when the provider actually returns.
        # Using the earlier request cutoff here would reject every real bar as
        # "fetched in the future". Explicit replay/test clocks remain fixed.
        instant = datetime.now(UTC)
    counts = {'filled': 0, 'pending': 0, 'failed': 0, 'expired': 0, 'cancelled': 0}
    for order in orders:
        try:
            status = await _settle_one(
                pool, order, quotes[order['ticker']], instant, refresh_now=now is None,
            )
            if status in counts:
                counts[status] += 1
        except Exception as exc:
            errors.append({'order_id': order['id'], 'ticker': order['ticker'],
                           'error': f'{type(exc).__name__}: {str(exc)[:200]}'})
    return counts | {'errors': errors}
