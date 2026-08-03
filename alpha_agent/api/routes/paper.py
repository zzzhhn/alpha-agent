"""GET/POST /api/paper/* — per-user paper-trading simulator.

All routes require auth via require_user. Account is auto-created on first
access (UPSERT pattern). Fill simulation runs in the daily cron, not here.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, date, datetime
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.dependencies import require_user

router = APIRouter(prefix="/api/paper", tags=["paper"])
PAPER_FEE_BPS = 10.0

# ── Pydantic models ──────────────────────────────────────────────────────────

class PositionOut(BaseModel):
    ticker: str
    qty: int
    avg_cost: float
    current_price: float | None
    unrealized_pnl: float
    unrealized_pct: float


class AccountResponse(BaseModel):
    account_id: int
    cash: float
    reserved_cash: float
    available_cash: float
    initial_cash: float
    portfolio_value: float
    total_return_pct: float
    unrealized_pnl: float
    realized_pnl: float
    positions: list[PositionOut]
    pending_orders: int
    reset_count: int


class PlaceOrderRequest(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=10)
    side: str = Field(..., pattern="^(buy|sell)$")
    order_type: str = Field(..., pattern="^(market|limit)$")
    qty: int = Field(..., gt=0)
    limit_price: float | None = None
    # Pick attribution: set automatically when placed from a pick's inline
    # drawer; left null for manual /paper orders. Both null or both set.
    pick_date: date | None = None
    pick_ticker: str | None = Field(default=None, max_length=10)
    pick_run_id: int | None = Field(default=None, gt=0)


class OrderResponse(BaseModel):
    order_id: int
    status: str
    signal_date: str
    message: str


class OrderOut(BaseModel):
    id: int
    ticker: str
    side: str
    order_type: str
    qty: int
    limit_price: float | None
    signal_date: str
    fill_date: str | None
    fill_price: float | None
    status: str
    fail_reason: str | None = None
    pick_date: str | None = None
    pick_ticker: str | None = None
    source_run_id: int | None = None
    source_policy_id: str | None = None
    source_payload_hash: str | None = None
    reserved_notional: float = 0.0
    fee_bps: float = 0.0
    transaction_cost: float = 0.0
    cohort_id: int = 0


class OrderListResponse(BaseModel):
    orders: list[OrderOut]
    total: int


class EquityPoint(BaseModel):
    date: str
    portfolio_value: float
    benchmark_index: float


class EquityCurveResponse(BaseModel):
    series: list[EquityPoint]
    base_date: str | None


class ResetResponse(BaseModel):
    reset_count: int
    cash: float
    message: str


class TickerAttribution(BaseModel):
    ticker: str
    realized_pnl: float
    unrealized_pnl: float
    pick_linked_trades: int
    self_directed_trades: int
    latest_pick_date: str | None = None
    source_type: str = Field(pattern="^(pick|manual|mixed)$")


class AttributionResponse(BaseModel):
    tickers: list[TickerAttribution]


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _get_or_create_account(pool: Any, user_id: int) -> dict[str, Any]:
    """Return the sim_account row for user_id, creating it if absent."""
    row = await pool.fetchrow(
        "SELECT * FROM sim_account WHERE user_id = $1", user_id
    )
    if row is None:
        row = await pool.fetchrow(
            "INSERT INTO sim_account (user_id) VALUES ($1) RETURNING *", user_id
        )
    if row is None:
        raise HTTPException(status_code=500, detail="failed to create sim account")
    return dict(row)


async def _current_closes(pool: Any, tickers: list[str]) -> dict[str, float]:
    """Latest daily close for each ticker from daily_prices."""
    if not tickers:
        return {}
    rows = await pool.fetch(
        """
        SELECT DISTINCT ON (ticker) ticker, close
        FROM daily_prices
        WHERE ticker = ANY($1::text[])
        ORDER BY ticker, date DESC
        """,
        tickers,
    )
    return {r["ticker"]: r["close"] for r in rows}


def _is_en_locale() -> bool:
    return os.environ.get("LOCALE", "zh") == "en"


def _insufficient_cash_message(ticker: str, est_cost: float, cash: float) -> str:
    return (
        f"Insufficient cash: buying {ticker} costs an estimated ${est_cost:,.2f}, "
        f"but available cash is ${cash:,.2f}"
        if _is_en_locale()
        else f"现金不足：买入 {ticker} 预计需要 ${est_cost:,.2f}，可用现金仅 ${cash:,.2f}"
    )


def _insufficient_position_message(ticker: str, qty: int, held_qty: int) -> str:
    return (
        f"Insufficient position: you hold {held_qty} shares of {ticker}, cannot sell {qty}"
        if _is_en_locale()
        else f"持仓不足：{ticker} 现持有 {held_qty} 股，无法卖出 {qty} 股"
    )


def _price_unavailable_message(ticker: str) -> str:
    return (
        f"No trusted close is available for {ticker}; the order was not reserved"
        if _is_en_locale()
        else f"{ticker} 暂无可信收盘价，无法预留资金，订单未提交"
    )


def _canonical_payload_hash(payload: Any) -> str:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            payload = payload
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _resolve_pick_provenance(
    conn: Any,
    body: PlaceOrderRequest,
) -> tuple[int | None, str | None, str | None]:
    """Verify a pick-linked order against the immutable product ledger.

    The client identifies the run; the server derives policy and payload hash
    from the ledger so neither can be forged by a browser request.
    """
    supplied = (body.pick_date, body.pick_ticker, body.pick_run_id)
    if not any(value is not None for value in supplied):
        return None, None, None
    if not all(value is not None for value in supplied):
        raise HTTPException(
            status_code=400,
            detail="pick_date, pick_ticker and pick_run_id must be set together",
        )
    if body.pick_ticker.upper() != body.ticker.upper():
        raise HTTPException(status_code=400, detail="pick_ticker must match ticker")
    row = await conn.fetchrow(
        """
        SELECT rr.id, rr.scheduled_for_date, rr.weight_policy_id,
               rs.user_visible_payload_json
        FROM research_run rr
        JOIN rating_snapshot rs ON rs.run_id = rr.id
        WHERE rr.id=$1 AND rr.status='complete' AND rs.ticker=$2
          AND rs.eligible=true
        """,
        body.pick_run_id,
        body.ticker.upper(),
    )
    if row is None or row["scheduled_for_date"] != body.pick_date:
        raise HTTPException(status_code=400, detail="pick provenance is not canonical")
    return (
        int(row["id"]),
        row["weight_policy_id"],
        _canonical_payload_hash(row["user_visible_payload_json"]),
    )


@lru_cache(maxsize=1)
def _xnys_calendar():
    # Keep the pandas-backed calendar import off the application startup path.
    # It is only needed when an order is placed, and is cached thereafter.
    import exchange_calendars as xcals

    return xcals.get_calendar("XNYS")


def _paper_signal_session(now: datetime | None = None) -> date:
    """Map an order instant to the latest applicable US market session.

    Fills select the first daily close strictly after signal_date. Using the
    server's UTC calendar date after the US close can therefore skip the next
    US session. The New York date, rolled back across weekends and exchange
    holidays, preserves the intended D+1-session fill.
    """
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    new_york_date = instant.astimezone(ZoneInfo("America/New_York")).date()
    return _xnys_calendar().date_to_session(
        new_york_date, direction="previous"
    ).date()


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/account", response_model=AccountResponse)
async def get_account(
    user_id: int = Depends(require_user),
) -> AccountResponse:
    pool = await get_db_pool()
    account = await _get_or_create_account(pool, user_id)
    account_id: int = account["id"]
    cohort_id = int(account["reset_count"] or 0)

    position_rows = await pool.fetch(
        "SELECT * FROM sim_position WHERE account_id = $1 AND cohort_id = $2",
        account_id,
        cohort_id,
    )
    positions = [row for row in position_rows if row["qty"] > 0]
    tickers = [r["ticker"] for r in positions]
    closes = await _current_closes(pool, tickers)

    total_unrealized = 0.0
    # Closed rows remain the durable realized-PnL ledger. Fetching all rows in
    # the same indexed query avoids both a correctness hole and another DB trip.
    total_realized_pnl = sum(row["realized_pnl"] or 0.0 for row in position_rows)
    pos_out: list[PositionOut] = []
    for p in positions:
        ticker = p["ticker"]
        current = closes.get(ticker)
        unr = ((current - p["avg_cost"]) * p["qty"]) if current is not None else 0.0
        unr_pct = ((current - p["avg_cost"]) / p["avg_cost"] * 100.0) if current and p["avg_cost"] else 0.0
        total_unrealized += unr
        pos_out.append(PositionOut(
            ticker=ticker,
            qty=p["qty"],
            avg_cost=p["avg_cost"],
            current_price=current,
            unrealized_pnl=unr,
            unrealized_pct=unr_pct,
        ))

    position_mkt_value = sum(
        closes.get(p["ticker"], p["avg_cost"]) * p["qty"] for p in positions
    )
    cash = account["cash"]
    portfolio_value = cash + position_mkt_value
    initial_cash = account["initial_cash"]
    total_return_pct = (portfolio_value - initial_cash) / initial_cash * 100.0

    pending_count = await pool.fetchval(
        "SELECT COUNT(*) FROM sim_order "
        "WHERE account_id = $1 AND cohort_id = $2 AND status = 'pending'",
        account_id,
        cohort_id,
    ) or 0
    reserved_cash = await pool.fetchval(
        "SELECT COALESCE(SUM(reserved_notional), 0) FROM sim_order "
        "WHERE account_id=$1 AND cohort_id=$2 AND side='buy' AND status='pending'",
        account_id,
        cohort_id,
    ) or 0.0

    return AccountResponse(
        account_id=account_id,
        cash=cash,
        reserved_cash=float(reserved_cash),
        available_cash=max(0.0, float(cash) - float(reserved_cash)),
        initial_cash=initial_cash,
        portfolio_value=portfolio_value,
        total_return_pct=total_return_pct,
        unrealized_pnl=total_unrealized,
        realized_pnl=total_realized_pnl,
        positions=pos_out,
        pending_orders=int(pending_count),
        reset_count=account["reset_count"],
    )


@router.post("/order", response_model=OrderResponse, status_code=201)
async def place_order(
    body: PlaceOrderRequest,
    user_id: int = Depends(require_user),
) -> OrderResponse:
    if body.order_type == "limit" and body.limit_price is None:
        raise HTTPException(status_code=400, detail="limit_price required for limit orders")
    if body.order_type == "limit" and body.limit_price is not None and body.limit_price <= 0:
        raise HTTPException(status_code=400, detail="limit_price must be positive")

    pool = await get_db_pool()
    signal_session = _paper_signal_session()
    ticker = body.ticker.strip().upper()

    async with pool.acquire() as conn:
        async with conn.transaction():
            account = await _get_or_create_account(conn, user_id)
            account_id = int(account["id"])
            account = dict(await conn.fetchrow(
                "SELECT * FROM sim_account WHERE id=$1 FOR UPDATE",
                account_id,
            ))
            cohort_id = int(account["reset_count"] or 0)
            source_run_id, source_policy_id, source_payload_hash = (
                await _resolve_pick_provenance(conn, body)
            )

            reserved_notional = 0.0
            if body.side == "buy":
                closes = await _current_closes(conn, [ticker])
                reference_price = (
                    body.limit_price
                    if body.order_type == "limit"
                    else closes.get(ticker)
                )
                if reference_price is None:
                    raise HTTPException(
                        status_code=400,
                        detail=_price_unavailable_message(ticker),
                    )
                est_notional = float(reference_price) * body.qty
                reserved_notional = est_notional * (1.0 + PAPER_FEE_BPS / 10000.0)
                already_reserved = await conn.fetchval(
                    "SELECT COALESCE(SUM(reserved_notional), 0) FROM sim_order "
                    "WHERE account_id=$1 AND cohort_id=$2 AND side='buy' "
                    "AND status='pending'",
                    account_id,
                    cohort_id,
                ) or 0.0
                available_cash = float(account["cash"]) - float(already_reserved)
                if reserved_notional > available_cash:
                    raise HTTPException(
                        status_code=400,
                        detail=_insufficient_cash_message(
                            ticker,
                            reserved_notional,
                            available_cash,
                        ),
                    )
            else:
                position = await conn.fetchrow(
                    "SELECT qty FROM sim_position "
                    "WHERE account_id=$1 AND cohort_id=$2 AND ticker=$3 FOR UPDATE",
                    account_id,
                    cohort_id,
                    ticker,
                )
                held_qty = int(position["qty"]) if position else 0
                pending_sell = await conn.fetchval(
                    "SELECT COALESCE(SUM(qty), 0) FROM sim_order "
                    "WHERE account_id=$1 AND cohort_id=$2 AND ticker=$3 "
                    "AND side='sell' AND status='pending'",
                    account_id,
                    cohort_id,
                    ticker,
                ) or 0
                available_qty = max(0, held_qty - int(pending_sell))
                if available_qty < body.qty:
                    raise HTTPException(
                        status_code=400,
                        detail=_insufficient_position_message(
                            ticker,
                            body.qty,
                            available_qty,
                        ),
                    )

            order_id: int = await conn.fetchval(
                """
                INSERT INTO sim_order
                    (account_id, ticker, side, order_type, qty, limit_price,
                     signal_date, pick_date, pick_ticker, source_run_id,
                     source_policy_id, source_payload_hash, reserved_notional,
                     fee_bps, cohort_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                        $12, $13, $14, $15)
                RETURNING id
                """,
                account_id,
                ticker,
                body.side,
                body.order_type,
                body.qty,
                body.limit_price,
                signal_session,
                body.pick_date,
                body.pick_ticker.upper() if body.pick_ticker else None,
                source_run_id,
                source_policy_id,
                source_payload_hash,
                reserved_notional,
                PAPER_FEE_BPS,
                cohort_id,
            )

    if body.order_type == "limit" and body.limit_price is not None:
        message = (
            f"限价单已提交，将在收盘价穿越 ${body.limit_price:.2f} 时成交（最多 5 个交易日）"
            if os.environ.get("LOCALE", "zh") != "en"
            else f"Limit order submitted; fills when close crosses ${body.limit_price:.2f} (up to 5 trading days)"
        )
    else:
        message = "市价单已提交，将于下一交易日收盘后成交" if os.environ.get("LOCALE", "zh") != "en" \
            else "Market order submitted; fills at next trading day close"

    return OrderResponse(
        order_id=order_id,
        status="pending",
        signal_date=signal_session.isoformat(),
        message=message,
    )


@router.get("/orders", response_model=OrderListResponse)
async def list_orders(
    status: str = "all",
    limit: int = 50,
    offset: int = 0,
    user_id: int = Depends(require_user),
) -> OrderListResponse:
    pool = await get_db_pool()
    account = await _get_or_create_account(pool, user_id)
    account_id: int = account["id"]
    cohort_id = int(account["reset_count"] or 0)

    valid_statuses = {"pending", "filled", "expired", "cancelled", "failed", "all"}
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"status must be one of {valid_statuses}")

    if status == "all":
        rows = await pool.fetch(
            "SELECT * FROM sim_order WHERE account_id=$1 AND cohort_id=$2 "
            "ORDER BY created_at DESC LIMIT $3 OFFSET $4",
            account_id, cohort_id, min(limit, 200), offset,
        )
        total = await pool.fetchval(
            "SELECT COUNT(*) FROM sim_order WHERE account_id=$1 AND cohort_id=$2",
            account_id, cohort_id,
        ) or 0
    else:
        rows = await pool.fetch(
            "SELECT * FROM sim_order WHERE account_id=$1 AND cohort_id=$2 "
            "AND status=$3 ORDER BY created_at DESC LIMIT $4 OFFSET $5",
            account_id, cohort_id, status, min(limit, 200), offset,
        )
        total = await pool.fetchval(
            "SELECT COUNT(*) FROM sim_order "
            "WHERE account_id=$1 AND cohort_id=$2 AND status=$3",
            account_id, cohort_id, status,
        ) or 0

    orders = [
        OrderOut(
            id=r["id"],
            ticker=r["ticker"],
            side=r["side"],
            order_type=r["order_type"],
            qty=r["qty"],
            limit_price=r["limit_price"],
            signal_date=r["signal_date"].isoformat(),
            fill_date=r["fill_date"].isoformat() if r["fill_date"] else None,
            fill_price=r["fill_price"],
            status=r["status"],
            fail_reason=r["fail_reason"],
            pick_date=r["pick_date"].isoformat() if r["pick_date"] else None,
            pick_ticker=r["pick_ticker"],
            source_run_id=r["source_run_id"],
            source_policy_id=r["source_policy_id"],
            source_payload_hash=r["source_payload_hash"],
            reserved_notional=float(r["reserved_notional"] or 0.0),
            fee_bps=float(r["fee_bps"] or 0.0),
            transaction_cost=float(r["transaction_cost"] or 0.0),
            cohort_id=int(r["cohort_id"] or 0),
        )
        for r in rows
    ]
    return OrderListResponse(orders=orders, total=int(total))


@router.delete("/order/{order_id}", status_code=204)
async def cancel_order(
    order_id: int,
    user_id: int = Depends(require_user),
) -> Response:
    pool = await get_db_pool()
    account = await _get_or_create_account(pool, user_id)
    account_id: int = account["id"]
    cohort_id = int(account["reset_count"] or 0)

    cancelled = await pool.fetchrow(
        "UPDATE sim_order SET status = 'cancelled' "
        "WHERE id=$1 AND account_id=$2 AND cohort_id=$3 "
        "AND status='pending' RETURNING id",
        order_id,
        account_id,
        cohort_id,
    )
    if cancelled is not None:
        return Response(status_code=204)

    order = await pool.fetchrow(
        "SELECT status FROM sim_order "
        "WHERE id=$1 AND account_id=$2 AND cohort_id=$3",
        order_id,
        account_id,
        cohort_id,
    )
    if order is None:
        raise HTTPException(status_code=404, detail="order not found")
    raise HTTPException(
        status_code=400,
        detail=f"cannot cancel order with status '{order['status']}'",
    )


@router.get("/equity-curve", response_model=EquityCurveResponse)
async def equity_curve(
    user_id: int = Depends(require_user),
) -> EquityCurveResponse:
    pool = await get_db_pool()
    account = await _get_or_create_account(pool, user_id)
    account_id: int = account["id"]
    cohort_id = int(account["reset_count"] or 0)

    rows = await pool.fetch(
        "SELECT as_of_date, portfolio_value, benchmark_close FROM sim_equity_daily "
        "WHERE account_id=$1 AND cohort_id=$2 ORDER BY as_of_date ASC",
        account_id,
        cohort_id,
    )
    if not rows:
        return EquityCurveResponse(series=[], base_date=None)

    base_bench = rows[0]["benchmark_close"] or 1.0
    series = [
        EquityPoint(
            date=r["as_of_date"].isoformat(),
            portfolio_value=r["portfolio_value"],
            benchmark_index=(
                (r["benchmark_close"] / base_bench * 100.0)
                if r["benchmark_close"] and base_bench
                else 100.0
            ),
        )
        for r in rows
    ]
    return EquityCurveResponse(series=series, base_date=rows[0]["as_of_date"].isoformat())


@router.post("/reset", response_model=ResetResponse)
async def reset_account(
    user_id: int = Depends(require_user),
) -> ResetResponse:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            account = await _get_or_create_account(conn, user_id)
            account_id = int(account["id"])
            account = dict(await conn.fetchrow(
                "SELECT * FROM sim_account WHERE id=$1 FOR UPDATE",
                account_id,
            ))
            initial_cash = float(account["initial_cash"])
            old_cohort = int(account["reset_count"] or 0)
            await conn.execute(
                "UPDATE sim_order SET status='cancelled' "
                "WHERE account_id=$1 AND cohort_id=$2 AND status='pending'",
                account_id,
                old_cohort,
            )
            # Positions and equity stay attached to the old cohort for audit;
            # the increment creates an empty current book without rewriting it.
            new_reset_count = old_cohort + 1
            await conn.execute(
                "UPDATE sim_account SET cash=$1, reset_count=$2, reset_at=now() "
                "WHERE id=$3",
                initial_cash,
                new_reset_count,
                account_id,
            )
    return ResetResponse(
        reset_count=new_reset_count,
        cash=initial_cash,
        message="账户已重置",
    )


@router.get("/attribution", response_model=AttributionResponse)
async def get_attribution(
    user_id: int = Depends(require_user),
) -> AttributionResponse:
    """Per-ticker PnL plus the observable source mix of filled orders.

    PnL remains ticker-level because sim_position stores one blended cost basis.
    `source_type` therefore describes provenance, not a fabricated PnL split.
    """
    pool = await get_db_pool()
    account = await _get_or_create_account(pool, user_id)
    account_id: int = account["id"]
    cohort_id = int(account["reset_count"] or 0)

    positions = await pool.fetch(
        "SELECT ticker, qty, avg_cost, realized_pnl FROM sim_position "
        "WHERE account_id=$1 AND cohort_id=$2",
        account_id,
        cohort_id,
    )
    trade_counts = await pool.fetch(
        """
        SELECT ticker,
               COUNT(*) FILTER (WHERE pick_date IS NOT NULL) AS pick_linked,
               COUNT(*) FILTER (WHERE pick_date IS NULL) AS self_directed,
               MAX(pick_date) AS latest_pick_date
        FROM sim_order
        WHERE account_id=$1 AND cohort_id=$2 AND status='filled'
        GROUP BY ticker
        """,
        account_id,
        cohort_id,
    )

    pos_by_ticker = {p["ticker"]: p for p in positions}
    counts_by_ticker = {r["ticker"]: r for r in trade_counts}
    all_tickers = set(pos_by_ticker) | set(counts_by_ticker)

    live_tickers = [t for t, p in pos_by_ticker.items() if p["qty"] > 0]
    closes = await _current_closes(pool, live_tickers)

    rows: list[TickerAttribution] = []
    for ticker in sorted(all_tickers):
        pos = pos_by_ticker.get(ticker)
        realized = pos["realized_pnl"] if pos else 0.0
        unrealized = 0.0
        if pos and pos["qty"] > 0:
            current = closes.get(ticker)
            if current is not None:
                unrealized = (current - pos["avg_cost"]) * pos["qty"]
        counts = counts_by_ticker.get(ticker)
        pick_linked = int(counts["pick_linked"]) if counts else 0
        self_directed = int(counts["self_directed"]) if counts else 0
        source_type = (
            "mixed"
            if pick_linked and self_directed
            else "pick"
            if pick_linked
            else "manual"
        )
        rows.append(TickerAttribution(
            ticker=ticker,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
            pick_linked_trades=pick_linked,
            self_directed_trades=self_directed,
            latest_pick_date=(
                counts["latest_pick_date"].isoformat()
                if counts and counts["latest_pick_date"]
                else None
            ),
            source_type=source_type,
        ))
    return AttributionResponse(tickers=rows)
