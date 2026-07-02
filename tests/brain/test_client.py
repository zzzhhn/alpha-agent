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
