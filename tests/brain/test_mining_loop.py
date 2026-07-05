"""Phase E4: the BRAIN mining round. Driven by a fake BrainClient (no network),
it must bucket each candidate into passed / flagged (self-correlated) / rejected
(below gates) / sim_error and persist every outcome to brain_alphas. Plus unit
coverage of the cumulative-PnL -> daily-return conversion the self-corr uses."""
import asyncpg
import pytest

from alpha_agent.brain import store
from alpha_agent.brain.client import AlphaMetrics, BrainSimulationError
from alpha_agent.brain.mining_loop import pnl_to_daily_returns, run_mining_round


# ── PnL -> daily returns ──────────────────────────────────────────────────
def _records(cum: list[float]) -> dict:
    return {"records": [[f"d{i}", v] for i, v in enumerate(cum)]}


def test_pnl_to_daily_returns_diffs_cumulative():
    r = pnl_to_daily_returns(_records([0, 1, 3, 4, 6]))
    assert r is not None
    assert list(r) == [1.0, 2.0, 1.0, 2.0]


def test_pnl_to_daily_returns_none_when_short_or_flat():
    assert pnl_to_daily_returns({"records": [[0, 0]]}) is None       # too short
    assert pnl_to_daily_returns(_records([1, 1, 1, 1, 1])) is None   # flat -> std 0
    assert pnl_to_daily_returns({}) is None                          # no records


# ── the round ─────────────────────────────────────────────────────────────
_PASS = AlphaMetrics("x", sharpe=1.6, fitness=1.2, turnover=0.1, returns=0.2, drawdown=0.05)
_FAIL = AlphaMetrics("x", sharpe=0.5, fitness=1.2, turnover=0.1, returns=0.2, drawdown=0.05)

# E1 (an existing ACTIVE alpha) daily returns = [1,2,1,2,1,2,1]
_E1_CUM = [0, 1, 3, 4, 6, 7, 9, 10]


class _FakeBrain:
    """Responds per simulate() call from a fixed list of outcomes. Each outcome:
    {'fail': bool, 'metrics': AlphaMetrics, 'pnl': recordset|None}."""

    def __init__(self, outcomes):
        self._outcomes = outcomes
        self._i = 0
        self._by_alpha: dict[str, dict] = {}
        self._n = 0

    async def authenticate(self):
        pass

    async def list_active_alphas(self):
        return [{"id": "E1"}]

    async def get_pnl(self, alpha_id):
        if alpha_id == "E1":
            return _records(_E1_CUM)
        return self._by_alpha.get(alpha_id, {}).get("pnl") or {"records": []}

    async def simulate(self, expr, settings):
        oc = self._outcomes[self._i]
        self._i += 1
        if oc.get("fail"):
            raise BrainSimulationError("sim boom")
        self._n += 1
        aid = f"A{self._n}"
        self._by_alpha[aid] = oc
        self._by_alpha[f"sim{self._n}"] = {**oc, "alpha_id": aid}
        return f"sim{self._n}"

    async def poll_simulation(self, sim_id, *, interval_s=8.0, max_wait_s=600.0):
        return {"status": "COMPLETE", "alpha": self._by_alpha[sim_id]["alpha_id"]}

    async def get_alpha_metrics(self, alpha_id):
        return self._by_alpha[alpha_id]["metrics"]

    async def get_self_correlation(self, alpha_id, **kw):
        # Test double: BRAIN's dedicated /correlations/self value, if the outcome
        # provides one (None → loop falls back to the local PnL approximation).
        return self._by_alpha.get(alpha_id, {}).get("brain_corr")

    async def fetch_alpha_expressions(self, **kw):
        return list(getattr(self, "_seed_alphas", []))

    async def fetch_data_fields(self, **kw):
        return list(getattr(self, "_data_fields", []))


