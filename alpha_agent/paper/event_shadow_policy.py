"""Frozen rules and pure evidence/accounting functions for the research sleeves."""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable

from alpha_agent.paper.market_clock import as_utc, market_session

POLICY = 'official_guidance_v1'
EXECUTION = 'indicative_regular_minute_close_v1'
MARKET = 'SPY'
SLEEVES = ('no_trade', 'long_only', 'long_short')
INITIAL_CASH = Decimal('100000.00')
MAX_TRADE = Decimal('5000.00')
MAX_GROSS = Decimal('25000.00')
MAX_SINGLE_SHORT_WEIGHT = Decimal('0.05')
MAX_SHORT_WEIGHT = Decimal('0.20')
MAX_GROSS_WEIGHT = Decimal('1.00')
MAX_POSITIONS = 5
FEE_RATE = Decimal('0.0010')
SLIPPAGE = Decimal('0.0010')
INITIAL_MARGIN = Decimal('0.50')
MAINTENANCE = Decimal('0.30')
PARTICIPATION = Decimal('0.01')
HOLD = timedelta(minutes=30)
ENTRY_WINDOW = timedelta(minutes=60)
MAX_QUOTE_AGE = timedelta(minutes=5)
_EQUITY = re.compile(r'[A-Z][A-Z0-9.\-]{0,9}\Z')
_UP = r'\b(?:raises?|increases?|lifts?|upgrades?|raised|increased)\b'
_DOWN = r'\b(?:cuts?|lowers?|reduces?|downgrades?|lowered|reduced)\b'
_METRIC = r'\b(?:revenue|sales|earnings|eps|ebitda|profit|financial|full[ -]year|fiscal[ -]year)\b'
_GUIDANCE = r'\b(?:guidance|outlook|forecast)\b'
_AMBIGUOUS = re.compile(r'\b(?:may|might|could|expects? to|considers?|withdraws?|suspends?|rumou?r|denies)\b|\?', re.I)


def direction_for(event: dict[str, Any]) -> tuple[str | None, str]:
    """Accept only an issuer headline with an unambiguous explicit revision."""
    if event.get('source') != 'investor_relations' or event.get('status') != 'observed':
        return None, 'not_unambiguous_issuer_guidance'
    title = str(event.get('title') or '').lower()[:400]
    if (_AMBIGUOUS.search(title) or not re.search(_METRIC, title)
            or not re.search(_GUIDANCE, title)):
        return None, 'no_explicit_guidance_revision'
    # Both increase and decrease anywhere in the headline means mixed evidence.
    up, down = re.search(_UP, title), re.search(_DOWN, title)
    if bool(up) == bool(down):
        return None, 'mixed_or_no_revision'
    verb = up or down
    assert verb is not None
    # Require guidance to be the object of the revision, rather than e.g.
    # "raises dividend and reaffirms guidance" or "cuts jobs; outlook steady".
    following = title[verb.end():]
    matched = re.match(
        r'\s+(?:(?:its|the|prior|updated|annual|quarterly|full[ -]year|fiscal(?:[ -]year)?|'
        r'year|20\d{2}|q[1-4]|fy\s*20\d{2}|revenue|sales|earnings|eps|ebitda|profit|financial|'
        r'adjusted|net|per[ -]share|operating|cash[ -]flow|and|/|&)[\s,]+){0,10}'
        + _GUIDANCE,
        following,
    )
    if not matched or _AMBIGUOUS.search(title[:verb.start()]):
        return None, 'no_explicit_guidance_revision'
    return ('long', 'issuer_raises_guidance') if up else ('short', 'issuer_lowers_guidance')


def number(value: Any) -> Decimal | None:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return result if result.is_finite() and abs(result) <= 1_000_000_000 else None


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def equity_ticker(symbol: Any) -> bool:
    return isinstance(symbol, str) and bool(_EQUITY.fullmatch(symbol))


def entry_window(known_at: datetime) -> tuple[datetime, datetime]:
    market = market_session(known_at)
    opening, closing = as_utc(market['open_at']), as_utc(market['close_at'])
    if closing - max(known_at, opening) < HOLD + timedelta(minutes=10):
        opening = as_utc(market['next_open_at'])
        closing = as_utc(market_session(opening)['close_at'])
    after = max(known_at, opening)
    return after, min(after + ENTRY_WINDOW, closing - HOLD - timedelta(minutes=5))


