"""Tests for GET /api/evolution/* endpoints."""
from __future__ import annotations

import json

import asyncpg
import pytest


async def _seed(applied_db):
    conn = await asyncpg.connect(applied_db)
    try:
        for d, ic in (("2 days", 0.05), ("1 day", 0.08)):
            await conn.execute(
                "INSERT INTO signal_ic_history (signal_name, window_days, ic, n_observations, computed_at) "
                f"VALUES ('news', 30, $1, 40, now() - interval '{d}') ON CONFLICT DO NOTHING",
                ic,
            )
        await conn.execute(
            "INSERT INTO signal_weight_current (signal_name, status, weight, last_updated, reason, shadow_streak) "
            "VALUES ('news','live',0.10,now(),'ic_above_threshold',0) "
            "ON CONFLICT (signal_name,status) DO UPDATE SET weight=EXCLUDED.weight"
        )
        await conn.execute(
            "INSERT INTO signal_weight_current (signal_name, status, weight, last_updated, reason, shadow_streak) "
            "VALUES ('news','shadow',0.12,now(),'shadow_candidate',3) "
            "ON CONFLICT (signal_name,status) DO UPDATE SET weight=EXCLUDED.weight, shadow_streak=EXCLUDED.shadow_streak"
        )
        await conn.execute(
            "INSERT INTO confidence_calibration (as_of, isotonic_map, buckets, n_pairs, applied) "
            "VALUES (now(), $1::jsonb, $2::jsonb, 73, true)",
            json.dumps({"x": [0.4, 0.6], "y": [0.3, 0.5]}),
            json.dumps([{"lo": 0.4, "hi": 0.5, "hit_rate": 0.35, "brier": 0.12, "n": 40}]),
        )
        await conn.execute(
            "INSERT INTO config_change_log (user_id, field, old_value, new_value, source) "
            "VALUES (0, 'signal_weights', '{}', '{\"baseline_ic\": 0.1}', 'auto_promote')"
        )
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_ic_trend_returns_series(client_with_db, applied_db):
    await _seed(applied_db)
    body = client_with_db.get("/api/evolution/ic_trend?window_days=30").json()
    news = [s for s in body["series"] if s["signal_name"] == "news"]
    assert news and len(news[0]["points"]) >= 2
    assert {"computed_at", "ic"} <= set(news[0]["points"][0])


@pytest.mark.asyncio
async def test_weights_returns_live_and_shadow(client_with_db, applied_db):
    await _seed(applied_db)
    w = client_with_db.get("/api/evolution/weights").json()
    news = {row["status"]: row for row in w["weights"] if row["signal_name"] == "news"}
    assert news["live"]["weight"] == pytest.approx(0.10)
    assert news["shadow"]["weight"] == pytest.approx(0.12)
    assert news["shadow"]["shadow_streak"] == 3


@pytest.mark.asyncio
async def test_calibration_returns_latest_snapshot(client_with_db, applied_db):
    await _seed(applied_db)
    cal = client_with_db.get("/api/evolution/calibration").json()
    assert cal["applied"] is True and cal["n_pairs"] == 73
    assert cal["buckets"][0]["brier"] == pytest.approx(0.12)


@pytest.mark.asyncio
async def test_changes_returns_auto_promote(client_with_db, applied_db):
    await _seed(applied_db)
    ch = client_with_db.get("/api/evolution/changes?limit=10").json()
    assert any(c["source"] == "auto_promote" for c in ch["changes"])