@pytest.mark.asyncio
async def test_run_mining_round_buckets_and_persists(applied_db):
    outcomes = [
        {"metrics": _PASS, "pnl": {"records": []}},   # low/absent corr -> passed
        {"metrics": _PASS, "pnl": _records(_E1_CUM)},  # corr ~1 vs E1 -> flagged
        {"metrics": _FAIL, "pnl": {"records": []}},    # below gates -> rejected
        {"fail": True},                                # sim raises -> sim_error
    ]
    client = _FakeBrain(outcomes)
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        summary = await run_mining_round(
            client, pool, user_id=1, n_candidates=4, rng_seed=1
        )
        assert summary == {
            "generated": 4, "passed": 1, "flagged": 1, "rejected": 1, "sim_error": 1,
        }

        rows = await store.list_brain_alphas(pool, 1)
        by_outcome = {r["outcome"]: r for r in rows}
        assert set(by_outcome) == {"passed", "flagged", "rejected", "sim_error"}
        assert by_outcome["passed"]["sharpe"] == 1.6
        # E1 is an ACTIVE alpha but BRAIN gave no official value here, so the
        # correlation surfaces in the ADJUSTED column (local vs the accepted set).
        assert by_outcome["flagged"]["self_correlation_adj"] > 0.7
        assert by_outcome["flagged"]["self_correlation_adj_with"] == "E1"
        assert by_outcome["sim_error"]["alpha_id"] is None
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_brain_authoritative_self_corr_flags(applied_db):
    """When BRAIN reports its OWN self-correlation (via /correlations/self here),
    that value gates — a near-duplicate of the user's own alphas (the seeding
    concern) is flagged even though the local ACTIVE set wouldn't catch it."""
    client = _FakeBrain([
        {"metrics": _PASS, "pnl": {"records": []}, "brain_corr": 0.88},  # BRAIN says redundant
        {"metrics": _PASS, "pnl": {"records": []}, "brain_corr": 0.20},  # BRAIN says fresh
    ])
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        summary = await run_mining_round(
            client, pool, user_id=1, n_candidates=2, rng_seed=1
        )
        assert summary["flagged"] == 1 and summary["passed"] == 1
        rows = {r["outcome"]: r for r in await store.list_brain_alphas(pool, 1)}
        assert rows["flagged"]["self_correlation"] == 0.88
        assert rows["flagged"]["self_correlation_with"] == "BRAIN"  # authoritative source
        assert rows["passed"]["self_correlation"] == 0.20
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_intra_batch_diversity_flags_near_duplicate(applied_db):
    """Diversification fix: two candidates in the SAME round with ~identical daily
    returns — the first passes, the second is flagged as a near-duplicate even
    though neither correlates with any ACTIVE alpha (BRAIN's own check scores both
    ~0 pre-submit). The 'passed' set must be mutually decorrelated."""
    dup = _records([0, 1, 3, 4, 6, 7, 9, 10])     # daily [1,2,1,2,1,2,1]
    diff = _records([0, 1, 2, 4, 6, 9, 12, 16])   # daily [1,1,2,2,3,3,4] — low corr
    client = _FakeBrain([
        {"metrics": _PASS, "pnl": dup},   # first -> passed, seeds the accepted set
        {"metrics": _PASS, "pnl": dup},   # identical returns -> flagged (intra-batch)
        {"metrics": _PASS, "pnl": diff},  # decorrelated -> passed
    ])

    async def _no_active():
        return []

    client.list_active_alphas = _no_active  # no ACTIVE alphas to compare against
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        summary = await run_mining_round(
            client, pool, user_id=1, n_candidates=3, rng_seed=1
        )
        assert summary["passed"] == 2 and summary["flagged"] == 1
        flagged = [r for r in await store.list_brain_alphas(pool, 1)
                   if r["outcome"] == "flagged"]
        assert len(flagged) == 1
        # near-dup of the first passer (A1, an unsubmitted factor) → adjusted column
        assert flagged[0]["self_correlation_adj"] > 0.7
        assert flagged[0]["self_correlation_adj_with"] == "A1"
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_reconcile_self_corr_across_passed_set(applied_db):
    """After a round, an EARLY passer's self-correlation reflects a LATER passer
    (the per-row value is otherwise frozen at mining time). Two moderately
    correlated passers (~0.24, both under the 0.7 gate) end up BOTH showing that
    correlation — neither stays at the mining-time 0.00."""
    b = _records([0, 1, 3, 4, 7, 8, 10, 13])   # daily [1,2,1,3,1,2,3]
    c = _records([0, 3, 4, 6, 9, 10, 13, 15])  # daily [3,1,2,3,1,3,2]  corr(b,c)=0.235
    client = _FakeBrain([
        {"metrics": _PASS, "pnl": b},   # first passer -> mining-time self_corr 0
        {"metrics": _PASS, "pnl": c},   # second passer -> 0.235 vs the first
    ])

    async def _no_active():
        return []

    client.list_active_alphas = _no_active
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        summary = await run_mining_round(client, pool, user_id=1, n_candidates=2, rng_seed=1)
        assert summary["passed"] == 2 and summary["flagged"] == 0
        passed = [r for r in await store.list_brain_alphas(pool, 1)
                  if r["outcome"] == "passed"]
        assert len(passed) == 2
        # BOTH reflect the mutual correlation in the ADJUSTED column after
        # reconciliation — neither frozen at the mining-time 0.00.
        assert all(0.2 < r["self_correlation_adj"] < 0.3 for r in passed)
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_smart_retry_flips_turnover_near_miss(applied_db):
    """A candidate failing ONLY on turnover at base settings is re-simulated once
    with higher decay; when the retry clears the gate it's recorded as passed with
    the WINNING (higher-decay) settings."""
    near_miss = AlphaMetrics("x", sharpe=1.6, fitness=1.2, turnover=0.5,
                             returns=0.2, drawdown=0.05)
    client = _FakeBrain([
        {"metrics": near_miss, "pnl": {"records": []}},  # base: turnover 0.5 -> fail
        {"metrics": _PASS, "pnl": {"records": []}},        # retry (more decay) -> pass
    ])

    async def _no_active():
        return []

    client.list_active_alphas = _no_active
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        summary = await run_mining_round(client, pool, user_id=1, n_candidates=1, rng_seed=1)
        assert summary["passed"] == 1 and summary["rejected"] == 0
        row = [r for r in await store.list_brain_alphas(pool, 1)
               if r["outcome"] == "passed"][0]
        assert row["turnover"] == _PASS.turnover      # the retry's metrics won
        assert int(row["settings"]["decay"]) >= 12    # higher-decay variant stored
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_no_retry_for_hopeless_miss(applied_db):
    """A catastrophic miss (Sharpe far below the gate) is not worth a retry sim —
    rejected after the single base simulation (no second sim consumed)."""
    hopeless = AlphaMetrics("x", sharpe=0.3, fitness=0.2, turnover=0.1,
                            returns=0.05, drawdown=0.05)
    client = _FakeBrain([{"metrics": hopeless, "pnl": {"records": []}}])  # ONE outcome

    async def _no_active():
        return []

    client.list_active_alphas = _no_active
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        summary = await run_mining_round(client, pool, user_id=1, n_candidates=1, rng_seed=1)
        assert summary["rejected"] == 1 and summary["passed"] == 0
        assert client._n == 1  # only the base sim ran; no retry
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_mark_submitted(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        rid = await store.record_brain_alpha(
            pool, user_id=1, expression="rank(returns)", settings={"decay": 0},
            outcome="passed", alpha_id="A1", sharpe=1.5, fitness=1.2, turnover=0.1,
        )
        await store.mark_submitted(pool, rid, brain_status="ACTIVE")
        row = (await store.list_brain_alphas(pool, 1))[0]
        assert row["submitted_at"] is not None
        assert row["brain_status"] == "ACTIVE"
        assert row["settings"] == {"decay": 0}  # jsonb decoded
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_get_brain_alpha_scoped_to_owner(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        rid = await store.record_brain_alpha(
            pool, user_id=1, expression="rank(vwap)", settings={"decay": 5},
            outcome="passed", alpha_id="A9", sharpe=1.7,
        )
        got = await store.get_brain_alpha(pool, 1, rid)
        assert got["alpha_id"] == "A9" and got["settings"] == {"decay": 5}
        # another user cannot read it
        assert await store.get_brain_alpha(pool, 2, rid) is None
        # unknown id
        assert await store.get_brain_alpha(pool, 1, 999999) is None
    finally:
        await pool.close()
