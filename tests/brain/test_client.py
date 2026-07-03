"""Phase E1: the WorldQuant BRAIN API client. Exercised entirely against an
httpx MockTransport (no network), covering auth, the simulate->poll->metrics
flow, ACTIVE-alpha filtering, submit, and the in-sample gate thresholds."""
import httpx
import pytest

from alpha_agent.brain.client import (
    AlphaMetrics,
    BrainAuthError,
    BrainClient,
    BrainSimulationError,
    BRAIN_API_BASE,
)


def _client(handler) -> BrainClient:
    ac = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url=BRAIN_API_BASE
    )
    return BrainClient("u", "p", client=ac)


# ── auth ──────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_authenticate_ok():
    c = _client(lambda req: httpx.Response(201))
    await c.authenticate()  # no raise
    await c.aclose()


@pytest.mark.asyncio
async def test_authenticate_bad_credentials_raises():
    c = _client(lambda req: httpx.Response(401))
    with pytest.raises(BrainAuthError):
        await c.authenticate()
    await c.aclose()


# ── simulate + poll ───────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_simulate_parses_sim_id_from_location():
    def h(req):
        assert req.url.path == "/simulations"
        return httpx.Response(201, headers={"Location": "/simulations/SIM123"})

    c = _client(h)
    assert await c.simulate("rank(returns)") == "SIM123"
    await c.aclose()


@pytest.mark.asyncio
async def test_poll_pending_then_complete_returns_alpha():
    calls = {"n": 0}

    def h(req):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(200, json={"status": "PENDING"})
        return httpx.Response(200, json={"status": "COMPLETE", "alpha": "A1"})

    c = _client(h)
    data = await c.poll_simulation("SIM", interval_s=0, max_wait_s=100)
    assert data["alpha"] == "A1"
    assert calls["n"] == 3
    await c.aclose()


@pytest.mark.asyncio
async def test_poll_warning_is_terminal_success():
    """BRAIN's WARNING is a terminal state that still yields an alpha (completed
    with warnings). It must return, not poll to timeout — this was the 7/8
    sim_error in run #1."""
    c = _client(
        lambda req: httpx.Response(200, json={"status": "WARNING", "alpha": "A2"})
    )
    data = await c.poll_simulation("SIM", interval_s=0, max_wait_s=100)
    assert data["alpha"] == "A2"
    await c.aclose()


@pytest.mark.asyncio
async def test_poll_returns_when_alpha_present_regardless_of_status():
    c = _client(
        lambda req: httpx.Response(200, json={"status": "SOMETHING", "alpha": "A3"})
    )
    data = await c.poll_simulation("SIM", interval_s=0, max_wait_s=100)
    assert data["alpha"] == "A3"
    await c.aclose()


@pytest.mark.asyncio
async def test_poll_failed_raises():
    c = _client(
        lambda req: httpx.Response(200, json={"status": "FAILED", "message": "bad expr"})
    )
    with pytest.raises(BrainSimulationError):
        await c.poll_simulation("SIM", interval_s=0)
    await c.aclose()


@pytest.mark.asyncio
async def test_poll_timeout_raises():
    c = _client(lambda req: httpx.Response(200, json={"status": "PENDING"}))
    with pytest.raises(BrainSimulationError):
        await c.poll_simulation("SIM", interval_s=0, max_wait_s=0)
    await c.aclose()


# ── read metrics / alphas / submit ────────────────────────────────────────
@pytest.mark.asyncio
async def test_get_alpha_metrics_parses_is_block():
    def h(req):
        return httpx.Response(
            200,
            json={"is": {"sharpe": 1.5, "fitness": 1.2, "turnover": 0.1,
                         "returns": 0.2, "drawdown": 0.08}},
        )

    c = _client(h)
    m = await c.get_alpha_metrics("A1")
    assert m.sharpe == 1.5 and m.fitness == 1.2 and m.passes_gates()
    await c.aclose()


@pytest.mark.asyncio
async def test_get_alpha_metrics_parses_brain_checks():
    """BRAIN's is.checks array is the authoritative gate verdict; SELF_CORRELATION
    is one of the checks. passes_gates() must honour it (excluding self-corr)."""
    def h(req):
        return httpx.Response(200, json={"is": {
            "sharpe": 1.5, "fitness": 1.2, "turnover": 0.1, "drawdown": 0.05,
            "checks": [
                {"name": "LOW_SHARPE", "result": "PASS", "value": 1.5},
                {"name": "LOW_FITNESS", "result": "PASS", "value": 1.2},
                {"name": "SELF_CORRELATION", "result": "FAIL", "value": 0.82},
            ],
        }})

    c = _client(h)
    m = await c.get_alpha_metrics("A1")
    assert m.brain_self_correlation() == 0.82
    # self-corr excluded from the merit verdict → PASS on its own metrics
    assert m.brain_checks_verdict() is True
    assert m.passes_gates() is True
    await c.aclose()


