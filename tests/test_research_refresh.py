from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pandas as pd
import pytest

from alpha_agent.data.security_identity import valid_research_symbol
from alpha_agent.backtest.l2 import select_holdings
from scripts.refresh_research_dataset import sec_snapshots, supplement_membership


def test_reused_para_is_not_paramount_or_automatically_psky():
    assert valid_research_symbol("PARA", date(2025, 8, 6))
    assert not valid_research_symbol("PARA", date(2026, 10, 30))
    rows = [{"ticker": t, "eligible": True, "tier": "BUY", "rank": i}
            for i, t in enumerate(["PARA", "AAPL", "MSFT"])]
    assert [r["ticker"] for r in select_holdings(rows, top_n=2)] == ["AAPL", "MSFT"]


def test_sec_uses_real_publication_quarter_and_units():
    common = {"end": "2026-06-30", "filed": "2026-08-01", "form": "10-Q"}
    payload = {"facts": {"us-gaap": {
        "Assets": {"units": {"USD": [{**common, "val": 500_000_000}]}},
        "Revenues": {"units": {"USD": [
            {**common, "start": "2026-04-01", "val": 20_000_000},
            {**common, "start": "2026-01-01", "val": 50_000_000},
            {**common, "start": "2026-04-01", "filed": "2026-11-01", "val": 25_000_000}]}},
    }}}
    rows = sec_snapshots(payload, "ABC", after="2026-04-30", through="2026-10-30")
    assert len(rows) == 1
    assert rows[0]["filing_date"] == "2026-08-02"
    assert rows[0]["assets"] == 500
    assert rows[0]["revenue"] == 20  # no YTD or future restatement leakage
    assert "eps" not in rows[0]  # never synthesize missing fields


def test_official_membership_updates_use_effective_dates():
    seed = pd.DataFrame([{"date": "2026-08-18", "tickers": "AAPL,TAP,TTD,BLDR,CTVA,WBD"}])
    september, _ = supplement_membership(seed, "2026-09-20")
    assert len(september) == 1
    latest, _ = supplement_membership(seed, "2026-10-30")
    symbols = set(latest.iloc[-1].tickers.split(","))
    assert symbols == {"AAPL", "BE", "P", "ILMN", "VYLR", "TWLO"}
    assert "OKTA" not in symbols  # announced, but only effective November 4


@pytest.mark.asyncio
async def test_identity_quarantine_prevents_any_fills_or_mutations():
    from alpha_agent.backtest.l2_driver import run_continuous_driver, run_driver
    pool = SimpleNamespace(fetch=AsyncMock(return_value=[{"ticker": "PARA"}]), execute=AsyncMock())
    for driver in (run_driver, run_continuous_driver):
        pool.fetch.reset_mock()
        result = await driver(pool, strategy_id=27)
        assert result["status"] == "identity_quarantined"
        assert result["generated"] == result["filled"] == 0
        pool.fetch.assert_awaited_once()
        pool.execute.assert_not_called()
