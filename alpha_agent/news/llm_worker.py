"""BYOK-LLM batch enrichment for news_items + macro_events.

Runs as the news_llm_enrich cron. Picks `row_limit` (default 100) rows
with llm_processed_at IS NULL, batches them through LiteLLMClient
(batch size 15), parses the structured JSON response, writes back.

Error semantics per spec: NO row-level retry cap. A malformed LLM
response leaves the rows untouched so the next cron tick re-picks them.
Backlog visible via /api/_health/news_freshness.llm_backlog.

Cost guard: row_limit per cron run + max_tokens=2000 per LLM call.
"""
from __future__ import annotations

import json
import logging

from alpha_agent.llm.base import Message
from alpha_agent.news.queries import (
    update_macro_event_llm,
    update_news_item_llm,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 15
_MAX_TOKENS = 2000

def _news_system_prompt(lang: str = "en") -> str:
    """Build the news-scoring system prompt with reasoning, in the
    requested user locale.

    Adds a `reasoning` field per item (2-3 sentence analysis) on top of the
    legacy `sentiment_score` + `sentiment_label`. The reasoning text gives
    the user a substantive analysis next to the color dot — addresses the
    2026-05-19 feedback that the LLM enrich button "only shows red/green/gray".

    lang = "zh" → reasoning in 简体中文. Anything else → English.
    """
    reasoning_lang = "简体中文" if lang == "zh" else "English"
    reasoning_directive = (
        f"Write the `reasoning` field in {reasoning_lang}. "
        "2-3 sentences total: (1) what the headline means for this ticker, "
        "(2) why it warrants your sentiment score, (3) one concrete watch-out "
        "or follow-on signal. Skip generic boilerplate."
    )
    return (
        "You score per-ticker financial news sentiment and write a brief "
        "analyst commentary. For each headline in the user message, return "
        "a JSON array element of shape "
        '{"id": <int>, "sentiment_score": <float in [-1,1]>, '
        '"sentiment_label": "pos"|"neg"|"neu", "reasoning": <string>}. '
        'Be conservative on the score: "company beats earnings" is +0.4 to '
        "+0.6, not 1.0. Use 1.0/-1.0 only for genuinely landmark events. "
        f"{reasoning_directive} "
        "Output the JSON array only, no prose."
    )


# Back-compat constant for any external import; defaults to English.
_NEWS_SYSTEM = _news_system_prompt("en")

_MACRO_SYSTEM = (
    "You analyze political/policy/geopolitical events for US-equity "
    "market impact. For each event in the user message, return a JSON "
    'array element of shape {"id": <int>, "tickers": [<US ticker>], '
    '"sectors": [<GICS sector name>], "sentiment_score": <float in [-1,1]>}. '
    "Tickers should be 1-15 max; leave empty for purely partisan posts. "
    "Apple-related posts include AAPL. Tariff announcements list relevant "
    "ADRs + sectors. Sanctions list directly affected names. Output the "
    "JSON array only, no prose."
)


def _build_llm_client():
    """Indirection so tests can monkeypatch _build_llm_client without
    pulling LiteLLM env into the test process."""
    from alpha_agent.config import get_settings
    from alpha_agent.llm.factory import create_llm_client
    return create_llm_client(get_settings())


async def enrich_pending(pool, row_limit: int = 100) -> tuple[int, int]:
    """Returns (n_processed, n_failed_batches)."""
    llm = _build_llm_client()
    n_proc = 0
    n_failed = 0

    # News items
    news = await pool.fetch(
        f"SELECT id, ticker, headline FROM news_items "
        f"WHERE llm_processed_at IS NULL "
        f"ORDER BY id LIMIT {int(row_limit)}"
    )
    for batch in _chunks(news, _BATCH_SIZE):
        ok = await _enrich_news_batch(pool, llm, batch)
        if ok:
            n_proc += len(batch)
        else:
            n_failed += 1

    # Macro events (separate row_limit budget would over-engineer; share)
    macro = await pool.fetch(
        f"SELECT id, title, body, author FROM macro_events "
        f"WHERE llm_processed_at IS NULL "
        f"ORDER BY id LIMIT {int(row_limit)}"
    )
    for batch in _chunks(macro, _BATCH_SIZE):
        ok = await _enrich_macro_batch(pool, llm, batch)
        if ok:
            n_proc += len(batch)
        else:
            n_failed += 1

    return n_proc, n_failed


async def enrich_news_for_ticker(
    pool, llm, ticker: str, row_limit: int = 100, lang: str = "en",
) -> tuple[int, int]:
    """BYOK per-ticker enrichment for the read-time path.

    Caller supplies the LLM client (typically built from the user's
    stored BYOK key via api.byok.get_llm_client). Only touches
    news_items rows WHERE ticker = $1 AND llm_processed_at IS NULL.
    Macro events use a separate dashboard-level enrich path (P1).

    `lang` controls the language of the `reasoning` field on each row
    ("zh" or "en"; defaults to English). Frontend passes the user's
    active locale so the analyst commentary matches the UI.

    Returns (n_processed, n_failed_batches). row_limit caps how many
    news_items a single user click can enqueue (token cost guard).
    """
    n_proc = 0
    n_failed = 0
    news = await pool.fetch(
        "SELECT id, ticker, headline FROM news_items "
        "WHERE ticker = $1 AND llm_processed_at IS NULL "
        "ORDER BY id LIMIT $2",
        ticker.upper(), int(row_limit),
    )
    for batch in _chunks(news, _BATCH_SIZE):
        ok = await _enrich_news_batch(pool, llm, batch, lang=lang)
        if ok:
            n_proc += len(batch)
        else:
            n_failed += 1
    return n_proc, n_failed


async def enrich_news_for_ticker_stream(
    pool, llm, ticker: str, row_limit: int = 100, lang: str = "en",
):
    """Streaming variant of `enrich_news_for_ticker`.

    Yields progress events as each batch completes so the frontend can fill
    the news list in progressively (no full-page reload):

      {"type": "start", "pending": <int>}            once, up front
      {"type": "items", "items": [<written item>...]} per completed batch
      {"type": "batch_failed"}                        per failed batch
      {"type": "done", "enriched": <int>, "failed_batches": <int>}

    Granularity note: the underlying LLM call is a *batch* (15 headlines →
    one JSON array, parsed in one shot — a truncated array fails the whole
    batch). True per-item streaming is therefore not structurally possible
    without N× the token spend, so the honest unit is per-batch: each
    `items` event carries every row that batch enriched, and the consumer
    splices them into the list in place. With ≤15 unenriched headlines (the
    common case) this is a single `items` event; longer backlogs paint
    batch by batch.

    Each item dict has the same shape the frontend NewsItemLite expects:
    {id, sentiment_score, sentiment_label, reasoning_text, reasoning_lang}.
    """
    news = await pool.fetch(
        "SELECT id, ticker, headline FROM news_items "
        "WHERE ticker = $1 AND llm_processed_at IS NULL "
        "ORDER BY id LIMIT $2",
        ticker.upper(), int(row_limit),
    )
    yield {"type": "start", "pending": len(news)}
    n_proc = 0
    n_failed = 0
    for batch in _chunks(news, _BATCH_SIZE):
        items = await _enrich_news_batch_items(pool, llm, batch, lang=lang)
        if items is None:
            n_failed += 1
            yield {"type": "batch_failed"}
            continue
        n_proc += len(batch)
        yield {"type": "items", "items": items}
    yield {"type": "done", "enriched": n_proc, "failed_batches": n_failed}


def _chunks(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i : i + n]


async def _enrich_news_batch_items(
    pool, llm, batch, lang: str = "en",
) -> list[dict] | None:
    """Enrich one batch and return the list of items written to the DB.

    Returns a list of `{id, sentiment_score, sentiment_label,
    reasoning_text, reasoning_lang}` dicts for each row the LLM successfully
    classified, or `None` if the whole batch failed (bad/truncated JSON) so
    the rows stay pending for the next click. This is the per-batch unit the
    streaming enrich endpoint surfaces so the news list fills in
    progressively without a full-page reload.
    """
    user_payload = "\n".join(
        f'{{"id": {r["id"]}, "ticker": "{r["ticker"]}", '
        f'"headline": {json.dumps(r["headline"])}}}'
        for r in batch
    )
    messages = [
        Message(role="system", content=_news_system_prompt(lang)),
        Message(role="user", content=user_payload),
    ]
    try:
        # Bumped from 2000 → 3000 to fit ~2-3 sentence reasoning per row at
        # batch=15. If the model truncates mid-array the whole batch parse
        # fails and the rows stay pending for next click.
        resp = await llm.chat(messages, temperature=0.0, max_tokens=3000)
        parsed = json.loads(resp.content)
    except Exception as exc:
        logger.warning("news llm enrich batch failed: %s: %s",
                       type(exc).__name__, exc)
        return None
    by_id = {int(p["id"]): p for p in parsed if isinstance(p, dict) and "id" in p}
    written: list[dict] = []
    for row in batch:
        p = by_id.get(int(row["id"]))
        if p is None:
            continue
        try:
            reasoning_raw = p.get("reasoning")
            reasoning_text = (
                str(reasoning_raw).strip()
                if reasoning_raw not in (None, "")
                else None
            )
            score = (
                float(p.get("sentiment_score"))
                if p.get("sentiment_score") is not None
                else None
            )
            label = p.get("sentiment_label")
            await update_news_item_llm(
                pool, int(row["id"]),
                score,
                label,
                reasoning_text=reasoning_text,
                reasoning_lang=lang if reasoning_text else None,
            )
            written.append({
                "id": int(row["id"]),
                "sentiment_score": score,
                "sentiment_label": label,
                "reasoning_text": reasoning_text,
                "reasoning_lang": lang if reasoning_text else None,
            })
        except Exception as exc:
            logger.warning("news llm update failed row=%s: %s: %s",
                           row["id"], type(exc).__name__, exc)
    return written


async def _enrich_news_batch(pool, llm, batch, lang: str = "en") -> bool:
    """Back-compat boolean wrapper used by the cron / non-stream paths."""
    items = await _enrich_news_batch_items(pool, llm, batch, lang=lang)
    return items is not None


async def _enrich_macro_batch(pool, llm, batch) -> bool:
    user_payload = "\n".join(
        f'{{"id": {r["id"]}, "author": "{r["author"]}", '
        f'"title": {json.dumps(r["title"])}, '
        f'"body": {json.dumps((r["body"] or "")[:1500])}}}'
        for r in batch
    )
    messages = [
        Message(role="system", content=_MACRO_SYSTEM),
        Message(role="user", content=user_payload),
    ]
    try:
        resp = await llm.chat(messages, temperature=0.0, max_tokens=_MAX_TOKENS)
        parsed = json.loads(resp.content)
    except Exception as exc:
        logger.warning("macro llm enrich batch failed: %s: %s",
                       type(exc).__name__, exc)
        return False
    by_id = {int(p["id"]): p for p in parsed if isinstance(p, dict) and "id" in p}
    for row in batch:
        p = by_id.get(int(row["id"]))
        if p is None:
            continue
        try:
            await update_macro_event_llm(
                pool, int(row["id"]),
                list(p.get("tickers") or []),
                list(p.get("sectors") or []),
                float(p.get("sentiment_score")) if p.get("sentiment_score") is not None else None,
            )
        except Exception as exc:
            logger.warning("macro llm update failed row=%s: %s: %s",
                           row["id"], type(exc).__name__, exc)
    return True
