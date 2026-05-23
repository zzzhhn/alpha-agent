import pytest

from alpha_agent.evolution.diagnostics import Diagnostic, compute_diagnostic
from alpha_agent.storage.postgres import close_pool, get_pool


@pytest.fixture
async def pool(applied_db):
    p = await get_pool(applied_db)
    yield p
    await close_pool()


@pytest.mark.asyncio
async def test_diagnostic_returns_struct_with_current_expression(pool):
    """Cognitive load UX: even on a fresh DB with zero IC history, the
    Diagnostic carries the current expression so the LLM prompt has a
    stable shape."""
    d = await compute_diagnostic(pool)
    assert isinstance(d, Diagnostic)
    assert isinstance(d.current_expression, str)
    assert len(d.current_expression) > 0
    assert d.weak_signal is None  # no history seeded
    assert isinstance(d.symptom_summary, str)


@pytest.mark.asyncio
async def test_diagnostic_picks_lowest_ic_signal_when_history_present(pool):
    """Seed two signals at the 30d window; diagnostic picks the lower-IC one."""
    await pool.execute(
        "INSERT INTO signal_ic_history (signal_name, window_days, ic, n_observations, computed_at) "
        "VALUES ('alpha', 30, 0.04, 100, now()), ('beta', 30, 0.005, 100, now())"
    )
    d = await compute_diagnostic(pool)
    assert d.weak_signal == "beta"
    assert d.weak_signal_ic is not None
    assert d.weak_signal_ic < 0.04


@pytest.mark.asyncio
async def test_diagnostic_is_jsonable(pool):
    """The Diagnostic must serialize to JSON-compatible dict via to_jsonable()
    because T5 returns it as the body of GET /api/factor-lab/diagnostic."""
    import json
    d = await compute_diagnostic(pool)
    payload = d.to_jsonable()
    json.dumps(payload)  # must not raise
    assert "current_expression" in payload
    assert "weak_signal" in payload
    assert "symptom_summary" in payload
