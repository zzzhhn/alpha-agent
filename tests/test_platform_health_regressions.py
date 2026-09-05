from __future__ import annotations

import asyncio
import json
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock

import asyncpg
import pytest

from alpha_agent.api.routes.picks import _load_market_context
from alpha_agent.data.retention import prune_daily_signals
from alpha_agent.fusion.rating import compute_confidence
from alpha_agent.storage import postgres
from alpha_agent.storage.product_ledger import LedgerConflict, RunMeta, record_research_run
from alpha_agent.storage.queries import upsert_daily_close
from alpha_agent.auth.dependencies import require_admin
from fastapi import HTTPException


async def test_cold_start_creates_only_one_pool_and_never_prints_dsn(monkeypatch):
    fake_pool = object()
    calls = 0

    async def create_pool(*args, **kwargs):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0)
        return fake_pool

    monkeypatch.setattr(asyncpg, "create_pool", create_pool)
    monkeypatch.setattr(postgres, "_pool", None)
    monkeypatch.setattr(postgres, "_pool_lock", None)
    results = await asyncio.gather(*(postgres.get_pool("secret-dsn") for _ in range(8)))
    assert calls == 1
    assert all(p is fake_pool for p in results)
    with pytest.raises(RuntimeError, match="different database") as exc:
        await postgres.get_pool("another-secret")
    assert "secret" not in str(exc.value)
    postgres._pool = None


async def test_invalid_previous_price_cannot_break_snapshot_json():
    pool = AsyncMock()
    pool.fetch.return_value = [{
        "ticker": "APH", "latest_price": 135.0, "previous_price": float("nan"),
        "price_date": date.today(), "company_name": "Amphenol", "company_name_zh": None,
    }]
    context = await _load_market_context(pool, ["APH"])
    assert context["APH"]["daily_change_pct"] is None
    assert context["APH"]["latest_price"] == 135.0
    json.dumps(context, allow_nan=False)


async def test_daily_price_writer_rejects_non_finite_data():
    pool = AsyncMock()
    for price in [float("nan"), float("inf"), float("-inf"), 0, -1, None]:
        await upsert_daily_close(pool, "APH", "2026-09-04", price)
    pool.execute.assert_not_called()
    assert compute_confidence([1.0, float("inf")]) == 1.0


async def test_prune_keeps_unmaterialized_ticker_even_before_global_watermark(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    old = date.today() - timedelta(days=100)
    try:
        await pool.executemany(
            "INSERT INTO daily_signals_fast(ticker,date,composite,rating) VALUES($1,$2,1,'OW')",
            [("AAPL", old), ("MSFT", old)],
        )
        await pool.execute("INSERT INTO consistency_outcomes VALUES('AAPL',$1,true)", old)
        await prune_daily_signals(pool)
        assert [r["ticker"] for r in await pool.fetch("SELECT ticker FROM daily_signals_fast")] == ["MSFT"]
    finally:
        await pool.close()


async def test_concurrent_publish_records_one_complete_run(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        meta = RunMeta(scheduled_for_date=date.today(), status="complete", started_at=datetime.now(UTC))
        results = await asyncio.gather(
            record_research_run(pool, meta, []), record_research_run(pool, meta, []),
            return_exceptions=True,
        )
        assert sum(isinstance(r, LedgerConflict) for r in results) == 1
        assert await pool.fetchval("SELECT count(*) FROM research_run WHERE status='complete'") == 1
    finally:
        await pool.close()


async def test_admin_role_is_explicit_and_fail_closed(monkeypatch):
    monkeypatch.delenv("ALPHACORE_ADMIN_USER_IDS", raising=False)
    with pytest.raises(HTTPException) as exc:
        await require_admin(user_id=2)
    assert exc.value.status_code == 403
    monkeypatch.setenv("ALPHACORE_ADMIN_USER_IDS", "2")
    assert await require_admin(user_id=2) == 2
    with pytest.raises(HTTPException):
        await require_admin(user_id=1)


def test_non_admin_cannot_mutate_global_policy(monkeypatch):
    from alpha_agent.auth.dependencies import require_user
    from alpha_agent.api.app import create_app
    from fastapi.testclient import TestClient
    client_with_db = TestClient(create_app())
    monkeypatch.setenv("ALPHACORE_ADMIN_USER_IDS", "2")
    client_with_db.app.dependency_overrides[require_user] = lambda: 3
    for path, body in [
        ("/api/admin/config", {"key": "rating.no_trade_band", "value": 0.2}),
        ("/api/factor-lab/_apply_migrations", {}),
        ("/api/factor-lab/_demo_seed", {}),
        ("/api/factor-lab/proposals/1/approve", {}),
        ("/api/evolution/proposals/1/approve", {}),
    ]:
        assert client_with_db.post(path, json=body).status_code == 403


async def test_byok_model_rollback_does_not_touch_brain_credential(applied_db, monkeypatch):
    from alpha_agent.api.routes import user
    from alpha_agent.settings.change_log import record_change
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        uid = await pool.fetchval("INSERT INTO users(email) VALUES('rollback@example.invalid') RETURNING id")
        for provider, model in [("kimi", "current-model"), ("worldquant_brain", "brain-marker")]:
            await pool.execute("""INSERT INTO user_byok(user_id,provider,ciphertext,nonce,last4,model)
                VALUES($1,$2,$3,$4,'test',$5)""", uid, provider, b"encrypted", b"nonce", model)
        change = await record_change(pool, uid, "byok.model", "old-model", "current-model")
        monkeypatch.setattr(user, "get_db_pool", AsyncMock(return_value=pool))
        await user.settings_rollback(change, user_id=uid)
        rows = {r["provider"]: r["model"] for r in await pool.fetch("SELECT provider,model FROM user_byok")}
        assert rows == {"kimi": "old-model", "worldquant_brain": "brain-marker"}
    finally:
        await pool.close()