def eligible_bars(raw: Iterable[dict], now: datetime, ticker: str) -> list[dict]:
    """Regular full minute bars, actually received, without duplicate versions."""
    session = market_session(now)
    if not session['is_open']:
        return []
    opening, closing = as_utc(session['open_at']), as_utc(session['close_at'])
    observed: dict[tuple[str, datetime], dict] = {}
    for bar in raw:
        try:
            if bar['ticker'] != ticker or not isinstance(bar['source'], str) or not bar['source']:
                continue
            start, end, received = (as_utc(bar[k]) for k in ('start', 'end', 'fetched_at'))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        price, volume = number(bar.get('close')), number(bar.get('volume'))
        if (not (opening <= start < end <= received <= now < closing and now - end <= MAX_QUOTE_AGE)
                or start.second or start.microsecond or end - start != timedelta(minutes=1)
                or price is None or price <= 0 or volume is None or volume < 0
                or bar.get('price_basis') != 'raw_unadjusted'):
            continue
        item = dict(bar, start=start, end=end, fetched_at=received, close=price, volume=volume,
                    price_quality='indicative_bar')
        key = (bar['source'], start)
        previous = observed.get(key)
        # No repricing to a later provider update. A conflicting same-receipt
        # duplicate invalidates that minute entirely instead of picking a side.
        if previous is None or received < previous['fetched_at']:
            observed[key] = item
        elif received == previous['fetched_at'] and (
            (price, volume) != (previous['close'], previous['volume'])
        ):
            previous['conflict'] = True
    return sorted((bar for bar in observed.values() if not bar.get('conflict')),
                  key=lambda bar: (bar['start'], bar['fetched_at'], bar['source']))


def entry_loan(raw: Iterable[dict], ticker: str, at: datetime, known_at: datetime) -> dict | None:
    # A newer explicit unknown/recall supersedes an older approved locate.
    rows = loan_updates(raw, ticker, known_at)
    if not rows:
        return None
    value = rows[-1]
    rating = number(value.get('annual_rate'))
    qty = value.get('available_shares')
    if (value['observed_at'] > at or value['valid_until'] < at
            or value.get('status') not in {'easy_to_borrow', 'hard_to_borrow_located'}
            or value.get('recalled') is True or rating is None or not 0 <= rating <= 5
            or type(qty) is not int or qty <= 0):
        return None
    return dict(value, annual_rate=rating)


def loan_updates(raw: Iterable[dict], ticker: str, known_at: datetime) -> list[dict]:
    rows = []
    for item in raw:
        if item.get('ticker') != ticker or not item.get('source') or not item.get('evidence_id'):
            continue
        try:
            at, until = as_utc(item['observed_at']), as_utc(item['valid_until'])
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        recalled = item.get('recalled') is True or item.get('status') == 'recalled'
        if at <= known_at and (until >= at or recalled):
            receipt = {key: item[key] for key in ('ticker', 'source', 'evidence_id', 'status', 'annual_rate',
                                                    'available_shares', 'loan_id') if key in item}
            rows.append(dict(receipt, observed_at=at, valid_until=until, recalled=recalled))
    return sorted(rows, key=lambda row: (row['observed_at'], str(row['evidence_id'])))


def transaction_price(bar: dict, buy: bool) -> Decimal:
    return (bar['close'] * (1 + SLIPPAGE if buy else 1 - SLIPPAGE)).quantize(Decimal('0.000001'))


def risk_capacity(direction: str, nav: Decimal, gross: Decimal, short: Decimal) -> Decimal:
    caps = (MAX_TRADE, MAX_GROSS - gross, nav * MAX_GROSS_WEIGHT - gross)
    if direction == 'short':
        caps += (nav * MAX_SINGLE_SHORT_WEIGHT, nav * MAX_SHORT_WEIGHT - short)
    return max(Decimal(0), min(caps))


def open_trade(direction: str, bar: dict, free_cash: Decimal, capacity: Decimal,
               loan: dict | None) -> dict | None:
    is_short = direction == 'short'
    if is_short and loan is None:
        return None
    price = transaction_price(bar, not is_short)
    unit_lock = price * (INITIAL_MARGIN + FEE_RATE if is_short else 1 + FEE_RATE)
    if price <= 0 or unit_lock <= 0:
        return None
    qty = min(int(capacity / max(price, bar['close'])), int(free_cash / unit_lock),
              int(bar['volume'] * PARTICIPATION))
    if is_short:
        qty = min(qty, loan['available_shares'])  # type: ignore[index]
    if qty <= 0:
        return None
    notional, fee = money(price * qty), money(price * qty * FEE_RATE)
    margin = money(notional * INITIAL_MARGIN) if is_short else Decimal(0)
    free_delta = -margin - fee if is_short else -notional - fee
    if free_cash + free_delta < 0:
        return None
    held = notional + margin if is_short else Decimal(0)
    return {'price': price, 'qty': qty, 'fee': fee, 'held': held, 'free_delta': free_delta}


def close_trade(trial: dict, bar: dict, borrow_cost: Decimal, dividend_cash: Decimal) -> dict | None:
    is_short = trial['direction'] == 'short'
    qty = trial['qty']
    price = transaction_price(bar, is_short)
    if price <= 0 or int(bar['volume'] * PARTICIPATION) < qty:
        return None
    exit_value, exit_fee = money(price * qty), money(price * qty * FEE_RATE)
    opening = money(trial['entry_price'] * qty)
    fees = trial['fees'] + exit_fee
    realized = (opening - exit_value if is_short else exit_value - opening) - fees - borrow_cost + dividend_cash
    free_delta = (trial['held_cash'] - exit_value if is_short else exit_value) - exit_fee - borrow_cost + dividend_cash
    return {'price': price, 'realized': realized, 'fee': exit_fee, 'free_delta': free_delta}


def required_cover(trial: dict, price: Decimal) -> bool:
    liability = price * trial['qty']
    return trial['direction'] == 'short' and trial['held_cash'] - liability < MAINTENANCE * liability
