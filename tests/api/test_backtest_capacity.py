from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from alpha_agent.api.routes.interactive import (
    FactorBacktestRequest,
    _BACKTEST_CAPACITY,
    factor_backtest,
)


def _request() -> FactorBacktestRequest:
    return FactorBacktestRequest.model_validate({
        "spec": {
            "name": "capacity_test",
            "hypothesis": "test capacity guard",
            "expression": "ts_mean(close, 5)",
            "operators_used": ["ts_mean"],
            "lookback": 10,
            "universe": "SP500",
            "justification": "test",
        }
    })


def test_busy_backtest_capacity_fails_fast_with_retry_hint() -> None:
    async def scenario() -> None:
        await _BACKTEST_CAPACITY.acquire()
        try:
            with pytest.raises(HTTPException) as caught:
                await factor_backtest(_request())
        finally:
            _BACKTEST_CAPACITY.release()

        assert caught.value.status_code == 429
        assert caught.value.headers == {"Retry-After": "5"}
        assert "active run" in str(caught.value.detail)

    asyncio.run(scenario())
