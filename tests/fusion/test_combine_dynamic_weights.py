"""Phase 6a Task 8: combine.py loads weights from signal_weight_current.

Tests verify:
  1. load_weights(pool) reads rows from signal_weight_current and returns a
     {signal_name: weight} dict.
  2. combine(..., weights_override=weights) honours the supplied weights and
     drops 0-weight signals from the composite cleanly.
"""
from __future__ import annotations

import pytest

from alpha_agent.fusion.combine import combine, load_weights
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.mark.asyncio
async def test_load_weights_from_db(pool):
    """signal_weight_current must drive combine weights, not a hardcoded dict."""
    await pool.execute(
        """
        INSERT INTO signal_weight_current
            (signal_name, weight, last_updated, reason)
        VALUES ($1, $2, now(), 'ic_above_threshold')
        """,
        "news", 0.045,
    )
    weights = await load_weights(pool)
    assert weights.get("news") == 0.045


@pytest.mark.asyncio
async def test_combine_drops_zero_weight_signals(pool):
    """Signals with weight 0 (auto-dropped) must not contribute."""
    await pool.execute(
        "INSERT INTO signal_weight_current(signal_name, weight, last_updated, reason) "
        "VALUES ('premarket', 0, now(), 'auto_dropped_low_ic')"
    )
    await pool.execute(
        "INSERT INTO signal_weight_current(signal_name, weight, last_updated, reason) "
        "VALUES ('news', 0.1, now(), 'ic_above_threshold')"
    )
    weights = await load_weights(pool)
    breakdown_in = [
        {"signal": "news", "z": 1.0, "confidence": 0.7,
         "weight_static": 0.1, "raw": {}, "source": "x"},
        {"signal": "premarket", "z": 2.0, "confidence": 0.5,
         "weight_static": 0.1, "raw": {}, "source": "x"},
    ]
    result = combine(breakdown_in, weights_override=weights)
    # premarket auto-dropped, only news contributes
    assert result["composite_score"] is not None
    pm_entry = next((b for b in result["breakdown"] if b["signal"] == "premarket"), None)
    if pm_entry:
        assert pm_entry["weight_effective"] == 0 or pm_entry["weight_effective"] is None
