"""Bounded, private indicative observations. No order endpoint or paid feed."""

from __future__ import annotations

import json
import math
import os
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

SYMBOLS = ("SPY", "QQQ", "NVDA")
DATA = "https://data.alpaca.markets"
CONTRACTS = "https://paper-api.alpaca.markets/v2/options/contracts"
NY = ZoneInfo("America/New_York")


def enabled():
    return os.getenv("PRIVATE_OPTION_RESEARCH", "").lower() == "true"


def number(value):
    try:
        val = float(value)
        return val if math.isfinite(val) and val >= 0 else None
    except (TypeError, ValueError):
        return None


def stamp(value):
    try:
        dt = datetime.fromisoformat(value)
        return dt.astimezone(UTC) if dt.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def select_contracts(records, symbol, spot, day):
    groups = {}
    for r in records:
        strike = number(r.get("strike_price"))
        if (
            r.get("underlying_symbol") != symbol
            or r.get("root_symbol") != symbol
            or not strike
            or r.get("type") not in {"call", "put"}
            or not r.get("symbol")
        ):
            continue
        try:
            expiry = date.fromisoformat(r["expiration_date"])
        except (KeyError, ValueError, TypeError):
            continue
        if day < expiry <= day + timedelta(days=14):
            groups.setdefault(expiry, []).append(r)
    selected = []
    for expiry in sorted(groups)[:2]:
        for side in ("call", "put"):
            side_rows = (r for r in groups[expiry] if r["type"] == side)
            selected.extend(
                sorted(
                    side_rows, key=lambda r: (abs(float(r["strike_price"]) - spot), r["symbol"])
                )[:3]
            )
    return selected


def observation(r, snapshot, received):
    quote = snapshot.get("latestQuote") or {}
    trade = snapshot.get("latestTrade") or {}
    stamp_q = stamp(quote.get("t"))
    age = (received - stamp_q).total_seconds() if stamp_q else None
    bid, ask = number(quote.get("bp")), number(quote.get("ap"))
    healthy = bid is not None and bid > 0 and ask is not None and ask >= bid
    quality = (
        "unavailable"
        if not healthy or age is None
        else "future"
        if age < 0
        else "stale"
        if age > 900
        else "indicative"
    )
    return {
        "contract": r["symbol"],
        "underlying": r["underlying_symbol"],
        "right": r["type"],
        "expiry": r["expiration_date"],
        "strike": number(r["strike_price"]),
        "provider_contract_id": r.get("id"),
        "root": r.get("root_symbol"),
        "multiplier": number(r.get("multiplier")),
        "bid": bid,
        "ask": ask,
        "bid_size": number(quote.get("bs")),
        "ask_size": number(quote.get("as")),
        "quote_at": quote.get("t"),
        "trade_at": trade.get("t"),
        "quality": quality,
        "iv": number(snapshot.get("impliedVolatility")),
        "greeks": snapshot.get("greeks") or None,
        "oi": number(r.get("open_interest")),
        "oi_as_of": r.get("open_interest_date"),
    }


async def collect(client, symbol, now):
    day = now.astimezone(NY).date()

    async def get(url, **params):
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    ref = (await get(f"{DATA}/v2/stocks/{symbol}/trades/latest", feed="iex")).get("trade") or {}
    spot, ref_at = number(ref.get("p")), stamp(ref.get("t"))
    if not spot or not ref_at or not timedelta(0) <= now - ref_at <= timedelta(minutes=15):
        return "no_fresh_reference", {}
    meta = await get(
        CONTRACTS,
        underlying_symbols=symbol,
        root_symbol=symbol,
        limit=1000,
        expiration_date_gte=day + timedelta(days=1),
        expiration_date_lte=day + timedelta(days=14),
        strike_price_gte=round(spot * 0.95, 2),
        strike_price_lte=round(spot * 1.05, 2),
    )
    if meta.get("next_page_token"):
        return "coverage_truncated", {}
    chosen = select_contracts(meta["option_contracts"], symbol, spot, day)
    if not chosen:
        return "no_contracts", {}
    snapshots = await get(
        f"{DATA}/v1beta1/options/snapshots",
        feed="indicative",
        symbols=",".join(r["symbol"] for r in chosen),
        limit=100,
    )
    received = datetime.now(UTC)
    rows = [observation(r, snapshots["snapshots"].get(r["symbol"]) or {}, received) for r in chosen]
    return (
        "observed" if all(r["quality"] == "indicative" for r in rows) else "partial",
        {
            "spot": spot,
            "spot_at": ref.get("t"),
            "feed": "indicative",
            "provider": "alpaca",
            "received_at": received.isoformat(),
            "contracts": rows,
        },
    )


async def sample_options(pool, now=None):
    if not enabled():
        return {"status": "disabled"}
    key, secret = os.getenv("ALPACA_API_KEY"), os.getenv("ALPACA_API_SECRET")
    if not key or not secret:
        return {"status": "credentials_missing"}
    from alpha_agent.paper.market_clock import market_session
    from alpha_agent.data.capacity import read_capacity

    now = now or datetime.now(UTC)
    if not market_session(now)["is_open"]:
        return {"status": "market_closed"}
    slot = now.replace(minute=(now.minute // 30) * 30, second=0, microsecond=0)
    existing = {
        r["symbol"]
        for r in await pool.fetch("SELECT symbol FROM research_option_sample WHERE slot=$1", slot)
    }
    if len(existing) == len(SYMBOLS):
        return {"status": "cached"}
    if not (await read_capacity(pool))["allow_writes"]:
        return {"status": "capacity_paused"}
    statuses = {}
    async with httpx.AsyncClient(
        headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}, timeout=5
    ) as client:
        for symbol in SYMBOLS:
            if symbol in existing:
                continue
            try:
                status, data = await collect(client, symbol, now)
            except httpx.HTTPStatusError as exc:
                status, data = f"provider_{exc.response.status_code}", {}
            except (httpx.RequestError, ValueError, KeyError, TypeError):
                status, data = "provider_unavailable", {}
            await pool.execute(
                "INSERT INTO research_option_sample VALUES ($1,$2,$3,$4,$5::jsonb) "
                "ON CONFLICT DO NOTHING",
                symbol,
                slot,
                datetime.now(UTC),
                status,
                json.dumps(data),
            )
            statuses[symbol] = status
    await pool.execute(
        "DELETE FROM research_option_sample WHERE slot < $1", now - timedelta(days=30)
    )
    return {"status": "checked", "symbols": statuses}


async def read_options(pool, symbol="NVDA", limit=1):
    rows = await pool.fetch(
        "SELECT received_at,status,sample FROM research_option_sample WHERE symbol=$1 "
        "ORDER BY slot DESC LIMIT $2",
        symbol,
        limit,
    )
    return {
        "status": (
            "disabled"
            if not enabled()
            else "credentials_missing"
            if not (os.getenv("ALPACA_API_KEY") and os.getenv("ALPACA_API_SECRET"))
            else "observed"
            if rows
            else "not_sampled"
        ),
        "symbol": symbol,
        "samples": [
            {
                "received_at": r["received_at"],
                "status": r["status"],
                "sample": json.loads(r["sample"]) if isinstance(r["sample"], str) else r["sample"],
            }
            for r in rows
        ],
    }
