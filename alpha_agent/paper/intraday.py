"""Bounded raw minute quotes and deterministic next-bar paper fills.

No database writes or daily-close fallback. A fill is an explicit simplified
simulation, not evidence of broker execution, liquidity or order-book access.
"""
from __future__ import annotations

import asyncio
import math
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Iterable

from alpha_agent.paper.market_clock import as_utc, market_session

EXECUTION_MODEL = "intraday_next_bar_v1"
SOURCE = "yfinance:history:1m"
MAX_BARS = 390


def _fetch_history(ticker: str):
    import yfinance as yf

    return yf.Ticker(ticker).history(
        period="1d", interval="1m", auto_adjust=False, back_adjust=False,
        actions=True, prepost=False, timeout=10, raise_errors=True,
    )


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


async def fetch_bars(ticker: str, now: datetime | str | None = None) -> list[dict]:
    """Fetch at most one regular session of raw 1m bars for one symbol.

    ``now`` selects the session and as-of cutoff, not a historical provider
    query. Missing/stale data returns []; provider errors propagate so callers
    can display their own bounded retry/error state. No cache or persistence.
    Corporate-action metadata is copied to every bar in the affected session
    to avoid losing an event that is reported only on its opening minute.
    """
    symbol = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.^=-]{0,19}", symbol):
        raise ValueError("invalid ticker")
    instant = as_utc(now) if now is not None else datetime.now(UTC)
    session = market_session(instant)
    opening, closing = as_utc(session["open_at"]), as_utc(session["close_at"])
    frame = await asyncio.to_thread(_fetch_history, symbol)
    fetched_at = datetime.now(UTC).isoformat()
    if frame is None or frame.empty:
        return []

    selected = []
    for timestamp, row in frame.sort_index().iterrows():
        start = as_utc(timestamp.to_pydatetime())
        if opening <= start < closing and start <= instant:
            selected.append((start, row))
    selected = selected[:MAX_BARS]
    action_known = all(column in frame.columns for column in ("Dividends", "Stock Splits"))
    actions = []
    for start, row in selected:
        dividend = _finite(row.get("Dividends"))
        split = _finite(row.get("Stock Splits"))
        if dividend not in (None, 0.0) or split not in (None, 0.0):
            actions.append({"at": start.isoformat(), "dividends": dividend, "stock_splits": split})
    result = []
    for start, row in selected:
        result.append({
            "start": start.isoformat(), "end": (start + timedelta(minutes=1)).isoformat(),
            "open": _finite(row.get("Open")), "high": _finite(row.get("High")),
            "low": _finite(row.get("Low")), "close": _finite(row.get("Close")),
            "volume": _finite(row.get("Volume")), "source": SOURCE,
            "fetched_at": fetched_at, "price_basis": "raw_unadjusted",
            "dividends": _finite(row.get("Dividends")),
            "stock_splits": _finite(row.get("Stock Splits")),
            "corporate_actions": actions, "corporate_actions_known": action_known,
        })
    return result


def select_fill(
    side: str,
    accepted_at: datetime | str,
    expires_at: datetime | str,
    bars: Iterable[dict],
    now: datetime | str,
    cancel_requested_at: datetime | str | None = None,
    slippage_bps: float = 5,
) -> dict:
    """Select the earliest eligible minute, never a more favorable later bar.

    A complete bar must end by now AND have been fetched after its end and
    before now. Start is strictly after acceptance, end no later than expiry
    or that same session's close. Cancellation at/before bar.start wins;
    later cancellation cannot erase that simulated execution. Without data,
    a cancellation after the first possible minute awaits reconciliation
    until expiry. Invalid earliest prices/actions block, not skip forward.

    ``filled_at`` is the simulated opening execution time; ``confirmed_at``
    records when this function can actually confirm it. Fees belong to the
    caller's quantity/ledger logic, separate from adverse-price slippage.
    """
    accepted, expires, instant = as_utc(accepted_at), as_utc(expires_at), as_utc(now)
    cancel = as_utc(cancel_requested_at) if cancel_requested_at is not None else None
    if side not in {"buy", "sell"}:
        raise ValueError("side must be buy or sell")
    slippage = _finite(slippage_bps)
    if slippage is None or not 0 <= slippage < 10000:
        raise ValueError("slippage_bps must be finite and between 0 and 10000")
    if expires <= accepted or instant < accepted:
        raise ValueError("expiry must follow acceptance and now must not precede acceptance")
    if cancel is not None and (cancel < accepted or cancel > instant):
        raise ValueError("cancel_requested_at must be between acceptance and now")
    session = market_session(accepted)
    base = {"execution_model": EXECUTION_MODEL, "session_date": session["session_date"]}
    deadline = min(expires, as_utc(session["close_at"]))

    def unresolved(reason: str, evidence: dict | None = None) -> dict:
        return {
            **base, "status": "expired" if instant >= deadline else "pending",
            "reason": reason, **({"bar": evidence} if evidence is not None else {}),
        }

    if not session["is_open"]:
        return {**base, "status": "expired", "reason": "accepted_outside_regular_session"}
    first_possible = accepted.replace(second=0, microsecond=0) + timedelta(minutes=1)
    if cancel is not None and cancel <= first_possible and cancel <= deadline:
        return {**base, "status": "cancelled", "reason": "cancelled_before_eligible_bar"}

    candidates = []
    for bar in bars:
        try:
            start, end = as_utc(bar["start"]), as_utc(bar["end"])
            fetched = as_utc(bar["fetched_at"])
        except (KeyError, TypeError, ValueError):
            continue
        if (
            accepted < start and start.second == 0 and start.microsecond == 0
            and end == start + timedelta(minutes=1) and end <= deadline
            and start >= as_utc(session["open_at"])
            and end <= instant and fetched <= instant
        ):
            candidates.append((start, end, fetched, bar))
    if not candidates:
        return unresolved("cancel_awaiting_market_data" if cancel else "awaiting_complete_bar")
    start, end, fetched, bar = min(candidates, key=lambda item: item[0])
    if cancel is not None and cancel <= start:
        return {**base, "status": "cancelled", "reason": "cancelled_before_eligible_bar"}
    if fetched < end:
        return unresolved("awaiting_complete_bar", bar)
    prices = [_finite(bar.get(key)) for key in ("open", "high", "low", "close")]
    if any(price is None or price <= 0 for price in prices):
        return unresolved("invalid_ohlc", bar)
    opening, high, low, closing = prices
    if low > min(opening, closing) or high < max(opening, closing) or low > high:
        return unresolved("invalid_ohlc_range", bar)
    if not bar.get("source") or bar.get("price_basis", "raw_unadjusted") != "raw_unadjusted":
        return unresolved("raw_price_evidence_required", bar)
    dividend, split = _finite(bar.get("dividends", 0)), _finite(bar.get("stock_splits", 0))
    if (
        dividend is None or split is None or dividend != 0 or split != 0
        or bar.get("corporate_actions") or bar.get("corporate_actions_known") is False
    ):
        return unresolved("corporate_action_requires_reconciliation", bar)
    fill_price = opening * (1 + (1 if side == "buy" else -1) * slippage / 10000)
    return {
        **base, "status": "filled", "reason": "earliest_complete_raw_bar",
        "reference_price": opening, "fill_price": fill_price, "slippage_bps": slippage,
        "filled_at": start.isoformat(), "confirmed_at": instant.isoformat(), "bar": dict(bar),
    }
