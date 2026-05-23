import asyncpg
import pytest

from alpha_agent.core.factor_ast import (
    BUILTIN_OPS,
    get_allowed_ops,
    refresh_allowed_ops,
)


@pytest.mark.asyncio
async def test_baseline_whitelist_is_builtin_only(applied_db):
    """Before any extended operators are registered, the whitelist equals
    the static built-ins (no DB-injected names)."""
    await refresh_allowed_ops(applied_db)
    assert get_allowed_ops() == BUILTIN_OPS


@pytest.mark.asyncio
async def test_refresh_picks_up_extended_operators(applied_db):
    """After inserting an extended_operators row, refresh_allowed_ops folds
    its name into the whitelist; new validations now accept it."""
    conn = await asyncpg.connect(applied_db)
    try:
        pid = await conn.fetchval(
            "INSERT INTO factor_proposals (expression, new_operators, evidence, diagnostic) "
            "VALUES ('x', '[]'::jsonb, '{}'::jsonb, '{}'::jsonb) RETURNING id"
        )
        await conn.execute(
            "INSERT INTO extended_operators (name, signature, python_impl, doc, "
            "registered_by, source_proposal_id) VALUES "
            "('lf_demo_op', '(x) -> x', 'def lf_demo_op(x): return x', 'demo', 0, $1)",
            pid,
        )
    finally:
        await conn.close()
    await refresh_allowed_ops(applied_db)
    ops = get_allowed_ops()
    assert "lf_demo_op" in ops
    assert BUILTIN_OPS.issubset(ops)


@pytest.mark.asyncio
async def test_refresh_idempotent(applied_db):
    """Calling refresh twice with no DB change leaves the whitelist identical."""
    await refresh_allowed_ops(applied_db)
    first = get_allowed_ops()
    await refresh_allowed_ops(applied_db)
    second = get_allowed_ops()
    assert first == second
