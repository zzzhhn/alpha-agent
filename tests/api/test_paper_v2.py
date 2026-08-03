"""Paper trading V2 P0 backend: order validation, fill-time cash re-check,
pick attribution round-trip, and the /api/paper/attribution aggregate.

Uses the real applied_db (not mocked) because validation queries
daily_prices/sim_position and the attribution endpoint does GROUP BY.
"""
from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta

import asyncpg
import pytest
from jose import jwt

from alpha_agent.api.routes.paper import _paper_signal_session

_SECRET = "test-secret-not-real-0123456789"


@pytest.mark.parametrize(
    ("instant", "expected"),
    [
        # 20:30 New York is already the next UTC date. The signal session must
        # remain Thursday so Friday is still the D+1 fill candidate.
        (datetime(2026, 7, 10, 0, 30, tzinfo=UTC), date(2026, 7, 9)),
        # Weekend rolls back to the latest exchange session.
        (datetime(2026, 7, 12, 12, 0, tzinfo=UTC), date(2026, 7, 10)),
        # 2026-07-03 is the observed Independence Day market holiday.
        (datetime(2026, 7, 3, 16, 0, tzinfo=UTC), date(2026, 7, 2)),
    ],
)
def test_paper_signal_session_uses_new_york_exchange_calendar(instant, expected):
    assert _paper_signal_session(instant) == expected


def _auth(user_id: int) -> dict:
    now = int(time.time())
    tok = jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + 3600},
        _SECRET, algorithm="HS256",
    )
    return {"Authorization": f"Bearer {tok}"}


async def _seed_user_and_account(applied_db, cash: float = 1000000.0) -> tuple[int, int]:
    conn = await asyncpg.connect(applied_db)
    try:
        user_id = await conn.fetchval(
            "INSERT INTO users (email) VALUES ($1) RETURNING id",
            f"paper-v2-{time.time_ns()}@test.com",
        )
        account_id = await conn.fetchval(
            "INSERT INTO sim_account (user_id, initial_cash, cash) VALUES ($1, $2, $2) RETURNING id",
            user_id, cash,
        )
        return user_id, account_id
    finally:
        await conn.close()


async def _seed_close(applied_db, ticker: str, price: float, d: date | None = None) -> None:
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO daily_prices (ticker, date, close) VALUES ($1, $2, $3) "
            "ON CONFLICT DO NOTHING",
            ticker, d or date.today(), price,
        )
    finally:
        await conn.close()


@pytest.fixture(autouse=True)
def _nextauth_secret(monkeypatch):
    monkeypatch.setenv("NEXTAUTH_SECRET", _SECRET)


# ── Order validation ─────────────────────────────────────────────────────────

async def test_buy_rejected_when_cash_insufficient(client_with_db, applied_db):
    user_id, _ = await _seed_user_and_account(applied_db, cash=1000.0)
    await _seed_close(applied_db, "AAPL", 200.0)

    r = client_with_db.post(
        "/api/paper/order",
        headers=_auth(user_id),
        json={"ticker": "AAPL", "side": "buy", "order_type": "market", "qty": 10},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "AAPL" in detail
    assert "2,000.00" in detail or "2000.00" in detail


async def test_buy_allowed_at_exact_cash_boundary(client_with_db, applied_db):
    user_id, _ = await _seed_user_and_account(applied_db, cash=2000.0)
    await _seed_close(applied_db, "AAPL", 200.0)

    r = client_with_db.post(
        "/api/paper/order",
        headers=_auth(user_id),
        json={"ticker": "AAPL", "side": "buy", "order_type": "market", "qty": 10},
    )
    assert r.status_code == 201


async def test_buy_allowed_when_no_price_data(client_with_db, applied_db):
    """No daily_prices row for the ticker: skip the check rather than block."""
    user_id, _ = await _seed_user_and_account(applied_db, cash=1.0)

    r = client_with_db.post(
        "/api/paper/order",
        headers=_auth(user_id),
        json={"ticker": "ZZZZ", "side": "buy", "order_type": "market", "qty": 10},
    )
    assert r.status_code == 201


async def test_sell_rejected_when_position_insufficient(client_with_db, applied_db):
    user_id, account_id = await _seed_user_and_account(applied_db)
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO sim_position (account_id, ticker, qty, avg_cost) VALUES ($1, 'AAPL', 5, 150.0)",
            account_id,
        )
    finally:
        await conn.close()

    r = client_with_db.post(
        "/api/paper/order",
        headers=_auth(user_id),
        json={"ticker": "AAPL", "side": "sell", "order_type": "market", "qty": 10},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert "AAPL" in detail
    assert "5" in detail


async def test_sell_rejected_when_no_position_at_all(client_with_db, applied_db):
    user_id, _ = await _seed_user_and_account(applied_db)
    r = client_with_db.post(
        "/api/paper/order",
        headers=_auth(user_id),
        json={"ticker": "NFLX", "side": "sell", "order_type": "market", "qty": 1},
    )
    assert r.status_code == 400


async def test_sell_allowed_at_exact_position_qty(client_with_db, applied_db):
    user_id, account_id = await _seed_user_and_account(applied_db)
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO sim_position (account_id, ticker, qty, avg_cost) VALUES ($1, 'AAPL', 5, 150.0)",
            account_id,
        )
    finally:
        await conn.close()

    r = client_with_db.post(
        "/api/paper/order",
        headers=_auth(user_id),
        json={"ticker": "AAPL", "side": "sell", "order_type": "market", "qty": 5},
    )
    assert r.status_code == 201


