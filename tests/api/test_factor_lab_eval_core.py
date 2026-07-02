"""Locks the behaviour of _evaluate_and_record — the shared validation core the
LLM proposer and the GA search both feed. With the per-candidate evaluator and
the self-correlation gate stubbed (so no panel/kernel/LLM is needed), it asserts
the DSR gate keeps the winner and drops the loser, the survivor is inserted as a
pending proposal tagged with its source, and every candidate is journaled."""
import json

import asyncpg
import pytest

from alpha_agent.api.routes import factor_lab
from alpha_agent.evolution.factor_validation import FactorCandidateResult
from alpha_agent.evolution.llm_factor_proposer import RawProposal


class _Diag:
    current_expression = "rank(returns)"

    def to_jsonable(self) -> dict:
        return {"current_expression": self.current_expression}


# canned per-expression Sharpe series: baseline ~1.0, a clear winner, a loser
# that fails the 60%-of-baseline mean gate.
_SHARPES = {
    "rank(returns)": [1.0, 1.0, 1.0],       # baseline
    "ts_mean(vwap, 20)": [2.0, 2.0, 2.0],   # winner (beats gate)
    "rank(volume)": [0.2, 0.2, 0.2],        # loser (below 0.6 * baseline)
}


async def _fake_eval(pool, runner, proposal, out_rejects=None):
    sharpes = _SHARPES.get(proposal.expression)
    if sharpes is None:
        return None
    return FactorCandidateResult(
        expression=proposal.expression,
        new_operators=[],
        sharpes=sharpes,
        ic_oos=0.03,
        n_folds=len(sharpes),
        operator_test_results=[],
    )


class _DummyRunner:
    def close(self) -> None:
        pass


class _DummyGate:
    def __init__(self, saved):
        pass

    def check(self, expression):
        return (0.0, None)  # never redundant


@pytest.mark.asyncio
async def test_evaluate_and_record_gates_inserts_and_journals(applied_db, monkeypatch):
    monkeypatch.setattr(factor_lab, "evaluate_factor_candidate", _fake_eval)
    monkeypatch.setattr(factor_lab, "SandboxRunner", _DummyRunner)
    monkeypatch.setattr(factor_lab, "SelfCorrelationGate", _DummyGate)

    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        winner = RawProposal(expression="ts_mean(vwap, 20)", new_operators=[])
        loser = RawProposal(expression="rank(volume)", new_operators=[])

        # llm_client=None => skeptic pass skipped (GA-style autonomous run).
        result = await factor_lab._evaluate_and_record(
            pool, [winner, loser], _Diag(), llm_client=None, source="ga"
        )

        assert result["evaluated"] == 2
        assert result["proposed"] == 1

        rows = await pool.fetch(
            "SELECT expression, status, evidence FROM factor_proposals"
        )
        assert len(rows) == 1
        assert rows[0]["status"] == "pending"
        assert rows[0]["expression"] == "ts_mean(vwap, 20)"
        ev = rows[0]["evidence"]
        ev = json.loads(ev) if isinstance(ev, str) else ev
        assert ev["source"] == "ga"          # source tag round-trips
        assert ev["skeptic"] is None          # no client => no skeptic verdict

        lessons = await pool.fetch("SELECT expression, outcome FROM factor_lessons")
        outcomes = {row["expression"]: row["outcome"] for row in lessons}
        assert outcomes["ts_mean(vwap, 20)"] == "accepted"
        assert outcomes["rank(volume)"] == "weak"
    finally:
        await pool.close()
