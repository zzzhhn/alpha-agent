"""Account identity/ownership and legacy compatibility without a live DB."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from alpha_agent.api.routes import paper
from alpha_agent.auth.dependencies import require_user
from alpha_agent.paper.accounts import create_bot_account, resolve_account


def _account(account_id=11, user_id=7, kind="human", **overrides):
    row = {
        "id": account_id, "user_id": user_id, "kind": kind,
        "name": "Original human" if kind == "human" else "Persistent bot",
        "status": "active", "initial_cash": 1000000.0,
        "cash": 812345.0, "reset_count": 3,
    }
    return row | overrides


@pytest.fixture
def pool():
    result = MagicMock()
    result.fetchrow = AsyncMock(return_value=_account())
    result.fetch = AsyncMock(return_value=[])
    result.fetchval = AsyncMock(return_value=0)
    result.execute = AsyncMock()
    return result


@pytest.fixture
def client(monkeypatch, pool):
    app = FastAPI()
    app.include_router(paper.router)
    app.dependency_overrides[require_user] = lambda: 7
    monkeypatch.setattr(paper, "get_db_pool", AsyncMock(return_value=pool))
    with TestClient(app) as client:
        yield client


async def test_default_resolves_human_without_touching_cash_or_history(pool):
    original = _account()
    resolved = await resolve_account(pool, 7)
    assert resolved == original
    sql, user_id = pool.fetchrow.call_args.args
    assert "kind = 'human'" in sql
    assert user_id == 7
    pool.execute.assert_not_awaited()
    pool.fetchrow.assert_awaited_once()


async def test_human_first_access_race_does_not_reset_the_winner(pool):
    winner = _account(cash=4321.0, reset_count=4)
    pool.fetchrow.side_effect = [None, winner]
    assert await resolve_account(pool, 7) == winner
    query = pool.fetchrow.call_args.args[0]
    assert "ON CONFLICT (user_id, kind)" in query
    assert "SET user_id=EXCLUDED.user_id" in query
    assert "SET cash" not in query


async def test_explicit_bot_resolves_with_owner_in_the_query(pool):
    bot = _account(22, kind="bot")
    pool.fetchrow.return_value = bot
    assert await resolve_account(pool, 7, 22) == bot
    sql, account_id, user_id = pool.fetchrow.call_args.args
    assert "id=$1 AND user_id=$2" in sql
    assert (account_id, user_id) == (22, 7)


async def test_missing_or_foreign_account_never_creates_a_replacement(pool):
    pool.fetchrow.return_value = None
    with pytest.raises(HTTPException) as exc:
        await resolve_account(pool, 7, 999)
    assert exc.value.status_code == 404
    pool.fetchrow.assert_awaited_once()
    pool.fetch.assert_not_awaited()


async def test_bot_creation_is_idempotent_and_does_not_rewrite_existing_book(pool):
    bot = _account(22, kind="bot", cash=500.0, reset_count=2)
    pool.fetchrow.return_value = bot
    first = await create_bot_account(pool, 7, "First name", 100000.0)
    second = await create_bot_account(pool, 7, "Changed request", 200000.0)
    assert first == second == bot
    sql = pool.fetchrow.call_args.args[0]
    assert "VALUES ($1, 'bot', $2, $3, $3)" in sql
    assert "DO UPDATE SET user_id=EXCLUDED.user_id" in sql
    assert "SET cash" not in sql and "SET name" not in sql
    pool.execute.assert_not_awaited()


@pytest.mark.parametrize("cash", [0, -1, float("inf"), float("nan")])
async def test_create_helper_rejects_invalid_cash_without_a_query(pool, cash):
    with pytest.raises(HTTPException) as exc:
        await create_bot_account(pool, 7, "Bot", cash)
    assert exc.value.status_code == 400
    pool.fetchrow.assert_not_awaited()


def test_account_list_does_not_create_a_bot(client, pool):
    pool.fetch.return_value = [_account()]
    response = client.get("/api/paper/accounts")
    assert response.status_code == 200
    assert response.json() == {"accounts": [{
        "account_id": 11, "kind": "human", "name": "Original human",
        "status": "active", "initial_cash": 1000000.0,
    }]}
    assert pool.fetch.call_args.args[1] == 7
    assert not any("INSERT" in call.args[0] for call in pool.fetchrow.call_args_list)


def test_create_api_returns_the_same_summary_on_retries(client, pool):
    pool.fetchrow.return_value = _account(22, kind="bot")
    first = client.post("/api/paper/accounts", json={"name": "Bot", "initial_cash": 10000})
    second = client.post("/api/paper/accounts", json={"name": "Other", "initial_cash": 20000})
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert first.json()["account_id"] == 22


@pytest.mark.parametrize("suffix", ["", "/orders", "/equity-curve", "/attribution"])
def test_all_scoped_reads_reject_other_owners_before_ledger_queries(client, pool, suffix):
    pool.fetchrow.return_value = None
    response = client.get(f"/api/paper/accounts/999{suffix}")
    assert response.status_code == 404
    assert pool.fetchrow.call_args.args[1:] == (999, 7)
    pool.fetch.assert_not_awaited()
    pool.execute.assert_not_awaited()


def test_legacy_query_cannot_switch_default_account(client, pool):
    response = client.get("/api/paper/account?account_id=22")
    assert response.status_code == 200
    assert response.json()["account_id"] == 11
    assert response.json()["cash"] == 812345.0
    assert response.json()["reset_count"] == 3
    assert "kind = 'human'" in pool.fetchrow.call_args.args[0]


def test_scoped_bot_summary_uses_existing_cash_and_cohort(client, pool):
    pool.fetchrow.side_effect = [
        _account(22, kind="bot", cash=1234.0, reset_count=0),
        None,  # No historical valuation has been recorded for this cohort.
    ]
    response = client.get("/api/paper/accounts/22")
    assert response.status_code == 200
    assert response.json()["cash"] == 1234.0
    assert response.json()["account_id"] == 22
    assert response.json()["last_valid_valuation"] is None
    ledger_query = pool.fetch.call_args_list[0]
    assert ledger_query.args[1:] == (22, 0)


def test_scoped_equity_retains_existing_history(client, pool):
    pool.fetchrow.return_value = _account(22, kind="bot", reset_count=0)
    pool.fetch.return_value = [{
        "as_of_date": date(2026, 10, 30), "portfolio_value": 125000.0,
        "benchmark_close": 500.0,
    }]
    response = client.get("/api/paper/accounts/22/equity-curve")
    assert response.status_code == 200
    assert response.json()["series"][0]["portfolio_value"] == 125000.0
    assert pool.fetch.call_args.args[1:] == (22, 0)


def test_scoped_orders_select_only_the_requested_book(client, pool):
    pool.fetchrow.return_value = _account(22, kind="bot", reset_count=0)
    response = client.get("/api/paper/accounts/22/orders")
    assert response.status_code == 200
    assert pool.fetch.call_args.args[1:3] == (22, 0)
    assert pool.fetchval.call_args.args[1:] == (22, 0)


def test_scoped_attribution_keeps_realized_history(client, pool):
    pool.fetchrow.return_value = _account(22, kind="bot", reset_count=0)
    pool.fetch.side_effect = [[{
        "ticker": "AAPL", "qty": 0, "avg_cost": 100.0, "realized_pnl": 321.0,
    }], [{
        "ticker": "AAPL", "pick_linked": 0, "self_directed": 1, "latest_pick_date": None,
    }]]
    response = client.get("/api/paper/accounts/22/attribution")
    assert response.status_code == 200
    assert response.json()["tickers"][0]["realized_pnl"] == 321.0
    assert all(call.args[1:] == (22, 0) for call in pool.fetch.call_args_list)


def test_new_accounts_and_scoped_reads_require_login(monkeypatch, pool):
    app = FastAPI()
    app.include_router(paper.router)
    monkeypatch.setattr(paper, "get_db_pool", AsyncMock(return_value=pool))
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/paper/accounts").status_code == 401
        assert anonymous.get("/api/paper/accounts/22").status_code == 401
        assert anonymous.post("/api/paper/accounts", json={
            "name": "Bot", "initial_cash": 100000,
        }).status_code == 401
    pool.fetchrow.assert_not_awaited()


@pytest.mark.parametrize("method,path", [
    ("post", "/api/paper/accounts/22/orders"),
    ("delete", "/api/paper/accounts/22/orders/44"),
    ("post", "/api/paper/accounts/22/reset"),
])
def test_manual_bot_mutation_routes_are_not_exposed(client, pool, method, path):
    response = getattr(client, method)(path)
    assert response.status_code in {404, 405}
    pool.fetchrow.assert_not_awaited()
    pool.execute.assert_not_awaited()


def test_mutation_guard_defends_against_accidental_bot_resolution():
    with pytest.raises(HTTPException) as exc:
        paper._require_human(_account(22, kind="bot"))
    assert exc.value.status_code == 403


def test_account_migration_preserves_legacy_ledger():
    migration = Path(paper.__file__).parents[2] / "storage/migrations/V049__paper_account_kinds.sql"
    sql = migration.read_text()
    assert "DEFAULT 'human'" in sql
    assert "UNIQUE (user_id, kind)" in sql
    assert "DROP CONSTRAINT IF EXISTS sim_account_user_id_key" in sql
    for forbidden in ["DELETE FROM", "TRUNCATE", "DROP TABLE", "UPDATE sim_position", "UPDATE sim_order"]:
        assert forbidden not in sql
