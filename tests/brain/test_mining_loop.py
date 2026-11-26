"""Phase E4: the BRAIN mining round. Driven by a fake BrainClient (no network),
it must bucket each candidate into passed / flagged (self-correlated) / rejected
(below gates) / sim_error and persist every outcome to brain_alphas. Plus unit
coverage of the cumulative-PnL -> daily-return conversion the self-corr uses."""
from datetime import date, timedelta
from itertools import accumulate
from random import Random

import asyncpg
import pytest

from alpha_agent.brain import store
from alpha_agent.brain.client import AlphaMetrics, BrainSimulationError
from alpha_agent.brain.mining_loop import run_mining_round
from alpha_agent.brain.pnl import pnl_to_return_intervals


# ── PnL -> daily returns ──────────────────────────────────────────────────
def _records(cum: list[float], *, start: date = date(2025, 1, 1)) -> dict:
    return {"records": [[(start + timedelta(days=i)).isoformat(), value]
                        for i, value in enumerate(cum)]}


def test_pnl_observation_intervals_preserve_gaps():
    pnl = {"records": [
        ["2025-01-06", 105], ["2025-01-02", 100], ["2025-01-03", 101],
        ["2025-01-07", "unavailable"], ["2025-01-08", 108],
    ]}
    returns = pnl_to_return_intervals(pnl)
    assert {" / ".join(day.isoformat() for day in interval): value for interval, value in returns.items()} == {
        "2025-01-02 / 2025-01-03": 1.0,
        "2025-01-03 / 2025-01-06": 4.0,
        "2025-01-06 / 2025-01-08": 3.0,
    }