async def test_account_includes_realized_pnl_from_fully_closed_positions(
    client_with_db, applied_db
):
    user_id, account_id = await _seed_user_and_account(applied_db)
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO sim_position (account_id, ticker, qty, avg_cost, realized_pnl) "
            "VALUES ($1, 'AAPL', 0, 150.0, 500.0), "
            "       ($1, 'MSFT', 2, 300.0, 75.0)",
            account_id,
        )
    finally:
        await conn.close()

    response = client_with_db.get("/api/paper/account", headers=_auth(user_id))
    assert response.status_code == 200
    body = response.json()
    assert body["realized_pnl"] == pytest.approx(575.0)
    assert [position["ticker"] for position in body["positions"]] == ["MSFT"]


# ── Pick attribution round-trip ──────────────────────────────────────────────

def test_pick_attribution_round_trips_through_order_and_list(client_with_db, applied_db):
    """Two sequential TestClient calls share the asyncpg pool singleton, which
    is bound to the event loop of the first call (closed when that call
    returns). Reset the singleton between calls — same pattern as
    test_factor_lab_approval.py / test_evolution_approval.py."""
    import asyncio

    import alpha_agent.storage.postgres as _pg

    user_id, _ = asyncio.run(_seed_user_and_account(applied_db))
    pick_d = date.today() - timedelta(days=1)

    r = client_with_db.post(
        "/api/paper/order",
        headers=_auth(user_id),
        json={
            "ticker": "AAPL", "side": "buy", "order_type": "market", "qty": 1,
            "pick_date": pick_d.isoformat(), "pick_ticker": "AAPL",
        },
    )
    assert r.status_code == 201

    _pg._pool = None
    _pg._pool_dsn = None

    r2 = client_with_db.get("/api/paper/orders", headers=_auth(user_id))
    assert r2.status_code == 200
    orders = r2.json()["orders"]
    assert len(orders) == 1
    assert orders[0]["pick_date"] == pick_d.isoformat()
    assert orders[0]["pick_ticker"] == "AAPL"


def test_manual_order_has_null_pick_fields(client_with_db, applied_db):
    import asyncio

    import alpha_agent.storage.postgres as _pg

    user_id, _ = asyncio.run(_seed_user_and_account(applied_db))
    r = client_with_db.post(
        "/api/paper/order",
        headers=_auth(user_id),
        json={"ticker": "AAPL", "side": "buy", "order_type": "market", "qty": 1},
    )
    assert r.status_code == 201

    _pg._pool = None
    _pg._pool_dsn = None

    r2 = client_with_db.get("/api/paper/orders", headers=_auth(user_id))
    orders = r2.json()["orders"]
    assert orders[0]["pick_date"] is None
    assert orders[0]["pick_ticker"] is None


# ── Attribution aggregate endpoint ──────────────────────────────────────────

