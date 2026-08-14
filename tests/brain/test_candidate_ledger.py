"""P0 generated-candidate audit ledger coverage."""
import asyncpg
import pytest

from alpha_agent.brain import store
from alpha_agent.brain.client import AlphaMetrics
from alpha_agent.brain.mining_loop import run_mining_round


@pytest.mark.asyncio
async def test_generated_candidates_are_run_scoped_and_paginated(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        run = await store.create_brain_run(
            pool,
            user_id=1,
            source="manual",
            requested_n=1,
            generation_target_n=2,
        )
        rows = await store.record_brain_run_candidates(
            pool,
            run["id"],
            [
                {
                    "expression": "rank(close)",
                    "settings": {"decay": 4},
                    "mechanism": "momentum",
                },
                {
                    "expression": "rank(volume)",
                    "settings": {"decay": 8},
                    "mechanism": "microstructure",
                },
            ],
        )
        assert [row["ordinal"] for row in rows] == [0, 1]
        assert rows[0]["settings"] == {"decay": 4}

        await store.update_brain_run_candidate(
            pool,
            rows[0]["id"],
            selected=True,
            stage="screened",
            status="selected",
            evidence={"coverage": 0.92},
            evidence_score=7.3,
            llm_score=8.0,
            llm_status="scored",
            reason_code="selected",
            reason_text="selected for simulation",
        )
        await store.update_brain_run_candidate(
            pool,
            rows[1]["id"],
            stage="screened",
            status="withheld",
            llm_status="bypassed",
            reason_code="below_evidence_threshold",
            reason_text="evidence score 3.20 < 5.75",
        )

        page = await store.query_brain_run_candidates(
            pool, 1, run["id"], limit=1, offset=0
        )
        assert page["total"] == 2
        assert page["candidates"][0]["selected"] is True
        assert page["candidates"][0]["evidence"] == {"coverage": 0.92}

        withheld = await store.query_brain_run_candidates(
            pool, 1, run["id"], selected=False, status="withheld"
        )
        assert withheld["total"] == 1
        assert withheld["candidates"][0]["reason_code"] == "below_evidence_threshold"

        # Parent-run ownership is part of the SQL query, not a client-side filter.
        foreign = await store.query_brain_run_candidates(pool, 2, run["id"])
        assert foreign["total"] == 0 and foreign["candidates"] == []
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_mining_updates_selected_candidate_with_simulation_outcome(
    applied_db, monkeypatch
):
    class _FakeBrain:
        def __init__(self):
            self.i = 0
            self.by_sim = {}

        async def authenticate(self):
            return None

        async def list_active_alphas(self):
            return []

        async def fetch_data_fields(self, **kwargs):
            return []

        async def simulate(self, expression, settings):
            self.i += 1
            self.by_sim[f"sim{self.i}"] = {
                "alpha": f"A{self.i}",
                "metrics": AlphaMetrics(
                    "x",
                    sharpe=1.5 if self.i == 1 else 0.2,
                    fitness=1.1 if self.i == 1 else 0.2,
                    turnover=0.1,
                    returns=0.2,
                    drawdown=0.05,
                ),
            }
            return f"sim{self.i}"

        async def poll_simulation(self, simulation_id, **kwargs):
            return self.by_sim[simulation_id]

        async def get_alpha_metrics(self, alpha_id):
            return self.by_sim[f"sim{alpha_id[1:]}"]["metrics"]

        async def get_self_correlation(self, alpha_id, **kwargs):
            return 0.1

        async def get_pnl(self, alpha_id):
            return {"records": []}

    import alpha_agent.brain.mining_loop as mining_loop

    monkeypatch.setattr(
        mining_loop,
        "generate_brain_candidates",
        lambda *args, **kwargs: ["rank(close)", "rank(volume)"],
    )
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        run = await store.create_brain_run(
            pool,
            user_id=1,
            source="manual",
            requested_n=2,
            generation_target_n=2,
        )
        summary = await run_mining_round(
            _FakeBrain(),
            pool,
            user_id=1,
            n_candidates=2,
            run_id=run["id"],
            seed_from_user_alphas=False,
            family_caps={},
            max_retries=0,
        )
        assert summary["persisted"] == 2
        ledger = await store.query_brain_run_candidates(pool, 1, run["id"])
        assert ledger["total"] == 2
        assert {row["status"] for row in ledger["candidates"]} == {"selected"}
        assert {row["stage"] for row in ledger["candidates"]} == {"simulation"}
        assert all(row["alpha_row_id"] is not None for row in ledger["candidates"])
        assert {row["simulation_outcome"] for row in ledger["candidates"]} == {
            "passed",
            "rejected",
        }
    finally:
        await pool.close()