@pytest.mark.asyncio
async def test_brain_checks_verdict_pending_is_none():
    m = AlphaMetrics("A", 1.5, 1.2, 0.1, 0.2, 0.05,
                     checks={"LOW_SHARPE": {"result": "PENDING"}})
    assert m.brain_checks_verdict() is None  # can't judge yet


@pytest.mark.asyncio
async def test_get_self_correlation_top_level_max():
    c = _client(lambda req: httpx.Response(200, json={"max": 0.66, "min": -0.2}))
    assert await c.get_self_correlation("A1") == 0.66
    await c.aclose()


@pytest.mark.asyncio
async def test_get_self_correlation_202_then_ready():
    calls = {"n": 0}

    def h(req):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(202, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"max": 0.71, "min": -0.1, "records": [[0.1, 0.2, 3]]})

    c = _client(h)
    # polls past the 202, then reads the authoritative top-level max
    assert await c.get_self_correlation("A1", interval_s=0) == 0.71
    assert calls["n"] == 2
    await c.aclose()


@pytest.mark.asyncio
async def test_get_self_correlation_none_when_no_top_level_max():
    # histogram-only body (no top-level max) → None, so the caller falls back to
    # the local approximation rather than mis-reading a bucket count as a corr.
    c = _client(lambda req: httpx.Response(200, json={"records": [[0.1, 0.2, 1]]}))
    assert await c.get_self_correlation("A1", interval_s=0) is None
    await c.aclose()


@pytest.mark.asyncio
async def test_list_active_alphas_filters_status():
    def h(req):
        return httpx.Response(200, json={"results": [
            {"id": "A1", "status": "ACTIVE"},
            {"id": "A2", "status": "UNSUBMITTED"},
            {"id": "A3", "status": "active"},  # case-insensitive
        ]})

    c = _client(h)
    active = await c.list_active_alphas()
    assert sorted(a["id"] for a in active) == ["A1", "A3"]
    await c.aclose()


@pytest.mark.asyncio
async def test_fetch_alpha_expressions_paginates_and_extracts_code():
    """Seeds = the FASTEXPR at alpha['regular']['code'], across pages."""
    def h(req):
        offset = int(dict(req.url.params).get("offset", "0"))
        if offset == 0:
            return httpx.Response(200, json={"results": [
                {"regular": {"code": "rank(returns)"}},
                {"regular": {"code": "ts_mean(vwap, 20)"}},
                {"regular": None},  # skipped (no code)
            ]})
        if offset == 50:
            return httpx.Response(200, json={"results": [
                {"regular": {"code": "group_rank(returns, sector)"}},
            ]})
        return httpx.Response(200, json={"results": []})  # end

    c = _client(h)
    exprs = await c.fetch_alpha_expressions(limit=200, page_size=50)
    assert exprs == [
        "rank(returns)", "ts_mean(vwap, 20)", "group_rank(returns, sector)",
    ]
    await c.aclose()


@pytest.mark.asyncio
async def test_submit_true_on_201():
    c = _client(lambda req: httpx.Response(201))
    assert await c.submit("A1") is True
    await c.aclose()


# ── gate logic (no I/O) ───────────────────────────────────────────────────
def test_passes_gates_enforces_all_thresholds():
    assert AlphaMetrics("A", 1.3, 1.15, 0.2, 0.2, 0.1).passes_gates()
    assert not AlphaMetrics("A", 1.0, 1.15, 0.2, 0.2, 0.1).passes_gates()  # sharpe
    assert not AlphaMetrics("A", 1.3, 1.0, 0.2, 0.2, 0.1).passes_gates()   # fitness
    assert not AlphaMetrics("A", 1.3, 1.15, 0.5, 0.2, 0.1).passes_gates()  # turnover
    assert not AlphaMetrics("A", 1.3, 1.15, 0.2, 0.2, 0.3).passes_gates()  # drawdown
    assert not AlphaMetrics("A", None, 1.15, 0.2, 0.2, 0.1).passes_gates()  # missing
