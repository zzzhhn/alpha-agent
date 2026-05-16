import json
from datetime import datetime, UTC
from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
def fake_pool():
    """A pool that returns 3 pending news_items + 2 pending macro_events,
    and records UPDATE calls."""
    pool = MagicMock()
    news_pending = [
        {"id": 1, "ticker": "AAPL", "headline": "Apple beats earnings"},
        {"id": 2, "ticker": "AAPL", "headline": "AAPL: Buffett trims"},
        {"id": 3, "ticker": "NVDA", "headline": "NVDA in massive AI deal"},
    ]
    macro_pending = [
        {"id": 101, "title": "Apple should make iPhones in America",
         "body": "Apple should make...", "author": "trump"},
        {"id": 102, "title": "Fed maintains policy rate", "body": "...",
         "author": "fed"},
    ]
    # Two sequential fetches: news first, then macro.
    pool.fetch = AsyncMock(side_effect=[news_pending, macro_pending])
    pool.execute = AsyncMock()
    return pool


@pytest.fixture
def fake_llm_with_canned_responses():
    """The worker batches news first then macro. Two canned LLM responses."""
    llm = MagicMock()
    news_resp = MagicMock()
    news_resp.content = json.dumps([
        {"id": 1, "sentiment_score": 0.5, "sentiment_label": "pos"},
        {"id": 2, "sentiment_score": -0.2, "sentiment_label": "neg"},
        {"id": 3, "sentiment_score": 0.8, "sentiment_label": "pos"},
    ])
    macro_resp = MagicMock()
    macro_resp.content = json.dumps([
        {"id": 101, "tickers": ["AAPL"], "sectors": ["Information Technology"],
         "sentiment_score": -0.3},
        {"id": 102, "tickers": [], "sectors": ["Financials"],
         "sentiment_score": 0.0},
    ])
    llm.chat = AsyncMock(side_effect=[news_resp, macro_resp])
    return llm


async def test_enrich_pending_processes_news_and_macro(
    fake_pool, fake_llm_with_canned_responses, monkeypatch
):
    from alpha_agent.news import llm_worker

    monkeypatch.setattr(llm_worker, "_build_llm_client",
                        lambda: fake_llm_with_canned_responses)

    n_proc, n_fail = await llm_worker.enrich_pending(fake_pool, row_limit=100)
    assert n_proc == 5
    assert n_fail == 0
    # 5 UPDATEs (3 news + 2 macro).
    assert fake_pool.execute.await_count == 5


async def test_enrich_pending_handles_malformed_llm_response(
    fake_pool, monkeypatch
):
    """If LLM returns non-JSON, the worker leaves rows untouched and
    counts the batch as failed (NOT a row-level retry cap; the same rows
    are picked up next cron tick)."""
    from alpha_agent.news import llm_worker

    bad_llm = MagicMock()
    bad_resp = MagicMock()
    bad_resp.content = "this is not JSON"
    bad_llm.chat = AsyncMock(return_value=bad_resp)
    monkeypatch.setattr(llm_worker, "_build_llm_client", lambda: bad_llm)

    n_proc, n_fail = await llm_worker.enrich_pending(fake_pool, row_limit=100)
    assert n_proc == 0
    assert n_fail >= 1
    # No UPDATEs at all (rows stay with llm_processed_at = NULL).
    assert fake_pool.execute.await_count == 0


async def test_enrich_pending_respects_row_limit(fake_pool, monkeypatch):
    """row_limit=100 caps how many pending rows are pulled per cron tick.
    The SQL LIMIT clause must reference this value."""
    from alpha_agent.news import llm_worker

    # Asserting the SQL pattern is enough; we mock fetch so the actual
    # SQL is captured in the call args.
    fake_pool.fetch = AsyncMock(side_effect=[[], []])
    fake_llm = MagicMock()
    fake_llm.chat = AsyncMock()
    monkeypatch.setattr(llm_worker, "_build_llm_client", lambda: fake_llm)

    await llm_worker.enrich_pending(fake_pool, row_limit=42)
    # Inspect the first fetch call's SQL (the news_items query).
    args, kwargs = fake_pool.fetch.await_args_list[0]
    assert "LIMIT 42" in args[0]
