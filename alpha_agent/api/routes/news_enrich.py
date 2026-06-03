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

import asyncio
import os
import sys

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from alpha_agent.api.byok import _build_byok_client, get_llm_client
from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.api.sse import SSE_HEADERS, sse_format
from alpha_agent.auth.crypto_box import CryptoError, decrypt
from alpha_agent.auth.dependencies import require_user
from alpha_agent.llm.base import LLMClient
from alpha_agent.news.llm_worker import (
    enrich_news_for_ticker,
    enrich_news_for_ticker_stream,
)

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


@router.post("/enrich/{ticker}/stream")
async def enrich_stream(
    ticker: str = Path(min_length=1, max_length=10),
    lang: str = Query("en", pattern="^(en|zh)$"),
    user_id: int = Depends(require_user),
) -> StreamingResponse:
    """SSE-streaming sibling of `enrich` (mirrors the Rich Brief streaming
    pattern).

    Streams one event per enrichment batch as it completes so the news list
    fills in progressively *in place* (no full-page reload). Auth is
    required; the BYOK key is fetched + decrypted server-side from the
    authenticated user's stored credentials, exactly like
    `brief.post_brief_stream` — the key never leaves the server and decrypt
    failures degrade into an SSE `error` event rather than a 500 to a blank
    UI. No-key still returns a pre-stream 400 (the frontend maps it to the
    existing "configure key" CTA).

    Granularity note: news enrichment is structurally a *batch* LLM call
    (15 headlines → one JSON array, parsed in one shot), so true per-item
    streaming is not possible without N× the token spend. The honest
    equivalent implemented here is per-batch progress: each `items` event
    carries every row that batch enriched and the consumer splices them in
    place. With ≤15 unenriched headlines (the common case) this is a single
    `items` event followed by `done`.
    """
    ticker = ticker.upper()
    pool = await get_db_pool()

    byok = await pool.fetchrow(
        "SELECT provider, ciphertext, nonce, model, base_url "
        "FROM user_byok WHERE user_id = $1 LIMIT 1",
        user_id,
    )
    if byok is None:
        raise HTTPException(
            status_code=400, detail="No BYOK key set; visit /settings to add one"
        )

    master = os.environ.get("BYOK_MASTER_KEY")
    if not master:
        raise HTTPException(status_code=500, detail="BYOK_MASTER_KEY not configured")

    async def generator():
        try:
            plaintext_key = decrypt(byok["ciphertext"], byok["nonce"], master.encode("utf-8"))
        except CryptoError:
            yield sse_format({
                "type": "error",
                "message": "Stored key cannot be decrypted. Please re-save it in /settings.",
            })
            return
        client = _build_byok_client(
            provider=byok["provider"],
            api_key=plaintext_key,
            api_base=byok["base_url"],
            model=byok["model"],
        )
        try:
            async for event in enrich_news_for_ticker_stream(
                pool, client, ticker, lang=lang,
            ):
                yield sse_format(event)
                await asyncio.sleep(0)
            await pool.execute(
                "UPDATE user_byok SET last_used_at = now() "
                "WHERE user_id = $1 AND provider = $2",
                user_id, byok["provider"],
            )
        except Exception as e:
            print(
                f"news enrich stream error: {type(e).__name__}: {e}",
                file=sys.stderr, flush=True,
            )
            yield sse_format({
                "type": "error",
                "message": f"LLM request failed ({type(e).__name__}). Check your key in /settings.",
            })
        finally:
            close = getattr(client, "close", None)
            if close is not None:
                await close()

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )
