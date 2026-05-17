"""Tests for Phase 6a Task 10: /api/_health/signals extended fields.

Verifies that /api/_health/signals exposes live IC values (30/60/90 day
windows), current weight, and tier color per signal. Tier rules:
  green   = min(ic_30d, ic_60d, ic_90d) > 0.02
  yellow  = 0.01 < min(ics) <= 0.02
  red     = auto_dropped_low_ic OR weight == 0
  unknown = no IC data
"""
from __future__ import annotations

import asyncpg
import pytest


@pytest.mark.asyncio
async def test_signals_includes_ic_and_tier(client_with_db, applied_db):
    """News signal with IC > 0.02 across all windows should report green tier."""
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO signal_ic_history(signal_name, window_days, ic, "
            "n_observations, computed_at) VALUES "
            "('news', 30, 0.045, 100, now()), "
            "('news', 60, 0.052, 200, now()), "
            "('news', 90, 0.039, 300, now())"
        )
        await conn.execute(
            "INSERT INTO signal_weight_current"
            "(signal_name, weight, last_updated, reason) "
            "VALUES ('news', 0.045, now(), 'ic_above_threshold')"
        )
    finally:
        await conn.close()

    r = client_with_db.get("/api/_health/signals")
    assert r.status_code == 200
    body = r.json()
    news_entry = next(s for s in body["signals"] if s["name"] == "news")
    assert "live_ic_30d" in news_entry
    assert abs(news_entry["live_ic_30d"] - 0.045) < 1e-3
    assert news_entry["tier"] == "green"
    assert abs(news_entry["weight_current"] - 0.045) < 1e-3


@pytest.mark.asyncio
async def test_dropped_signal_shows_red_tier(client_with_db, applied_db):
    """A signal with weight=0 + auto_dropped reason should report red tier."""
    conn = await asyncpg.connect(applied_db)
    try:
        await conn.execute(
            "INSERT INTO signal_weight_current"
            "(signal_name, weight, last_updated, reason) "
            "VALUES ('premarket', 0, now(), 'auto_dropped_low_ic')"
        )
    finally:
        await conn.close()

    r = client_with_db.get("/api/_health/signals")
    assert r.status_code == 200
    body = r.json()
    pm = next(s for s in body["signals"] if s["name"] == "premarket")
    assert pm["tier"] == "red"
    assert pm["weight_current"] == 0.0
