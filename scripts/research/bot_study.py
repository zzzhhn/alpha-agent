"""Offline bot audit. Never imports application modules or calls providers/DB.

Only CLI functions read/write files. Pure kernels accept explicit clocks/data.
Returns are exploratory price-only research units, not executable live P&L.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from collections import Counter
from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import time

import numpy as np
import pandas as pd


def unpack(value):
    return json.loads(value) if isinstance(value, str) else value or {}


def evidence_check(context, decision):
    """Check references against the actual map, not a reconstructed historical map."""
    evidence = context.get('evidence_map')
    refs = [r for a in decision.get('actions', []) for r in a.get('evidence_ids', [])]
    instruments = {str(x['instrument_id']): x['ticker'] for x in context.get('instruments', [])}
    missing, wrong_ticker, no_refs = [], 0, 0
    for action in decision.get('actions', []):
        if action.get('type', 'set_target_weight') == 'cancel_order':
            continue
        ids = action.get('evidence_ids', [])
        no_refs += not bool(ids)
        if evidence is not None:
            missing.extend(r for r in ids if r not in evidence)
            ticker = instruments.get(str(action.get('instrument_id')))
            wrong_ticker += bool(ids) and not any(evidence.get(r, {}).get('ticker') == ticker for r in ids)
    return {'references': len(refs), 'map_available': evidence is not None,
            'missing_references': len(missing) if evidence is not None else None,
            'wrong_ticker_actions': wrong_ticker if evidence is not None else None,
            'actions_without_references': no_refs}


def numeric_claims(context, text):
    """Conservative claim extractor: explicit ticker/rank and ticker/score only.

    Never declares all prose true just because its numeric tokens occur somewhere.
    Unsupported cost/score comparisons and broad overlap claims are separate flags.
    """
    recs = {x['ticker']: x for x in context.get('recommendations', [])}
    checks = []
    for ticker, rank in re.findall(r'([A-Z][A-Z0-9.\-]{0,9})(?:第|[（(]第)(\d+)', text):
        if ticker in recs:
            checks.append({'field': 'rank', 'matches': recs[ticker].get('rank') == int(rank)})
    for ticker, score in re.findall(r'([A-Z][A-Z0-9.\-]{0,9})[（(](?:第\d+[，,]\s*)?(?:综合分)?(\d+\.\d{2,})', text):
        if ticker in recs:
            checks.append({'field': 'composite_z', 'matches': abs(recs[ticker]['composite_z'] - float(score)) <= .0011})
    held = {p['ticker'] for p in context.get('account', {}).get('positions', []) if p.get('qty', 0) > 0}
    overlap_match = re.search(r'与平台(?:排名|推荐)?前(\d+)完全一致', text)
    overlap_n = int(overlap_match.group(1)) if overlap_match else 8
    claimed_top = {x['ticker'] for x in recs.values() if x.get('rank') is not None and x['rank'] <= overlap_n}
    range_check = None
    match = re.search(r'各仓权重约(\d+\.\d+)%-(\d+\.\d+)%', text)
    positions = context.get('account', {}).get('positions', [])
    quotes = context.get('quotes', {})
    if match and positions and all(quotes.get(p['ticker'], {}).get('quality') == 'fresh' for p in positions):
        values = [p['qty']*quotes[p['ticker']]['price'] for p in positions]
        nav = context['account']['cash']+sum(values)
        range_check = all(abs(actual-float(claim)/100) <= .00051 for actual, claim in zip([min(values)/nav, max(values)/nav], match.groups()))
    return {'explicit_checks': len(checks), 'mismatches': sum(not x['matches'] for x in checks),
            'overlap_claim_false': bool(overlap_match) and len(claimed_top) == overlap_n and held != claimed_top,
            'weight_range_matches': range_check,
            'score_cost_uncalibrated': '综合分' in text and any(w in text for w in ['覆盖', '不划算', '成本']) and any(w in text for w in ['差距', '接近', '信号差距']),
            'scope': 'explicit ticker rank/score only; other quantitative prose requires human review'}


def audit_runs(runs):
    output = []
    for i, run in enumerate(sorted(runs, key=lambda r: r['created_at']), 1):
        context, result = unpack(run['context']), unpack(run['result'])
        decision = result.get('decision', {})
        recs = context.get('recommendations', [])
        top = {r['ticker'] for r in recs if r.get('rank') is not None and r['rank'] <= 8}
        book = context.get('account', {})
        held = {p['ticker'] for p in book.get('positions', []) if p.get('qty', 0) > 0}
        values = {p['ticker']: p['qty'] * (p.get('current_price') or 0) for p in book.get('positions', [])}
        quotes = context.get('quotes', {})
        if held and all(quotes.get(t, {}).get('quality') == 'fresh' for t in held):
            values = {p['ticker']: p['qty']*quotes[p['ticker']]['price'] for p in book['positions'] if p.get('qty', 0) > 0}
            nav = book['cash'] + sum(values.values())
        else:
            nav = book.get('portfolio_value')
        active_distance = None
        if nav and len(top) == 8:
            weights = {t: v/nav for t, v in values.items()}
            active_distance = .5 * (sum(abs(weights.get(t, 0) - (1/8 if t in top else 0)) for t in top | held) + book['cash']/nav)
        actions = result.get('actions', [])
        config = unpack(run['config_snapshot'])
        output.append({'run': i, 'time': run['created_at'][:16], 'status': run['status'],
                       'outcome': result.get('outcome_reason', decision.get('decision', 'unknown')),
                       'config_version': run['config_version'], 'decision': decision.get('decision'),
                       'decision_preserved': bool(decision),
                       'proposed_actions': len(decision.get('actions', [])),
                       'action_statuses': dict(Counter(a['status'] for a in actions)),
                       'guard_reasons': dict(Counter(a.get('reason', 'unspecified') for a in actions if a['status'] in ['rejected', 'deferred'])),
                       'citations': evidence_check(context, decision),
                       'numbers': numeric_claims(context, run.get('summary') or ''),
                       'held': len(held) if context else None,
                       'top8_overlap': len(held & top) if context and len(top) == 8 else None,
                       'outside_top8': len(held-top) if context and len(top) == 8 else None,
                       'active_weight_distance': active_distance,
                       'research_age': context.get('research_age_sessions'),
                       'horizon': config.get('horizon_sessions'),
                       'model': run['model'], 'prompt_tokens': run['prompt_tokens'],
                       'completion_tokens': run['completion_tokens'], 'llm_calls': run['llm_calls'],
                       'cost_usd': None, 'cost_reason': 'no_local_pricing_or_invoice',
                       'at_4096_limit': run['completion_tokens'] == 4096,
                       'premarket_mislabeled_closed': bool(context and not context.get('market', {}).get('is_open') and '已收盘' in (run.get('summary') or '') and pd.Timestamp(context['created_at']) < pd.Timestamp(context['market']['open_at']))})
    return output


@dataclass(frozen=True)
class Policy:
    sleeve: str = 'tactical'
    n: int = 8
    cadence: str = 'snapshot'
    hold_k: int | None = None
    kind: str = 'ranked'

    @property
    def name(self):
        return f'{self.sleeve}_n{self.n}_{self.cadence}_k{self.hold_k or 0}_{self.kind}'


def policy_grid():
    """36 predeclared variants; every one is retained, including failures."""
    return [Policy(s, n, c, k) for s in ['tactical', 'strategic']
            for c in ['snapshot', 'weekly', '20sessions']
            for n, k in [(8, None), (12, None), (20, None), (8, 12), (8, 20), (8, 30)]]


def select_targets(held, ranks, policy):
    ordered = sorted(ranks, key=lambda t: (ranks[t], t))
    if policy.hold_k is None:
        return ordered[:policy.n]
    keep = sorted(t for t in held if ranks.get(t, math.inf) <= policy.hold_k)
    candidates = [t for t in ordered if ranks[t] <= 8 and t not in keep]
    return keep + candidates[:max(0, policy.n-len(keep))]


def fill_cash_delta(side, qty, price, fee_bps=10, slippage_bps=5):
    f, s = fee_bps/10000, slippage_bps/10000
    fill = price * (1+s if side == 'buy' else 1-s)
    return (-1 if side == 'buy' else 1) * qty * fill * (1+f if side == 'buy' else 1-f)


def rebalance(cash, held, prices, targets, *, cap=.25, turnover_cap=2., preserve=False,
              fee_bps=10, slippage_bps=5):
    """Whole units, sell then buy, cash nonnegative. Missing targets leave cash.

    1% reservation cushion mirrors submission sizing; same-close settlement is
    explicitly an offline approximation. Price gaps/corporate actions not solved.
    """
    held = dict(held)
    if any(not np.isfinite(prices.get(t, np.nan)) for t in held):
        return cash, held, 0., 0., 'missing_held_execution_mark'
    nav = cash + sum(q*prices[t] for t, q in held.items())
    desired = {}
    for t in set(held) | set(targets):
        p = prices.get(t, np.nan)
        if t not in targets:
            desired[t] = 0
        elif not np.isfinite(p) or p <= 0:
            desired[t] = held.get(t, 0)
        elif preserve and t in held:
            desired[t] = min(held[t], math.floor(nav*cap/p))
        else:
            desired[t] = math.floor(nav * min(cap, 1/len(targets)) / p)
    planned = sum(abs(desired[t]-held.get(t, 0))*prices.get(t, 0) for t in desired if np.isfinite(prices.get(t, np.nan)))
    if planned > turnover_cap*nav + 1e-6:
        return cash, held, 0., 0., 'turnover_budget_exceeded'
    notional, drag = 0., 0.
    for buying in [False, True]:
        for t in sorted(desired):
            delta = desired[t]-held.get(t, 0)
            if (delta > 0) != buying or delta == 0:
                continue
            price = prices[t]
            qty = abs(delta)
            side = 'buy' if buying else 'sell'
            unit = abs(fill_cash_delta(side, 1, price, fee_bps, slippage_bps))
            if buying:
                qty = min(qty, math.floor(max(0., cash)/(unit*1.01)))
            if qty <= 0:
                continue
            flow = fill_cash_delta(side, qty, price, fee_bps, slippage_bps)
            cash += flow
            held[t] = held.get(t, 0) + (qty if buying else -qty)
            notional += qty*price
            drag += abs(flow)-qty*price if buying else qty*price-flow
            if not held[t]:
                del held[t]
    assert cash >= -1e-6
    return cash, held, notional/nav, drag/nav, None


def snapshot_clock(scheduled, available_at, sessions, closes):
    """D is earliest session close at/after date and publication proxy; D+1 fill."""
    i = bisect_left(sessions, scheduled)
    while i < len(sessions) and pd.Timestamp(closes[i]) < pd.Timestamp(available_at):
        i += 1
    return (i, i+1) if i+1 < len(sessions) else (None, None)


def simulate(policy, snapshots, sessions, matrix, *, initial_cash=1_000_000., fee_bps=10, slippage_bps=5):
    cash, held = initial_cash, {}
    navs, turns, drags, bad = [], [], [], []
    lastmarks, last_decision, last_week, pending = {}, -10000, None, None
    failures = Counter()
    sources = {s['decision_index']: s for s in snapshots}
    events = 0
    for i, day in enumerate(sessions):
        marks = matrix.loc[day].to_dict()
        for t in held:
            if np.isfinite(marks.get(t, np.nan)):
                lastmarks[t] = marks[t]
        missing = any(not np.isfinite(marks.get(t, np.nan)) for t in held)
        turnover, drag = 0., 0.
        if pending is not None:
            targets = select_targets(held, pending['ranks'][policy.sleeve], policy)
            if policy.kind == 'eligible':
                targets = pending['eligible']
            missing_target = sum(not np.isfinite(marks.get(t, np.nan)) for t in targets)
            failures['missing_target_price'] += missing_target
            cash, held, turnover, drag, failure = rebalance(
                cash, held, marks, targets, preserve=policy.hold_k is not None,
                cap=.02 if policy.kind == 'eligible' else 1. if policy.kind == 'spy' else .25,
                fee_bps=fee_bps, slippage_bps=slippage_bps)
            if failure:
                failures[failure] += 1
            events += 1
            pending = None
        for t in held:
            if np.isfinite(marks.get(t, np.nan)):
                lastmarks[t] = marks[t]
        # Carry marks ONLY for a visibly labelled diagnostic path. Primary is null
        # for the entire period if even one exposed session lacks a true price.
        navs.append(cash + sum(q*lastmarks[t] for t, q in held.items()))
        turns.append(turnover)
        drags.append(drag)
        bad.append(missing)
        snap = sources.get(i)
        if snap:
            week = pd.Timestamp(day).isocalendar()[:2]
            due = policy.cadence == 'snapshot' or (policy.cadence == 'weekly' and week != last_week) or (policy.cadence == '20sessions' and i-last_decision >= 20)
            ranks = snap['ranks'][policy.sleeve]
            if due and (ranks or policy.kind == 'eligible'):
                pending, last_decision, last_week = snap, i, week
            elif due and not ranks:
                failures['ranking_unavailable'] += 1
    returns = np.asarray(navs)/np.r_[initial_cash, navs[:-1]]-1
    return {'nav': np.asarray(navs), 'returns': returns, 'turnover': np.asarray(turns),
            'cost_drag': np.asarray(drags), 'missing': np.asarray(bad),
            'failures': dict(failures), 'events': events, 'ending_positions': len(held)}


def bootstrap_metrics(returns, spy, ew, turnover, *, reps=600, block=5, seed=20261112):
    """Paired circular moving blocks; exploratory percentile intervals, no p-values."""
    n = len(returns)
    rng = np.random.default_rng(seed)
    starts = rng.integers(n, size=(reps, math.ceil(n/block)))
    ix = ((starts[..., None]+np.arange(block)) % n).reshape(reps, -1)[:, :n]
    a, b, c = (np.asarray(x)[ix] for x in [returns, spy, ew])
    ar, br, cr = (np.prod(1+x, axis=1)-1 for x in [a, b, c])
    paths = np.cumprod(1+a, axis=1)
    peaks = np.maximum.accumulate(np.column_stack([np.ones(reps), paths]), axis=1)[:, 1:]
    dd = np.max(1-paths/peaks, axis=1)
    series = {'return': ar, 'excess_spy': ar-br, 'excess_eligible': ar-cr,
              'turnover': np.asarray(turnover)[ix].sum(axis=1), 'max_drawdown': dd}
    return {key: np.quantile(value, [.025, .975]).tolist() for key, value in series.items()}


def summarize(path, spy, ew, *, reps=600, block=5):
    r = path['returns']
    wealth = np.r_[1., np.cumprod(1+r)]
    total = wealth[-1]-1
    dd = float(np.max(1-wealth/np.maximum.accumulate(wealth)))
    result = {'sessions': len(r), 'return': total,
              'excess_spy': total-(np.prod(1+spy['returns'])-1),
              'excess_eligible': total-(np.prod(1+ew['returns'])-1),
              'turnover': float(path['turnover'].sum()), 'max_drawdown': dd,
              'cost_drag_sum': float(path['cost_drag'].sum()), 'events': path['events'],
              'missing_exposed_sessions': int(path['missing'].sum()), 'failures': path['failures']}
    own_bad = bool(path['missing'].any())
    spy_bad = bool(spy['missing'].any())
    ew_bad = bool(ew['missing'].any())
    result['quality'] = 'incomplete_path' if own_bad else 'complete_price_path_not_PIT_certified'
    result['benchmark_quality'] = {'spy_complete': not spy_bad, 'eligible_complete': not ew_bad}
    intervals = bootstrap_metrics(r, spy['returns'], ew['returns'], path['turnover'], reps=reps, block=block)
    result['ci95'] = intervals
    diagnostic = {}
    invalid = (['return', 'max_drawdown'] if own_bad else []) + (['excess_spy'] if own_bad or spy_bad else []) + (['excess_eligible'] if own_bad or ew_bad else [])
    for key in invalid:
        diagnostic[key] = result[key]
        result[key] = None
        intervals[key] = None
    if diagnostic:
        result['diagnostic_carried_marks'] = diagnostic

    return result


def prepare_snapshots(runs, ratings, sessions, closes):
    result, collisions = [], 0
    complete = runs[(runs.status == 'complete') & (runs.run_type == 'daily_close')]
    for row in complete.sort_values('created_at').to_dict('records'):
        frame = ratings[ratings.run_id == row['id']]
        times = pd.to_datetime(frame.as_of, utc=True, errors='coerce')
        available = max(pd.Timestamp(row['created_at']), times.max())
        di, ei = snapshot_clock(str(row['scheduled_for_date']), available, sessions, closes)
        if di is None:
            continue
        good = frame[frame.eligible & ~((frame.ticker == 'PARA') & (str(row['scheduled_for_date']) > '2025-08-06'))]
        tact = {x.ticker: float(x.rank) for x in good.itertuples() if pd.notna(x.rank)}
        # Do not infer missing historical long rankings from current scoring.
        strat = {x.ticker: float(x.long_policy_rank) for x in good.itertuples() if pd.notna(x.long_policy_rank)}
        result.append({'decision_index': di, 'entry_index': ei,
                       'ranks': {'tactical': tact, 'strategic': strat},
                       'eligible': sorted(good.ticker.tolist()),
                       'scheduled': str(row['scheduled_for_date']), 'available_proxy': available.isoformat()})
    unique = {}
    for item in result:
        collisions += item['decision_index'] in unique
        unique[item['decision_index']] = item
    return sorted(unique.values(), key=lambda x: x['decision_index']), {'complete_runs': len(complete), 'executable_runs': len(result), 'same_decision_close_collisions': collisions, 'decision_closes': len(unique), 'strategic_rank_runs': sum(bool(x['ranks']['strategic']) for x in result)}


def slot_comparator(data, matrix, sessions, closes):
    """Same saved contexts and actual run opportunities; daily-close approximation.

    Never creates missing scheduled opportunities or uses post-slot snapshots.
    Two same-day slots settle sequentially at the SAME close (not real clock).
    """
    cash = float(data['account'][0]['initial_cash'])
    held, nav, overlap, unavailable = {}, {}, [], Counter()
    events = {}
    for r in sorted(data['runs'], key=lambda r: r['created_at']):
        c = unpack(r['context'])
        if c and c.get('market', {}).get('is_open'):
            day = r['trading_session']
            events.setdefault(day, []).append(c)
    for day in sessions:
        marks = matrix.loc[day].to_dict()
        for c in events.get(day, []):
            if c.get('research_usable_for_new_buy') is False:
                unavailable['stale_or_unavailable_research'] += 1
                continue
            top = sorted(c.get('recommendations', []), key=lambda x: (x.get('rank') or math.inf, x['ticker']))[:8]
            # All decisions select from the supplied context, not a newer export.
            targets = [x['ticker'] for x in top]
            quotes = c.get('quotes', {})
            if any(quotes.get(t, {}).get('quality') != 'fresh' for t in held):
                unavailable['portfolio_mark_unavailable'] += 1
                continue
            executable = dict(marks)
            for t in targets:
                if quotes.get(t, {}).get('quality') != 'fresh':
                    executable[t] = np.nan
                    unavailable['target_quote_unavailable'] += 1
            cash, held, _, _, failure = rebalance(cash, held, executable, targets)
            if failure:
                unavailable[failure] += 1
        if all(np.isfinite(marks.get(t, np.nan)) for t in held):
            nav[day] = cash + sum(q*marks[t] for t, q in held.items())
    quality = Counter()
    valid_equity = []
    for e in data['equity']:
        day = e['as_of_date']
        if day not in sessions or e['valuation_quality'] not in ['cash_only', 'session_close'] or e.get('portfolio_value') is None:
            quality['invalid_or_pre_account'] += 1
            continue
        if pd.Timestamp(e['valued_at']) < pd.Timestamp(closes[sessions.index(day)]):
            quality['before_close'] += 1
            continue
        valid_equity.append(e)
    for e in valid_equity:
        day = e['as_of_date']
        if day in nav:
            overlap.append({'date': day, 'bot_nav': e['portfolio_value'], 'rule_nav': nav[day]})
    first, last = overlap[0], overlap[-1]
    botret = last['bot_nav']/first['bot_nav']-1
    ruleret = last['rule_nav']/first['rule_nav']-1
    return {'first': first['date'], 'last': last['date'], 'close_observations': len(overlap),
            'return_intervals': len(overlap)-1, 'invested_close_observations': sum(e['cash'] < e['portfolio_value'] for e in valid_equity),
            'bot_return': botret, 'rule_return': ruleret, 'bot_minus_rule': botret-ruleret,
            'bot_final_nav': last['bot_nav'], 'rule_final_nav': last['rule_nav'],
            'v4_from_initial_cash_bot': last['bot_nav']/float(data['account'][0]['initial_cash'])-1,
            'v4_from_initial_cash_rule': last['rule_nav']/float(data['account'][0]['initial_cash'])-1,
            'v4_first_close': next(x for x in overlap if x['date'] >= '2026-11-06'),
            'daily_close_points': overlap, 'excluded': dict(quality), 'failures': dict(unavailable),
            'basis': 'saved-context opportunities; same-slot-day close; no minute matching; price basis unreconciled',
            'increment_identified': False}


def load_inputs(data_dir):
    return (json.loads((data_dir/'bot_account3.json').read_text()),
            pd.read_parquet(data_dir/'rating_snapshot.parquet'),
            pd.read_parquet(data_dir/'research_run.parquet'),
            pd.read_parquet(data_dir/'daily_prices.parquet'))


def study(data, ratings, runs, prices, *, reps=600, block=5):
    import exchange_calendars as xcals
    prices = prices.copy()
    prices['date'] = prices.date.astype(str)
    prices = prices[~((prices.ticker == 'PARA') & (prices.date > '2025-08-06'))]
    if prices.duplicated(['ticker', 'date']).any():
        raise ValueError('duplicate price keys')
    matrix = prices.pivot(index='date', columns='ticker', values='close').sort_index()
    if ((matrix <= 0) & matrix.notna()).any().any():
        raise ValueError('nonpositive price')
    cal = xcals.get_calendar('XNYS', start='2026-02-20', end='2026-11-12')
    sessions = [d.strftime('%Y-%m-%d') for d in cal.sessions if '2026-06-20' <= d.strftime('%Y-%m-%d') <= matrix.index.max()]
    closes = [cal.session_close(d).isoformat() for d in sessions]
    matrix = matrix.reindex(sessions)
    snapshots, inventory = prepare_snapshots(runs, ratings, sessions, closes)
    suspect = matrix.pct_change(fill_method=None).abs() > .35
    # Include earlier jumps as well in the input quality count, without revising
    # historical ranks or treating this counterfactual as repaired real prices.
    full_matrix = prices.pivot(index='date', columns='ticker', values='close').sort_index()
    jumps_all = full_matrix.pct_change(fill_method=None).abs() > .35
    corrected = matrix.copy()
    jumps = matrix.pct_change(fill_method=None)
    for t in matrix:
        for i in np.flatnonzero(suspect[t].to_numpy()):
            corrected.iloc[i:, corrected.columns.get_loc(t)] /= (1+jumps.iloc[i][t])
    first_strategic = next(sessions[s['decision_index']] for s in snapshots if s['ranks']['strategic'])
    periods = {'choose': ('2026-06-20', '2026-09-30'), 'check': ('2026-10-01', '2026-11-11'),
               'full': ('2026-06-20', '2026-11-11'), 'common_sleeve': (first_strategic, '2026-11-11')}
    registry, results, contrasts = [], [], []
    for variant, policy in enumerate(policy_grid(), 1):
        registry.append({'trial': variant, 'policy': policy.name, **asdict(policy), 'purpose': 'exploratory; not frozen-40 family'})
    for sensitivity, panel in [('as_exported', matrix), ('jump_neutralized_counterfactual', corrected)]:
        for period, (start, end) in periods.items():
            days = [d for d in sessions if start <= d <= end]
            offset = sessions.index(days[0])
            snaps = [{**s, 'decision_index': s['decision_index']-offset, 'entry_index': s['entry_index']-offset}
                     for s in snapshots if start <= sessions[s['decision_index']] <= end]
            # Reset each block; no inherited train holdings or borrowed labels.
            sub = panel.loc[days]
            spy = simulate(Policy(n=1, kind='spy'), [{'decision_index': 0, 'ranks': {'tactical': {'SPY': 1}}, 'eligible': ['SPY']}], days, sub)
            ew = simulate(Policy(n=10000, kind='eligible'), snaps, days, sub)
            paths = {}
            for policy in policy_grid():
                path = simulate(policy, snaps, days, sub)
                paths[policy.name] = path
                metrics = summarize(path, spy, ew, reps=reps, block=block)
                results.append({'policy': policy.name, 'period': period, 'sensitivity': sensitivity, **metrics})
            for policy in policy_grid():
                path = paths[policy.name]
                baseline = paths[Policy(sleeve=policy.sleeve).name]
                intervals = bootstrap_metrics(path['returns'], baseline['returns'], baseline['returns'], path['turnover']-baseline['turnover'], reps=reps, block=block)
                bad = bool(path['missing'].any() or baseline['missing'].any())
                contrasts.append({'policy': policy.name, 'period': period, 'sensitivity': sensitivity,
                                  'baseline': Policy(sleeve=policy.sleeve).name,
                                  'net_return_difference': None if bad else float(np.prod(1+path['returns'])-np.prod(1+baseline['returns'])),
                                  'net_difference_ci95': None if bad else intervals['excess_spy'],
                                  'turnover_difference': float((path['turnover']-baseline['turnover']).sum()),
                                  'turnover_difference_ci95': intervals['turnover'],
                                  'cost_drag_difference': float((path['cost_drag']-baseline['cost_drag']).sum())})
            for label, path in [('SPY', spy), ('eligible_EW', ew)]:
                results.append({'policy': label, 'period': period, 'sensitivity': sensitivity,
                                **summarize(path, spy, ew, reps=reps, block=block)})
    choose = [r for r in results if r['period'] == 'choose' and r['sensitivity'] == 'as_exported' and r['policy'].startswith('tactical') and r.get('return') is not None]
    selected = max(choose, key=lambda x: (x['return'], x['policy']))['policy'] if choose else None
    return {'protocol': {'fee_bps': 10, 'slippage_bps': 5, 'bootstrap_reps': reps,
                         'block_sessions': block, 'seed': 20261112, 'initial_cash': 1_000_000,
                         'terminal': 'mark_to_market_no_fictional_liquidation', 'trial_count': len(registry),
                         'selection': 'maximum choose net return among tactical policies only; deterministic name tie-break',
                         'selected_policy': selected, 'periods': periods},
            'inventory': {**inventory, 'expected_sessions': len(sessions),
                          'suspect_events_all_prices': int(jumps_all.sum().sum()),
                          'suspect_events_study': int(suspect.sum().sum()),
                          'suspect_tickers': sorted(suspect.columns[suspect.any()].tolist()),
                          'first_strategic_rank_decision': first_strategic},
            'audit': audit_runs(data['runs']), 'slot_comparator': slot_comparator(data, matrix, sessions, closes),
            'order_audit': {'filled_orders': sum(o['status'] == 'filled' for o in data['orders']),
                            'paid_fees': sum(float(o['transaction_cost'] or 0) for o in data['orders'] if o['status'] == 'filled'),
                            'slippage_notional': sum(abs(float(o['fill_price'])-float(o['reference_price']))*o['qty'] for o in data['orders'] if o['status'] == 'filled')},
            'trials': registry, 'results': results, 'paired_contrasts': contrasts}


def pct(value):
    return '未知' if value is None else f'{value*100:.2f}'


def render_markdown(result):
    lines = ['# 机器人离线研究汇总', '', '仅本地研究；价格缺失时主收益留空，carried marks 只作诊断。', '',
             '## 日志审计', '', '|轮次/UTC|状态|决策动作|引用/缺失|Top8重合|输入/输出token|', '|---|---|---:|---|---|---|']
    for r in result['audit']:
        c = r['citations']
        lines.append(f"|{r['run']} {r['time']}|{r['status']}|{r['proposed_actions']}|{c['references']}/{c['missing_references']}|{r['top8_overlap']}|{r['prompt_tokens']}/{r['completion_tokens']}|")
    lines += ['', '## 全试验登记与结果', '', '数值为百分比；换手是累计双边名义/NAV。CI 为配对时间块 bootstrap 95%描述区间，未经选择校正。', '',
              '|敏感性|区块|策略|净收益|对SPY差|对eligible差|换手|最大回撤|净收益CI|质量|', '|---|---|---|---:|---:|---:|---:|---:|---|---|']
    for r in result['results']:
        ci = r['ci95']
        interval = ','.join(pct(x) for x in ci['return']) if ci and ci['return'] else '未知'
        lines.append('|'+ '|'.join([r['sensitivity'], r['period'], r['policy'], pct(r.get('return')), pct(r.get('excess_spy')), pct(r.get('excess_eligible')), pct(r['turnover']), pct(r.get('max_drawdown')), interval, r['quality']])+'|')
    lines += ['', '## 相对同sleeve逐快照Top8的配对差', '', '|敏感性|区块|策略|净收益差pp|差值CI|换手差pp|费用拖累差pp|', '|---|---|---|---:|---|---:|---:|']
    for r in result['paired_contrasts']:
        ci = r['net_difference_ci95']
        lines.append('|'+ '|'.join([r['sensitivity'], r['period'], r['policy'], pct(r['net_return_difference']), ','.join(pct(x) for x in ci) if ci else '未知', pct(r['turnover_difference']), pct(r['cost_drag_difference'])])+'|')
    lines += ['', '## 试验定义', '', '```json', json.dumps(result['trials'], ensure_ascii=False, indent=2), '```']
    return '\n'.join(lines)+'\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path('/tmp/alpha-research/data'))
    parser.add_argument('--out-dir', type=Path, default=Path('/tmp/alpha-research/out/bot'))
    parser.add_argument('--bootstrap-reps', type=int, default=600)
    parser.add_argument('--block-sessions', type=int, default=5)
    args = parser.parse_args()
    if args.bootstrap_reps < 20 or args.block_sessions < 1:
        parser.error('bootstrap-reps >=20 and block-sessions >=1 required')
    started = time.monotonic()
    inputs = load_inputs(args.data_dir)
    result = study(*inputs, reps=args.bootstrap_reps, block=args.block_sessions)
    result['input_sha256'] = {name: hashlib.sha256((args.data_dir/name).read_bytes()).hexdigest() for name in ['bot_account3.json', 'rating_snapshot.parquet', 'research_run.parquet', 'daily_prices.parquet']}
    result['runtime_seconds'] = round(time.monotonic()-started, 3)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir/'bot_study.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    (args.out_dir/'bot_study.md').write_text(render_markdown(result))
    print(json.dumps({'runtime_seconds': result['runtime_seconds'], 'inventory': result['inventory'], 'selected': result['protocol']['selected_policy'], 'out_dir': str(args.out_dir)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
