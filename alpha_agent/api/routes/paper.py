"""GET/POST /api/paper/* — per-user paper-trading simulator.

All routes require auth via require_user. Account is auto-created on first
access (UPSERT pattern). Fill simulation runs in the daily cron, not here.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.auth.dependencies import require_user

router = APIRouter(prefix="/api/paper", tags=["paper"])

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


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/account", response_model=AccountResponse)
async def get_account(
    user_id: int = Depends(require_user),
) -> AccountResponse:
    pool = await get_db_pool()
    account = await _get_or_create_account(pool, user_id)
    account_id: int = account["id"]

    positions = await pool.fetch(
        "SELECT * FROM sim_position WHERE account_id = $1 AND qty > 0",
        account_id,
    )
    tickers = [r["ticker"] for r in positions]
    closes = await _current_closes(pool, tickers)

    total_unrealized = 0.0
    total_realized_pnl = 0.0
    pos_out: list[PositionOut] = []
    for p in positions:
        ticker = p["ticker"]
        current = closes.get(ticker)
        unr = ((current - p["avg_cost"]) * p["qty"]) if current is not None else 0.0
        unr_pct = ((current - p["avg_cost"]) / p["avg_cost"] * 100.0) if current and p["avg_cost"] else 0.0
        total_unrealized += unr
        total_realized_pnl += p["realized_pnl"]
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
        "SELECT COUNT(*) FROM sim_order WHERE account_id = $1 AND status = 'pending'",
        account_id,
    ) or 0

    return AccountResponse(
        account_id=account_id,
        cash=cash,
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
    account = await _get_or_create_account(pool, user_id)
    account_id: int = account["id"]
    today = date.today()

    order_id: int = await pool.fetchval(
        """
        INSERT INTO sim_order
            (account_id, ticker, side, order_type, qty, limit_price, signal_date)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING id
        """,
        account_id, body.ticker, body.side, body.order_type,
        body.qty, body.limit_price, today,
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
        signal_date=today.isoformat(),
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

    valid_statuses = {"pending", "filled", "expired", "cancelled", "all"}
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"status must be one of {valid_statuses}")

    if status == "all":
        rows = await pool.fetch(
            "SELECT * FROM sim_order WHERE account_id = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            account_id, min(limit, 200), offset,
        )
        total = await pool.fetchval(
            "SELECT COUNT(*) FROM sim_order WHERE account_id = $1", account_id
        ) or 0
    else:
        rows = await pool.fetch(
            "SELECT * FROM sim_order WHERE account_id = $1 AND status = $2 ORDER BY created_at DESC LIMIT $3 OFFSET $4",
            account_id, status, min(limit, 200), offset,
        )
        total = await pool.fetchval(
            "SELECT COUNT(*) FROM sim_order WHERE account_id = $1 AND status = $2",
            account_id, status,
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

    order = await pool.fetchrow(
        "SELECT id, account_id, status FROM sim_order WHERE id = $1", order_id
    )
    if order is None or order["account_id"] != account_id:
        raise HTTPException(status_code=404, detail="order not found")
    if order["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"cannot cancel order with status '{order['status']}'")

    await pool.execute(
        "UPDATE sim_order SET status = 'cancelled' WHERE id = $1", order_id
    )
    return Response(status_code=204)


@router.get("/equity-curve", response_model=EquityCurveResponse)
async def equity_curve(
    user_id: int = Depends(require_user),
) -> EquityCurveResponse:
    pool = await get_db_pool()
    account = await _get_or_create_account(pool, user_id)
    account_id: int = account["id"]

    rows = await pool.fetch(
        "SELECT as_of_date, portfolio_value, benchmark_close FROM sim_equity_daily "
        "WHERE account_id = $1 ORDER BY as_of_date ASC",
        account_id,
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
    account = await _get_or_create_account(pool, user_id)
    account_id: int = account["id"]
    initial_cash: float = account["initial_cash"]

    # Mark all active positions qty=0, keep rows for audit
    await pool.execute(
        "UPDATE sim_position SET qty = 0, updated_at = now() WHERE account_id = $1 AND qty > 0",
        account_id,
    )
    # Cancel all pending orders
    await pool.execute(
        "UPDATE sim_order SET status = 'cancelled' WHERE account_id = $1 AND status = 'pending'",
        account_id,
    )
    # Restore cash and bump reset_count
    new_reset_count = (account["reset_count"] or 0) + 1
    await pool.execute(
        "UPDATE sim_account SET cash = $1, reset_count = $2, reset_at = now() WHERE id = $3",
        initial_cash, new_reset_count, account_id,
    )
    return ResetResponse(
        reset_count=new_reset_count,
        cash=initial_cash,
        message="账户已重置",
    )
