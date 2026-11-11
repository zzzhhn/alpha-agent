"""Locks the behaviour of _evaluate_and_record — the shared validation core the
LLM proposer and the GA search both feed. With the per-candidate evaluator and
the self-correlation gate stubbed (so no panel/kernel/LLM is needed), it asserts
the DSR gate keeps the winner and drops the loser, the survivor is inserted as a
pending proposal tagged with its source, and every candidate is journaled."""
import json
import asyncio
from types import SimpleNamespace

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


async def _fake_eval(pool, runner, proposal, out_rejects=None, *, context=None):
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
    def __init__(self, saved, **kwargs):
        pass

    def check(self, expression):
        return (0.0, None)  # never redundant


@pytest.fixture(autouse=True)
def evaluation_stubs(monkeypatch):
    monkeypatch.setattr(factor_lab, "evaluate_factor_candidate", _fake_eval)
    monkeypatch.setattr(factor_lab, "SandboxRunner", _DummyRunner)
    monkeypatch.setattr(factor_lab, "SelfCorrelationGate", _DummyGate)
    monkeypatch.setattr(factor_lab, "load_research_context", lambda: SimpleNamespace(
        panel=None, evidence=lambda: {"validator": "test"},
    ))


@pytest.mark.asyncio
async def test_evaluate_and_record_gates_inserts_and_journals(applied_db):
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
        assert ev["gate_version"] == "dsr_lite_v2_nonneg_floor"
        assert ev["base_threshold"] == pytest.approx(0.6)
        assert result["duplicates_skipped"] == 0

        lessons = await pool.fetch("SELECT expression, outcome FROM factor_lessons")
        outcomes = {row["expression"]: row["outcome"] for row in lessons}
        assert outcomes["ts_mean(vwap, 20)"] == "accepted"
        assert outcomes["rank(volume)"] == "weak"
    finally:
        await pool.close()


@pytest.mark.parametrize("status", ["pending", "approved", "rejected"])
@pytest.mark.parametrize("source", ["llm", "ga"])
async def test_factor_lab_dedup_only_blocks_pending(applied_db, status, source):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        original = await pool.fetchrow(
            "INSERT INTO factor_proposals (status, expression, evidence, diagnostic) "
            "VALUES ($1, 'ts_mean( vwap,20 )', '{}'::jsonb, '{}'::jsonb) RETURNING *",
            status,
        )
        result = await factor_lab._evaluate_and_record(
            pool, [RawProposal(expression="ts_mean(vwap, 20)", new_operators=[])],
            _Diag(), source=source,
        )
        duplicate = status == "pending"
        assert result["proposed"] == (0 if duplicate else 1)
        assert result["duplicates_skipped"] == int(duplicate)
        assert result["_diag"]["duplicates_skipped"] == int(duplicate)
        candidate = result["_diag"]["candidates"][0]
        assert candidate.get("skipped_duplicate", False) == duplicate
        assert await pool.fetchval("SELECT count(*) FROM factor_proposals") == (1 if duplicate else 2)
        assert dict(await pool.fetchrow(
            "SELECT * FROM factor_proposals WHERE id=$1", original["id"],
        )) == dict(original)
    finally:
        await pool.close()


async def test_factor_lab_dedup_within_same_round(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        proposal = RawProposal(expression="ts_mean(vwap, 20)", new_operators=[])
        result = await factor_lab._evaluate_and_record(pool, [proposal, proposal], _Diag())
        assert result["proposed"] == 1
        assert result["duplicates_skipped"] == 1
        assert result["_diag"]["candidates"][1]["skipped_duplicate"] is True
        assert await pool.fetchval("SELECT count(*) FROM factor_proposals") == 1
    finally:
        await pool.close()


async def test_factor_lab_dedup_serializes_concurrent_writers(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        results = await asyncio.gather(*(
            factor_lab._insert_pending_if_new(pool, expression, [], {}, {})
            for expression in ("rank( close )", "rank(close)")
        ))
        assert sorted(results) == [False, True]
        assert await pool.fetchval("SELECT count(*) FROM factor_proposals") == 1
    finally:
        await pool.close()


@pytest.mark.parametrize(("base_mean", "r_mean", "accepted"), [
    (-7.01, -0.1, False),
    (-7.01, 0.0, False),
    (-7.01, 0.55, True),
    (0.0, -0.1, False),
    (0.0, 0.0, False),
    (0.0, 0.1, True),
    (1.0, 0.55, False),
    (1.0, 0.6, False),
    (1.0, 0.61, True),
])
async def test_factor_lab_mean_gate_and_evidence(applied_db, monkeypatch, base_mean, r_mean, accepted):
    monkeypatch.setitem(_SHARPES, "rank(returns)", [base_mean] * 3)
    monkeypatch.setitem(_SHARPES, "ts_mean(vwap, 20)", [r_mean] * 3)
    # Isolate the mean gate: the independent DSR gate passes every candidate.
    monkeypatch.setattr(factor_lab, "deflated_sharpe_lite", lambda *args: 0.0)
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        result = await factor_lab._evaluate_and_record(
            pool, [RawProposal(expression="ts_mean(vwap, 20)", new_operators=[])], _Diag(),
        )
        threshold = base_mean * 0.6 if base_mean > 0 else 0.0
        assert result["proposed"] == int(accepted)
        assert result["_diag"]["base_threshold"] == pytest.approx(threshold)
        assert result["_diag"]["gate_version"] == "dsr_lite_v2_nonneg_floor"
        candidate = result["_diag"]["candidates"][0]
        assert candidate["passes_mean"] is accepted
        assert candidate["base_threshold"] == pytest.approx(threshold)
        assert candidate["gate_version"] == "dsr_lite_v2_nonneg_floor"
        rows = await pool.fetch("SELECT evidence FROM factor_proposals")
        assert len(rows) == int(accepted)
        if accepted:
            evidence = json.loads(rows[0]["evidence"])
            assert evidence["gate_version"] == "dsr_lite_v2_nonneg_floor"
            assert evidence["base_threshold"] == pytest.approx(threshold)
    finally:
        await pool.close()