async def test_attribution_aggregates_realized_unrealized_and_trade_counts(client_with_db, applied_db):
    user_id, account_id = await _seed_user_and_account(applied_db)
    await _seed_close(applied_db, "AAPL", 220.0)

    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO sim_position (account_id, ticker, qty, avg_cost, realized_pnl) "
            "VALUES ($1, 'AAPL', 10, 200.0, 500.0)",
            account_id,
        )
        # One pick-linked filled order, one self-directed filled order.
        await conn.execute(
            "INSERT INTO sim_order (account_id, ticker, side, order_type, qty, signal_date, "
            "status, pick_date, pick_ticker) "
            "VALUES ($1, 'AAPL', 'buy', 'market', 5, $2, 'filled', $2, 'AAPL')",
            account_id, date.today() - timedelta(days=2),
        )
        await conn.execute(
            "INSERT INTO sim_order (account_id, ticker, side, order_type, qty, signal_date, status) "
            "VALUES ($1, 'AAPL', 'buy', 'market', 5, $2, 'filled')",
            account_id, date.today() - timedelta(days=1),
        )
        # A pending order must not be counted.
        await conn.execute(
            "INSERT INTO sim_order (account_id, ticker, side, order_type, qty, signal_date, status) "
            "VALUES ($1, 'AAPL', 'buy', 'market', 1, $2, 'pending')",
            account_id, date.today(),
        )
    finally:
        await conn.close()

    r = client_with_db.get("/api/paper/attribution", headers=_auth(user_id))
    assert r.status_code == 200
    rows = r.json()["tickers"]
    assert len(rows) == 1
    row = rows[0]
    assert row["ticker"] == "AAPL"
    assert row["realized_pnl"] == pytest.approx(500.0)
    assert row["unrealized_pnl"] == pytest.approx((220.0 - 200.0) * 10)
    assert row["pick_linked_trades"] == 1
    assert row["self_directed_trades"] == 1
    assert row["latest_pick_date"] == (date.today() - timedelta(days=2)).isoformat()
    assert row["source_type"] == "mixed"


@pytest.mark.parametrize(
    ("pick_date", "expected_source"),
    [
        (date.today() - timedelta(days=1), "pick"),
        (None, "manual"),
    ],
)
async def test_attribution_classifies_single_source(
    client_with_db, applied_db, pick_date, expected_source
):
    user_id, account_id = await _seed_user_and_account(applied_db)
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO sim_order (account_id, ticker, side, order_type, qty, "
            "signal_date, status, pick_date, pick_ticker) "
            "VALUES ($1, 'MSFT', 'buy', 'market', 1, $2, 'filled', $3, $4)",
            account_id,
            date.today(),
            pick_date,
            "MSFT" if pick_date else None,
        )
    finally:
        await conn.close()

    response = client_with_db.get("/api/paper/attribution", headers=_auth(user_id))
    row = response.json()["tickers"][0]
    assert row["source_type"] == expected_source


async def test_attribution_empty_account_returns_empty_list(client_with_db, applied_db):
    user_id, _ = await _seed_user_and_account(applied_db)
    r = client_with_db.get("/api/paper/attribution", headers=_auth(user_id))
    assert r.status_code == 200
    assert r.json()["tickers"] == []


# ── Fill-time cash re-check (cron) ──────────────────────────────────────────

async def test_fill_marks_order_failed_when_batch_exhausts_cash(applied_db):
    """Two same-day buy orders that together exceed cash: the first fills,
    the second must fail with a readable reason rather than overdraw."""
    conn = await asyncpg.connect(applied_db)
    try:
        user_id = await conn.fetchval(
            "INSERT INTO users (email) VALUES ('fillcash@test.com') RETURNING id"
        )
        acct_id = await conn.fetchval(
            "INSERT INTO sim_account (user_id, initial_cash, cash) VALUES ($1, 1000.0, 1000.0) RETURNING id",
            user_id,
        )
        signal_date = date(2026, 7, 10)
        fill_date = date(2026, 7, 11)
        order_ids = []
        for _ in range(2):
            oid = await conn.fetchval(
                "INSERT INTO sim_order (account_id, ticker, side, order_type, qty, signal_date) "
                "VALUES ($1, 'AAPL', 'buy', 'market', 6, $2) RETURNING id",
                acct_id, signal_date,
            )
            order_ids.append(oid)
        # 6 shares @ 100 = 600; two orders = 1200 > 1000 cash available.
        await conn.execute(
            "INSERT INTO daily_prices (ticker, date, close) VALUES ('AAPL', $1, 100.0) "
            "ON CONFLICT DO NOTHING", fill_date,
        )

        from alpha_agent.api.routes.cron_routes import _run_paper_fill
        result = await _run_paper_fill(applied_db)
        assert result["filled"] == 1
        assert result["failed"] == 1

        rows = await conn.fetch(
            "SELECT status, fail_reason FROM sim_order WHERE id = ANY($1::bigint[]) ORDER BY id",
            order_ids,
        )
        statuses = sorted(r["status"] for r in rows)
        assert statuses == ["failed", "filled"]
        failed_row = next(r for r in rows if r["status"] == "failed")
        assert failed_row["fail_reason"]
        assert "600.00" in failed_row["fail_reason"]

        acct = await conn.fetchrow("SELECT cash FROM sim_account WHERE id = $1", acct_id)
        assert acct["cash"] == pytest.approx(1000.0 - 600.0)
    finally:
        await conn.close()
