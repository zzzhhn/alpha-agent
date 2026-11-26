"""V063 preserves previously recorded BRAIN results and research evidence."""
import asyncpg

from alpha_agent.storage.migrations import runner


async def test_v063_leaves_historical_diversity_evidence_unavailable(test_db_url, monkeypatch):
    discover = runner._discover
    v063 = "V063__brain_diversity_evidence"
    with monkeypatch.context() as prior:
        prior.setattr(runner, "_discover", lambda: [
            (version, path) for version, path in discover() if version[:4] < "V063"
        ])
        await runner.apply_migrations(test_db_url)

    conn = await asyncpg.connect(test_db_url)
    try:
        row_id = await conn.fetchval("""
            INSERT INTO brain_alphas (
                user_id, expression, outcome, self_correlation_adj, research_evidence
            )
            VALUES (1, 'rank(returns)', 'passed', 0.55, '{"context_key": "existing-test"}')
            RETURNING id
        """)
        assert v063 in await runner.apply_migrations(test_db_url)
        row = await conn.fetchrow(
            "SELECT self_correlation_adj, research_evidence->>'context_key' AS context_key, "
            "diversity_evidence FROM brain_alphas WHERE id=$1",
            row_id,
        )
        assert (row["self_correlation_adj"], row["context_key"], row["diversity_evidence"]) == (
            0.55, "existing-test", None,
        )
        assert await runner.apply_migrations(test_db_url) == []
    finally:
        await conn.close()
