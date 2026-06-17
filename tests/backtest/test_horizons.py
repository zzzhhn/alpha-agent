# tests/backtest/test_horizons.py
"""Signal horizon metadata + IC horizon validation (council #4, #3 pure parts)."""
import pytest

from alpha_agent.signals.horizons import (
    DEFAULT_HORIZON_DAYS,
    SIGNAL_HORIZON_DAYS,
    native_horizon,
)
from alpha_agent.backtest.ic_engine import compute_walk_forward_ic


def test_native_horizons_are_signal_appropriate():
    # factor + supply_chain are long-horizon; premarket is intraday; news is fast.
    assert native_horizon("factor") == 60
    assert native_horizon("supply_chain") == 60
    assert native_horizon("premarket") == 1
    assert native_horizon("news") == 3
    # unregistered signal falls back to the reference horizon.
    assert native_horizon("does_not_exist") == DEFAULT_HORIZON_DAYS


def test_every_default_weight_signal_has_a_horizon():
    # Keep the registry in lockstep with the fusion signal set.
    from alpha_agent.fusion.weights import DEFAULT_WEIGHTS

    for name in DEFAULT_WEIGHTS:
        assert name in SIGNAL_HORIZON_DAYS, f"missing native horizon for {name}"


@pytest.mark.asyncio
async def test_invalid_horizon_raises():
    # council #3: a non-positive / non-int horizon must fail loudly, not run a
    # malformed LEAD() query. (No DB needed; validation happens before the query.)
    for bad in (0, -5, 2.5, "5"):
        with pytest.raises(ValueError):
            await compute_walk_forward_ic(None, "factor", 90, horizon_days=bad)