def test_pnl_observation_intervals_keep_flat_and_short_samples():
    assert pnl_to_return_intervals({"records": [[0, 0]]}) == {}
    assert list(pnl_to_return_intervals(_records([1, 1])).values()) == [0.0]
    assert pnl_to_return_intervals({}) == {}


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
async def test_empty_candidate_pool_marks_ledger_run_failed(applied_db, monkeypatch):
    """A zero-candidate generator result is a failed run, never a successful
    completion with an empty results table."""
    import alpha_agent.brain.mining_loop as mining_loop

    client = _FakeBrain([])
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        run = await store.create_brain_run(
            pool,
            user_id=1,
            source="manual",
            requested_n=5,
            generation_target_n=24,
            family_focus="options",
            seed=1234,
        )
        monkeypatch.setattr(
            mining_loop, "generate_brain_candidates", lambda *args, **kwargs: [],
        )

        with pytest.raises(RuntimeError, match="no usable expressions"):
            await run_mining_round(
                client,
                pool,
                user_id=1,
                n_candidates=5,
                generation_target_n=24,
                family_focus="options",
                run_id=run["id"],
                seed_from_user_alphas=False,
            )

        stored = await store.get_brain_run(pool, run["id"], user_id=1)
        assert stored["status"] == "failed"
        assert stored["generated_n"] == 0
        assert "no usable expressions" in stored["error_detail"]
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
        # max_retries=0: this test asserts the AUTHORITATIVE flag is honored; the
        # settings-axis rescue (a separate path) would otherwise consume the
        # mock's canned responses and convert the flag into a rescue attempt.
        summary = await run_mining_round(
            client, pool, user_id=1, n_candidates=2, rng_seed=1,
            max_retries=0, family_caps={},
        )
        assert summary["flagged"] == 1 and summary["passed"] == 1
        rows = {r["outcome"]: r for r in await store.list_brain_alphas(pool, 1)}
        assert rows["flagged"]["self_correlation"] == 0.88
        assert rows["flagged"]["self_correlation_with"] == "BRAIN"  # authoritative source
        assert rows["passed"]["self_correlation"] == 0.20
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_self_corr_warning_band_does_not_reject(applied_db):
    """0.65–0.70 is advisory only; BRAIN's official 0.70 limit is the gate."""
    client = _FakeBrain([
        {"metrics": _PASS, "pnl": {"records": []}, "brain_corr": 0.68},
    ])
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        summary = await run_mining_round(
            client, pool, user_id=1, n_candidates=1, rng_seed=1,
            max_retries=0, family_caps={},
        )
        assert summary["passed"] == 1 and summary["flagged"] == 0
        row = (await store.list_brain_alphas(pool, 1))[0]
        assert row["self_correlation"] == 0.68
        assert "near official limit" in row["detail"]
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
        # Permissive family caps: isolate the CORR near-dup behavior from the
        # separate family-saturation gate (tested elsewhere).
        summary = await run_mining_round(
            client, pool, user_id=1, n_candidates=3, rng_seed=1,
            family_caps={"value": 99, "options": 99, "revision": 99,
                         "momentum": 99, "lowvol": 99, "other": 99},
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
        summary = await run_mining_round(client, pool, user_id=1, n_candidates=2, rng_seed=1, family_caps={})
        assert summary["passed"] == 2 and summary["flagged"] == 0
        passed = [r for r in await store.list_brain_alphas(pool, 1)
                  if r["outcome"] == "passed"]
        assert len(passed) == 2
        # BOTH reflect the mutual correlation in the ADJUSTED column after
        # reconciliation — neither frozen at the mining-time 0.00.
        assert all(0.2 < r["self_correlation_adj"] < 0.3 for r in passed)
        by_id = {r["alpha_id"]: r["diversity_evidence"] for r in passed}
        assert by_id["A1"]["decision"]["adjusted_correlation"]["n"] == 0
        assert by_id["A2"]["decision"]["adjusted_correlation"]["n"] == 7
        for evidence in by_id.values():
            assert evidence["reconciled_adjusted_correlation"]["n"] == 7
    finally:
        await pool.close()


@pytest.mark.asyncio
async def test_smart_retry_flips_turnover_near_miss(applied_db):
    """A candidate failing ONLY on turnover at base settings is re-simulated once
    with higher decay; when the retry clears the gate it's recorded as passed with
    the WINNING (higher-decay) settings."""
    near_miss = AlphaMetrics("x", sharpe=1.6, fitness=1.2, turnover=0.8,
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
async def test_confirmed_submission_keeps_mining_result(applied_db):
    pool = await asyncpg.create_pool(applied_db, min_size=1, max_size=2)
    try:
        rid = await store.record_brain_alpha(
            pool, user_id=1, expression="rank(returns)", settings={"decay": 0},
            outcome="passed", alpha_id="A1", sharpe=1.5, fitness=1.2, turnover=0.1,
        )
        assert await store.claim_brain_submission(pool, 1, rid)
        await store.confirm_brain_submission(pool, 1, rid, status="active")
        row = (await store.list_brain_alphas(pool, 1))[0]
        assert row["submitted_at"] is not None
        assert row["brain_status"] == "active"
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



@pytest.fixture
async def dated_round(applied_db, monkeypatch):
    from alpha_agent.brain import mining_loop

    async with asyncpg.create_pool(applied_db, min_size=1, max_size=3) as pool:
        async def run(outcomes, references, *, family_focus=None, active=None, max_retries=0):
            class Client(_FakeBrain):
                async def list_active_alphas(self):
                    return [{"id": alpha_id} for alpha_id in (references if active is None else active)]

                async def get_pnl(self, alpha_id):
                    if alpha_id in references:
                        return references[alpha_id]
                    return await super().get_pnl(alpha_id)

            monkeypatch.setattr(mining_loop, "generate_brain_candidates",
                                lambda *args, **kwargs: ["rank(returns)"])
            await run_mining_round(
                Client(outcomes), pool, user_id=1, n_candidates=1, rng_seed=1,
                max_retries=max_retries, family_caps={}, seed_from_user_alphas=False,
                family_focus=family_focus,
            )
            return next(row for row in await store.list_brain_alphas(pool, 1)
                        if row["alpha_id"] in {"A1", "A2"})

        yield run, pool


def _series(deltas, *, start=0, stop=None):
    observations = list(accumulate(deltas, initial=100.0))
    return _records(observations[start:stop], start=date(2025, 1, 1) + timedelta(days=start))


def _decisions(row):
    evidence = row["diversity_evidence"]
    assert evidence["method"] == "brain_exact_return_intervals_v1"
    decision = evidence["decision"]
    return decision["adjusted_correlation"], decision["incremental_contribution"]


async def test_disjoint_calendar_windows_do_not_flag_a_candidate(dated_round):
    run, _ = dated_round
    ref = _records([100, 101, 104, 106, 111], start=date(2025, 1, 1))
    candidate = _records([100, 101, 104, 106, 111], start=date(2025, 4, 1))
    row = await run([{"metrics": _PASS, "pnl": candidate}], {"E1": ref})
    assert (row["outcome"], row["self_correlation_adj"]) == ("passed", None)
    correlation, marginal = _decisions(row)
    assert correlation == {"value": None, "against": None, "n": 0}
    assert marginal == {"value": None, "references": [], "n": 0}
    assert row["research_evidence"] is None


async def test_partial_overlap_only_fits_the_shared_window(dated_round):
    run, _ = dated_round
    deltas = [((i * 7) % 23) - 8 for i in range(155)]
    references = {"E1": _series(deltas, start=0, stop=101)}
    candidate = _series(deltas, start=30, stop=151)
    row = await run([{"metrics": _PASS, "pnl": candidate}], references)
    corr, marginal = _decisions(row)
    assert row["outcome"] == "flagged"
    assert corr == {"value": pytest.approx(1.0), "against": "E1", "n": 70}
    assert marginal == {"value": pytest.approx(0.0, abs=1e-12), "references": ["E1"], "n": 70}


async def test_incremental_fit_intersects_all_selected_references(dated_round):
    run, _ = dated_round
    rng = Random(23)
    a = [rng.gauss(0, 1) for _ in range(180)]
    b = [rng.gauss(0, 1) for _ in range(180)]
    combined = [x + y for x, y in zip(a, b, strict=True)]
    references = {
        "E1": _series(a, start=0, stop=121),
        "E2": _series(b, start=50, stop=181),
        "DISJOINT": _records([100, 102, 107, 109], start=date(2024, 1, 1)),
    }
    row = await run([{"metrics": _PASS, "pnl": _series(combined, start=20, stop=151)}], references)
    corr, marginal = _decisions(row)
    assert corr["n"] == 100
    assert set(marginal["references"]) == {"E1", "E2"}
    assert marginal["n"] == 70
    assert marginal["value"] == pytest.approx(0.0, abs=1e-12)
    assert row["outcome"] == "flagged"


@pytest.mark.parametrize(("gap_in_reference", "samples"), [(False, 73), (True, 74)])
async def test_gap_needs_both_return_endpoints_to_match(dated_round, gap_in_reference, samples):
    run, _ = dated_round
    complete = _series([((i * 7) % 23) - 8 for i in range(75)])
    gappy = {"records": complete["records"][:35] + complete["records"][36:]}
    row = await run([{"metrics": _PASS, "pnl": gappy}],
                    {"E1": gappy if gap_in_reference else complete})
    corr, marginal = _decisions(row)
    assert corr["n"] == marginal["n"] == samples
    assert corr["value"] == pytest.approx(1.0)
    assert marginal["value"] == pytest.approx(0.0, abs=1e-12)


async def test_same_window_keeps_correlation_and_reports_short_regression(dated_round):
    run, _ = dated_round
    matching = _records([100, 101, 104, 106, 111])
    row = await run([{"metrics": _PASS, "pnl": matching}], {"E1": matching})
    assert row["outcome"] == "flagged"
    corr, marginal = _decisions(row)
    assert corr == {"value": pytest.approx(1.0), "against": "E1", "n": 4}
    assert marginal == {"value": None, "references": ["E1"], "n": 4}


async def test_two_shared_intervals_are_counted_but_pearson_is_unavailable(dated_round):
    run, _ = dated_round
    complete = _records([100, 101, 104, 106, 111])
    tail = {"records": complete["records"][2:]}
    row = await run([{"metrics": _PASS, "pnl": tail}], {"E1": complete})
    corr, marginal = _decisions(row)
    assert row["outcome"] == "passed"
    assert corr == {"value": None, "against": None, "n": 2}
    assert marginal["value"] is None


async def test_authoritative_correlation_still_flags_without_any_local_overlap(dated_round):
    run, _ = dated_round
    ref = _records([100, 101, 104, 106, 111])
    candidate = _records([100, 101, 104, 106, 111], start=date(2025, 4, 1))
    row = await run([{"metrics": _PASS, "pnl": candidate, "brain_corr": 0.88}], {"E1": ref})
    assert (row["outcome"], row["self_correlation"], row["self_correlation_with"]) == ("flagged", 0.88, "BRAIN")
    corr, marginal = _decisions(row)
    assert corr["value"] is marginal["value"] is None
    assert corr["n"] == marginal["n"] == 0


async def _seed_blend_parents(pool):
    await store.record_brain_alpha(
        pool, user_id=1, expression="rank(returns)", settings={}, alpha_id="P",
        outcome="passed", sharpe=1.3, turnover=0.1,
    )
    await store.record_brain_alpha(
        pool, user_id=1, expression="rank(close)", settings={}, alpha_id="N",
        outcome="rejected", sharpe=1.0, turnover=0.1,
    )


@pytest.mark.parametrize(("official", "outcome"), [(0.3, "passed"), (0.75, "flagged")])
async def test_blend_uses_official_gate_and_excludes_parents_from_both_estimates(dated_round, official, outcome):
    run, pool = dated_round
    await _seed_blend_parents(pool)
    deltas = [((i * 7) % 23) - 8 for i in range(75)]
    parent = _series(deltas)
    external = _series(deltas, start=5)
    row = await run([{"metrics": _PASS, "pnl": parent, "brain_corr": official}],
                    {"E1": external, "P": parent, "N": parent}, active=["E1"],
                    family_focus="blend")
    assert (row["outcome"], row["self_correlation"]) == (outcome, official)
    assert row["blend_parents"] == ["N", "P"]
    corr, marginal = _decisions(row)
    assert corr == {"value": pytest.approx(1.0), "against": "E1", "n": 70}
    assert marginal == {"value": pytest.approx(0.0, abs=1e-12), "references": ["E1"], "n": 70}
    if outcome == "passed":
        assert row["diversity_evidence"]["reconciled_adjusted_correlation"] == corr


async def test_blend_retry_remains_official_only_and_persists_winning_window(dated_round):
    run, pool = dated_round
    await _seed_blend_parents(pool)
    deltas = [((i * 7) % 23) - 8 for i in range(75)]
    same = _series(deltas)
    shorter = _series(deltas, start=10)
    row = await run([
        {"metrics": _PASS, "pnl": same, "brain_corr": 0.75},
        {"metrics": _PASS, "pnl": shorter, "brain_corr": 0.20},
    ], {"E1": same, "P": same}, active=["E1"], family_focus="blend", max_retries=1)
    assert (row["alpha_id"], row["outcome"], row["retried"]) == ("A2", "passed", True)
    assert row["self_correlation"] == 0.20
    corr, marginal = _decisions(row)
    assert corr["n"] == marginal["n"] == 65
    assert corr["against"] == "E1"


async def test_non_blend_axis_retry_uses_new_dates_and_keeps_its_own_evidence(dated_round):
    run, _ = dated_round
    ref = _records([100, 101, 104, 106, 111])
    alternate = _records([100, 101, 104, 106, 111], start=date(2025, 4, 1))
    row = await run([
        {"metrics": _PASS, "pnl": {"records": []}, "brain_corr": 0.75},
        {"metrics": _PASS, "pnl": alternate, "brain_corr": 0.20},
    ], {"E1": ref}, max_retries=1)
    assert (row["alpha_id"], row["outcome"], row["retried"]) == ("A2", "passed", True)
    assert row["self_correlation"] == 0.20
    corr, marginal = _decisions(row)
    assert corr["value"] is marginal["value"] is None
    assert corr["n"] == marginal["n"] == 0
