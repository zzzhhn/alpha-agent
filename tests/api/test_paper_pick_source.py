from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import UTC, date, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from alpha_agent.api.routes import paper, picks
from alpha_agent.fusion.policy import get_policy
from alpha_agent.storage import product_ledger
from tests.api.test_picks_contract import snapshot

MARKET_DATE = date(2026, 11, 10)
RUN_ID = 10


@pytest.fixture
def order_fixture(monkeypatch):
    run = {
        "id": RUN_ID, "scheduled_for_date": MARKET_DATE, "run_type": "daily_close",
        "finished_at": datetime(2026, 11, 10, 22, tzinfo=UTC), "data_asof": None,
        "input_data_cutoff": None, "weight_policy_id": "tactical-test",
        "health_json": {"passed": True},
    }
    rows = [snapshot(f"T{i:02}", 61. - i, i, strategic=float(i)) for i in range(1, 61)]
    account = {"id": 1, "cash": 100_000, "reset_count": 0}
    conn = AsyncMock()
    conn.fetchrow.return_value = account
    instrument = {"id": 17, "identity_status": "supported_universe"}
    conn.fetchrow.side_effect = [account, instrument]
    conn.fetchval.side_effect = [0, 123]

    @asynccontextmanager
    async def transaction():
        yield

    @asynccontextmanager
    async def acquire():
        yield conn

    conn.transaction = transaction
    pool = MagicMock(acquire=acquire, fetchrow=AsyncMock(return_value=None))
    monkeypatch.setattr(product_ledger, "get_latest_canonical_run", AsyncMock(return_value=run))
    monkeypatch.setattr(product_ledger, "get_run_snapshots", AsyncMock(return_value=rows))
    monkeypatch.setattr(picks, "get_db_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(picks, "latest_completed_xnys_session", lambda: MARKET_DATE)
    monkeypatch.setattr(paper, "get_db_pool", AsyncMock(return_value=pool))
    monkeypatch.setattr(paper, "_get_or_create_account", AsyncMock(return_value=account))
    monkeypatch.setattr(paper, "latest_completed_xnys_session", lambda now: MARKET_DATE)
    monkeypatch.setattr(paper, "_paper_signal_session", lambda now: MARKET_DATE)
    conn.fetch.return_value = [{"ticker": r["ticker"], "date": MARKET_DATE, "close": 100.0} for r in rows]

    app = FastAPI()
    app.include_router(paper.router)
    app.include_router(picks.router)
    app.dependency_overrides[paper.require_user] = lambda: 1
    return TestClient(app), conn, run, rows


def order_body(ticker, *, mode="long", board_side="long"):
    return {
        "ticker": ticker, "side": "buy", "order_type": "market", "qty": 100,
        "pick_date": MARKET_DATE.isoformat(), "pick_ticker": ticker,
        "pick_run_id": RUN_ID, "pick_mode": mode, "pick_side": board_side,
    }


@pytest.mark.parametrize(
    ("mode", "board_side", "rank", "expected_ticker"),
    [("long", "long", 1, "T60"), ("long", "long", 6, "T55"),
     ("long", "long", 50, "T11"), ("long", "short", 1, "T01"),
     ("short", "long", 50, "T50")],
)
def test_ranked_board_order_persists_exact_mode_payload(
    order_fixture, mode, board_side, rank, expected_ticker,
):
    client, conn, run, rows = order_fixture
    board = client.get(f"/api/picks/lean?limit=50&mode={mode}&side={board_side}").json()
    card = board["picks"][rank - 1]
    assert card["ticker"] == expected_ticker
    assert card["run_id"] == RUN_ID
    assert card["market_date"] == MARKET_DATE.isoformat()
    response = client.post("/api/paper/order", json=order_body(
        expected_ticker, mode=mode, board_side=board_side,
    ))
    assert response.status_code == 201, response.text

    insert_sql, *args = conn.fetchval.await_args.args
    assert "INSERT INTO sim_order" in insert_sql
    assert args[1:5] == [expected_ticker, "buy", "market", 100]
    payload = next(row["user_visible_payload_json"] for row in rows if row["ticker"] == expected_ticker)
    policy = run["weight_policy_id"]
    if mode == "long":
        payload = payload["_mode_payloads"]["long"]
        policy = get_policy("strategic").policy_id
    assert args[7:12] == [MARKET_DATE, expected_ticker, RUN_ID, policy, paper._canonical_payload_hash(payload)]
    assert board["run"]["policy_id"] == policy
    assert args[12] == pytest.approx(10010)
    assert args[15:17] == [17, 100.0]
    conn.fetch.assert_awaited_once()
    assert conn.fetch.await_args.args[1:] == ([expected_ticker], [MARKET_DATE])


@pytest.mark.parametrize(("case", "detail"), [
    ("replaced", "superseded"),
    ("expired", "not tradable"),
    ("unranked", "not ranked"),
    ("mode", "mode is unavailable"),
    ("board_quote", "not tradable"),
    ("ticker_quote", "no valid close"),
])
def test_unusable_pick_sources_never_insert_orders(order_fixture, monkeypatch, case, detail):
    client, conn, run, rows = order_fixture
    body = order_body("T55")
    if case == "replaced":
        run["id"] = RUN_ID + 1
    if case == "expired":
        monkeypatch.setattr(picks, "latest_completed_xnys_session", lambda: date(2026, 11, 11))
    if case == "unranked":
        body = order_body("T01")  # Bottom of the strategic long board.
    if case == "mode":
        rows[0]["user_visible_payload_json"].pop("_mode_payloads")
    if case == "board_quote":
        rows[54]["user_visible_payload_json"]["_mode_payloads"]["long"]["price_date"] = "2026-11-09"
    if case == "ticker_quote":
        body = order_body("T01", board_side="short")
        rows[0]["user_visible_payload_json"]["_mode_payloads"]["long"]["latest_price"] = None

    response = client.post("/api/paper/order", json=body)
    assert response.status_code == 409
    assert detail in response.json()["detail"]
    conn.fetchval.assert_not_awaited()


def test_legacy_attribution_keeps_original_policy_and_hash(order_fixture):
    client, conn, run, rows = order_fixture
    payload = deepcopy(rows[0]["user_visible_payload_json"])
    conn.fetchrow.side_effect = [
        conn.fetchrow.return_value,
        {**run, "user_visible_payload_json": payload},
        {"id": 17, "identity_status": "supported_universe"},
    ]
    body = order_body("T01")
    del body["pick_mode"], body["pick_side"]
    response = client.post("/api/paper/order", json=body)
    assert response.status_code == 201
    assert conn.fetchval.await_args.args[11:13] == (
        run["weight_policy_id"], paper._canonical_payload_hash(payload),
    )
