"""POST /api/news/enrich/{ticker} - read-time BYOK enrichment.

Authenticated users trigger this from the stock page to enrich any
news_items for the given ticker that have not yet been LLM-processed.
The user's stored BYOK key is used (no global server-side key); this
is the read-time replacement for the removed news_llm_enrich cron.

Failure modes (inherited from get_llm_client):
  401 - missing/invalid Bearer token
  400 - user has no BYOK key stored (front-end should show "Add LLM
        key in Settings" CTA)
  500 - BYOK_MASTER_KEY missing on server

On success: returns counts of how many news_items were processed.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query
from pydantic import BaseModel

from alpha_agent.api.byok import get_llm_client
from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.llm.base import LLMClient
from alpha_agent.news.llm_worker import enrich_news_for_ticker

router = APIRouter(prefix="/api/news", tags=["news"])


class EnrichResponse(BaseModel):
    ticker: str
    enriched: int
    failed_batches: int


@router.post("/enrich/{ticker}", response_model=EnrichResponse)
async def enrich(
    ticker: str = Path(min_length=1, max_length=10),
    lang: str = Query("en", pattern="^(en|zh)$"),
    llm: LLMClient = Depends(get_llm_client),
) -> EnrichResponse:
    """Run the BYOK LLM enrichment over un-processed news_items for `ticker`.

    `lang` controls the language of the per-headline reasoning text the LLM
    writes into news_items.reasoning_text (V007 column). The frontend
    NewsBlock passes the user's active locale so the analyst commentary
    matches the UI; older clients that don't send it default to English.
    """
    pool = await get_db_pool()
    t = ticker.upper()
    n_proc, n_failed = await enrich_news_for_ticker(pool, llm, t, lang=lang)
    return EnrichResponse(ticker=t, enriched=n_proc, failed_batches=n_failed)
