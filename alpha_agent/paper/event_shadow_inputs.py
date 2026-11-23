"""Bounded read-only inputs for the equity event research tick."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from urllib.parse import quote

from alpha_agent.paper.intraday import fetch_bars
from alpha_agent.paper.market_clock import as_utc, market_session

MAX_TICKERS = 12


async def read_regular_bars(tickers: list[str], now: datetime) -> tuple[list[dict], list[str]]:
    """Existing equity data only: minutes, not two-sided quotes or live fills."""
    limiter = asyncio.Semaphore(2)
    evidence_floor = now.replace(second=0, microsecond=0)

    async def one(ticker: str) -> tuple[list[dict], str | None]:
        try:
            async with limiter:
                bars = await asyncio.wait_for(fetch_bars(ticker, now), timeout=8)
            # Only a small recent slice is eligible for the live tick.
            return [dict(bar, ticker=ticker) for bar in bars[-8:]], None
        except Exception:  # no provider exception body in persisted receipts
            return [], ticker

    if not market_session(evidence_floor)['is_open']:
        return [], []
    batches = await asyncio.gather(*(one(ticker) for ticker in tickers[:MAX_TICKERS]))
    return [bar for batch, _ in batches for bar in batch], [bad for _, bad in batches if bad is not None]


async def read_alpaca_borrow_status(client, tickers: list[str], now: datetime) -> list[dict]:
    """Optional authenticated GET only. Asset status is NOT a locate, quantity, or rate.

    The caller owns authorized client credentials. Status-only evidence must not
    be upgraded to a short fill; this adapter never guesses inventory or fees.
    """
    limiter = asyncio.Semaphore(2)
    session = market_session(now)
    if not session['is_open']:
        return []

    async def one(ticker: str) -> dict | None:
        async with limiter:
            response = await client.get(
                'https://paper-api.alpaca.markets/v2/assets/' + quote(ticker, safe=''), timeout=6,
            )
        if response.status_code != 200:
            return None
        data = response.json()
        if (data.get('symbol') != ticker or data.get('class') != 'us_equity'
                or not isinstance(data.get('id'), str)):
            return None
        status = data.get('borrow_status') if data.get('shortable') is True else 'not_shortable'
        observed = datetime.now(UTC)
        until = as_utc(session['close_at'])
        if observed >= until:
            return None
        return {'ticker': ticker, 'source': 'alpaca_paper_asset_status',
                'status': status or 'unavailable', 'evidence_id': f"{data['id']}:{observed.isoformat()}",
                'observed_at': observed, 'valid_until': until, 'recalled': False}

    rows = await asyncio.gather(*(one(ticker) for ticker in tickers[:MAX_TICKERS]), return_exceptions=True)
    return [row for row in rows if isinstance(row, dict)]
