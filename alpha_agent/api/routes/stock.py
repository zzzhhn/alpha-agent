"""GET /api/stock/{ticker} — full card for one ticker, read-only from DB.

Ticker is normalised to uppercase.  Returns a stale flag when the most
recent row is older than 24 hours.  Spec §7.2.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Literal

_log = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from pydantic import BaseModel

from alpha_agent.api.byok import get_llm_client
from alpha_agent.api.cache_headers import set_public_cache
from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.storage.queries import (
    get_company_profile,
    upsert_company_profile_en,
)
from alpha_agent.api.signal_lookup import fetch_latest_signal
from alpha_agent.auth.dependencies import require_user
from alpha_agent.backtest.confidence_calibration import load_active_calibration
from alpha_agent.fusion.attribution import top_drivers, top_drags
from alpha_agent.fusion.grades import grade_dimensions
from alpha_agent.fusion.grade_thresholds import get_dimension_thresholds
from alpha_agent.llm.base import LLMClient, Message
from alpha_agent.signals.yf_helpers import (
    extract_ohlcv,
    extract_profile,
    get_ticker,
)

router = APIRouter(prefix="/api/stock", tags=["stock"])


class NewsItemLite(BaseModel):
    id: int
    source: str
    headline: str
    url: str
    published_at: str
    sentiment_score: float | None
    sentiment_label: str | None
    # V007 (2026-05-19): per-headline LLM-written commentary, surfaced in
    # NewsBlock alongside the sentiment dot so the user sees the *why* not
    # just the color. `reasoning_lang` tracks which locale the LLM was asked
    # to write in ("zh"|"en") so the UI can set the lang= attribute.
    reasoning_text: str | None = None
    reasoning_lang: str | None = None


class FullCard(BaseModel):
    ticker: str
    rating: str
    # Calibrated directional hit-rate (honest edge, ~50%); also sizes positions.
    confidence: float
    # Raw signal-agreement = 1/(1+variance(z)): the conviction headline, NOT a
    # hit-rate. Defaulted so legacy callers without the field still validate.
    agreement: float = 0.0
    composite_score: float
    as_of: str
    top_drivers: list[str]
    top_drags: list[str]
    breakdown: list[dict]
    # True for a slow-only ticker: daily-pipeline data, rating/confidence
    # derived, no fast factors, can be up to ~1 day old.
    partial: bool = False
    news_items: list[NewsItemLite] = []
    # B2 (2026-05-19): hysteresis band absorbed a tier flip today. Sticky
    # `rating` differs from the raw threshold mapping; UI surfaces a small
    # indicator so the user can see the band is currently active.
    tier_flip_today: bool = False
    # B5 (2026-05-19): GEX intraday regime classifier. None when option
    # chain unavailable / fetch failed gracefully. Surfaced as a badge
    # on the stock detail page header to disambiguate "buy-dip works"
    # (regime=pinned) from "trend continuation" (regime=volatile).
    gex_info: dict | None = None
    # B8 (2026-05-19): per-dimension letter grades derived from breakdown
    # z's. Six dimensions (Momentum/Technical/Sentiment/Catalyst/Insider/
    # Flow) each receive an A+ to F grade so the user reads SeekingAlpha-
    # style at-a-glance without monthly fundamental ingest.
    dimension_grades: dict[str, str] = {}


class StockResponse(BaseModel):
    card: FullCard
    stale: bool


@router.get("/{ticker}", response_model=StockResponse)
async def get_stock(
    response: Response,
    ticker: str = Path(min_length=1, max_length=10),
) -> StockResponse:
    """Return the most-recent RatingCard for *ticker*.

    Reads via fetch_latest_signal so a slow-only ticker (covered by the
    daily pipeline but not the intraday cron, e.g. NVDA) resolves to a
    partial card instead of 404ing.
    """
    ticker = ticker.upper()
    pool = await get_db_pool()
    cal_map = await load_active_calibration(pool)
    # Signal, news, and dimension thresholds are independent reads, so run them
    # concurrently: with the function in hkg1 and the DB in us-east-1 every query
    # is a transpacific round trip, and gathering collapses three sequential
    # waves into one. (thresholds is cached in-process, so on a warm instance
    # it's a no-op; the gather matters on a cold instance.) The news read is only
    # wasted on a 404 ticker.
    sig, news_rows, dim_thresholds = await asyncio.gather(
        fetch_latest_signal(pool, ticker, cal_map=cal_map),
        pool.fetch(
            """
            SELECT id, source, headline, url, published_at,
                   sentiment_score, sentiment_label,
                   reasoning_text, reasoning_lang
            FROM news_items
            WHERE ticker = $1
            ORDER BY published_at DESC
            LIMIT 20
            """,
            ticker,
        ),
        get_dimension_thresholds(pool),
    )
    if sig is None:
        raise HTTPException(status_code=404, detail=f"No rating for {ticker}")
    # Rating card is global, slow-moving (intraday cron refreshes ~every 15 min):
    # let the hkg1 edge serve repeat opens so a re-click never pays the
    # transpacific round trip or queues behind a cron write.
    set_public_cache(response, s_maxage=45, swr=300)

    fetched_at: datetime = sig["fetched_at"]
    stale = (datetime.now(UTC) - fetched_at) > timedelta(hours=24)
    news_items = [
        NewsItemLite(
            id=r["id"],
            source=r["source"],
            headline=r["headline"],
            url=r["url"],
            published_at=r["published_at"].isoformat(),
            sentiment_score=r["sentiment_score"],
            sentiment_label=r["sentiment_label"],
            reasoning_text=r["reasoning_text"],
            reasoning_lang=r["reasoning_lang"],
        )
        for r in news_rows
    ]

    card = FullCard(
        ticker=sig["ticker"],
        rating=sig["rating"],
        confidence=sig["confidence"],
        agreement=sig["agreement"],
        composite_score=sig["score"],
        as_of=fetched_at.isoformat(),
        top_drivers=top_drivers(sig["breakdown"]),
        top_drags=top_drags(sig["breakdown"]),
        breakdown=sig["breakdown"],
        partial=sig["partial"],
        news_items=news_items,
        tier_flip_today=sig.get("tier_flip_today", False),
        gex_info=sig.get("gex_info"),
        dimension_grades=grade_dimensions(sig["breakdown"], dim_thresholds),
    )
    return StockResponse(card=card, stale=stale)


# ---------------------------------------------------------------------------
# B4 (2026-05-19) Event-on-chart + LLM "why" explanation
# ---------------------------------------------------------------------------


class ChartEvent(BaseModel):
    """One event marker for the PriceChart overlay. `type` drives the
    glyph + colour the lightweight-charts setMarkers call renders.
    sentiment_score and sentiment_label come from the LLM-enrich step
    (Phase 5b read-time path) and are nullable for un-enriched rows."""
    ts: str
    type: Literal["news", "macro_political", "macro_geopolitical"]
    headline: str
    url: str | None = None
    sentiment_score: float | None = None
    sentiment_label: str | None = None


class ChartEventsResponse(BaseModel):
    ticker: str
    from_ts: str
    to_ts: str
    events: list[ChartEvent]


@router.get("/{ticker}/events", response_model=ChartEventsResponse)
async def get_events(
    response: Response,
    ticker: str = Path(min_length=1, max_length=10),
    from_ts: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    to_ts: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
) -> ChartEventsResponse:
    """Return timestamped events for a ticker within [from_ts, to_ts].

    Pulls from news_items (per-ticker direct) UNION macro_events
    (per-ticker via tickers_extracted array containment from the LLM
    enrich step). Capped at 200 events per request so a single chart
    overlay never explodes — older time ranges that exceed the cap
    are truncated newest-first.
    """
    ticker = ticker.upper()
    pool = await get_db_pool()
    try:
        from_d = datetime.strptime(from_ts, "%Y-%m-%d").replace(tzinfo=UTC)
        to_d = datetime.strptime(to_ts, "%Y-%m-%d").replace(tzinfo=UTC) + timedelta(days=1)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"date parse: {exc}")

    news_rows = await pool.fetch(
        """
        SELECT published_at, headline, url, sentiment_score, sentiment_label
        FROM news_items
        WHERE ticker = $1 AND published_at >= $2 AND published_at < $3
        ORDER BY published_at DESC
        LIMIT 200
        """,
        ticker, from_d, to_d,
    )

    # macro events use Postgres array containment on tickers_extracted —
    # the LLM enrich step writes that array. Tickers w/o LLM enrich yet
    # simply won't surface macro events; that's the correct degraded
    # behaviour (the user can hit the LLM enrich button on news to bootstrap).
    macro_rows = await pool.fetch(
        """
        SELECT published_at, title, url, author, sentiment_score
        FROM macro_events
        WHERE $1 = ANY(tickers_extracted)
          AND published_at >= $2 AND published_at < $3
        ORDER BY published_at DESC
        LIMIT 200
        """,
        ticker, from_d, to_d,
    )

    events: list[ChartEvent] = []
    for r in news_rows:
        events.append(ChartEvent(
            ts=r["published_at"].isoformat(),
            type="news",
            headline=r["headline"],
            url=r["url"],
            sentiment_score=r["sentiment_score"],
            sentiment_label=r["sentiment_label"],
        ))
    for r in macro_rows:
        # Author = "Trump" / "Fed" / etc. classifies political vs geopolitical
        author = (r["author"] or "").lower()
        ev_type: Literal["news", "macro_political", "macro_geopolitical"]
        if author in {"trump", "potus", "harris"} or "politic" in author:
            ev_type = "macro_political"
        else:
            ev_type = "macro_geopolitical"
        events.append(ChartEvent(
            ts=r["published_at"].isoformat(),
            type=ev_type,
            headline=r["title"],
            url=r["url"],
            sentiment_score=r["sentiment_score"],
        ))

    # Newest first across the union, capped.
    events.sort(key=lambda e: e.ts, reverse=True)
    events = events[:200]

    # Chart overlay is a global, slow-moving read. (When called internally by
    # explain_range the response is a throwaway, so the header is discarded.)
    set_public_cache(response, s_maxage=120, swr=600)
    return ChartEventsResponse(
        ticker=ticker, from_ts=from_ts, to_ts=to_ts, events=events,
    )


class ExplainRangeResponse(BaseModel):
    ticker: str
    from_ts: str
    to_ts: str
    explanation: str
    event_count: int
    cache: Literal["hit", "miss"] = "miss"


@router.post("/{ticker}/explain_range", response_model=ExplainRangeResponse)
async def explain_range(
    ticker: str = Path(min_length=1, max_length=10),
    from_ts: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    to_ts: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"),
    language: Literal["zh", "en"] = Query("en"),
    user_id: int = Depends(require_user),
    llm: LLMClient = Depends(get_llm_client),
) -> ExplainRangeResponse:
    """B4 lasso replacement (v1): LLM-generated 3-sentence explanation
    of which events most likely drove a price move within the user's
    selected window. Cached via B3 (per-user, key folds in from_ts,
    to_ts, language, top headlines hash) so a re-click on the same
    range is sub-100ms and zero BYOK spend.
    """
    ticker = ticker.upper()
    pool = await get_db_pool()

    # Internal reuse of the events query — pass a throwaway Response (its cache
    # header is discarded; explain_range is a POST and sets none of its own).
    events_resp = await get_events(
        Response(), ticker=ticker, from_ts=from_ts, to_ts=to_ts
    )
    if not events_resp.events:
        return ExplainRangeResponse(
            ticker=ticker, from_ts=from_ts, to_ts=to_ts,
            explanation=("无可见事件 in 此时间段;价格变动可能由因子/技术面驱动。"
                          if language == "zh" else
                          "No visible news / macro events in this range; "
                          "price move likely factor- or technicals-driven."),
            event_count=0, cache="miss",
        )

    # Build the user-prompt context. Keep it compact: top-10 events by
    # absolute sentiment score (or newest if score missing) so the LLM
    # focuses on signal rather than noise.
    def _score_key(e: ChartEvent) -> float:
        return abs(e.sentiment_score) if e.sentiment_score is not None else 0.0
    sorted_events = sorted(events_resp.events, key=_score_key, reverse=True)[:10]
    bullets = "\n".join(
        f"- [{e.ts[:10]}] {e.type}: {e.headline[:140]}"
        f"  (sent={e.sentiment_score:+.2f})" if e.sentiment_score is not None
        else f"- [{e.ts[:10]}] {e.type}: {e.headline[:140]}"
        for e in sorted_events
    )

    system = (
        "你是一位冷静的股票分析师。给定一支股票在某段时间内发生的事件列表,"
        "用 2-3 句中文给出最可能影响价格的事件 +ranking。不要捏造数据,只用提供的事件。"
        if language == "zh" else
        "You are a sober equity analyst. Given a ticker and a list of events "
        "in a time window, identify in 2-3 sentences which events most likely "
        "moved the price. Do not invent data — use only events provided."
    )
    user = (
        f"Ticker: {ticker}\nWindow: {from_ts} to {to_ts}\n"
        f"Events ({len(sorted_events)} of {len(events_resp.events)} total, "
        f"ranked by |sentiment|):\n{bullets}"
    )
    messages = [Message(role="system", content=system), Message(role="user", content=user)]

    # B3 cache wrap
    from alpha_agent.llm.cache import (
        CACHE_TTL_DEFAULT, cache_key, cached_response, store_response,
    )

    key = cache_key(
        model=getattr(llm, "_model", "byok"),
        messages=messages,
        variant=f"{ticker}|{from_ts}|{to_ts}|{language}|n={len(sorted_events)}",
    )
    cached_text = await cached_response(pool, user_id, key)
    if cached_text is not None:
        return ExplainRangeResponse(
            ticker=ticker, from_ts=from_ts, to_ts=to_ts,
            explanation=cached_text, event_count=len(events_resp.events),
            cache="hit",
        )

    try:
        resp = await llm.chat(messages, temperature=0.3, max_tokens=400)
    finally:
        close = getattr(llm, "close", None)
        if close is not None:
            await close()

    text = (resp.content or "").strip()
    if text:
        await store_response(
            pool, user_id, key,
            getattr(llm, "_model", "byok"), text,
            ttl=CACHE_TTL_DEFAULT,
        )
    return ExplainRangeResponse(
        ticker=ticker, from_ts=from_ts, to_ts=to_ts,
        explanation=text or "LLM 返回空响应。",
        event_count=len(events_resp.events), cache="miss",
    )


# ---------------------------------------------------------------------------
# A1 (2026-05-19) — Persona-as-prompt LLM commentary per signal camp
# ---------------------------------------------------------------------------


class PersonaExplainResponse(BaseModel):
    ticker: str
    persona: str
    explanation: str
    cache: Literal["hit", "miss"] = "miss"


@router.post(
    "/{ticker}/persona/{persona_name}/explain",
    response_model=PersonaExplainResponse,
)
async def persona_explain(
    ticker: str = Path(min_length=1, max_length=10),
    persona_name: str = Path(min_length=2, max_length=24),
    language: Literal["zh", "en"] = Query("en"),
    user_id: int = Depends(require_user),
    llm: LLMClient = Depends(get_llm_client),
) -> PersonaExplainResponse:
    """Render a named persona's commentary for one ticker.

    Critical (per backlog A1): this MUST stay on the detail-drawer-open
    path only. The cron must never fan persona calls per ticker per day
    — 7 personas × N tickers × M days would 7x the BYOK token spend
    with zero marginal UX gain. Cron path is the AttributionTable z
    payload; LLM persona text is read-time-on-demand only.

    Cached via B3 per (user, ticker, persona, language, as_of_date) so
    re-clicks on the same persona within 24h are sub-100ms.
    """
    from alpha_agent.llm.cache import (
        CACHE_TTL_DEFAULT, cache_key, cached_response, store_response,
    )
    from alpha_agent.personas import get_persona
    from alpha_agent.personas.registry import render_system_prompt

    ticker = ticker.upper()
    persona = get_persona(persona_name)
    if persona is None:
        raise HTTPException(
            status_code=404,
            detail=f"persona {persona_name!r} not registered",
        )

    pool = await get_db_pool()
    cal_map = await load_active_calibration(pool)
    sig = await fetch_latest_signal(pool, ticker, cal_map=cal_map)
    if sig is None:
        raise HTTPException(status_code=404, detail=f"no rating for {ticker}")

    # Subset the breakdown to the persona's scope so the LLM doesn't
    # waste tokens on signals outside the camp. Pass raw payloads
    # along where available so the persona can quote concrete numbers
    # (headlines, ATR values, etc.).
    scoped = [
        b for b in sig["breakdown"]
        if b.get("signal") in persona.signals
    ]
    if not scoped:
        return PersonaExplainResponse(
            ticker=ticker, persona=persona.name,
            explanation=(
                "该 persona 关注的信号当前为空。"
                if language == "zh" else
                "No data for this persona's signals right now."
            ),
            cache="miss",
        )

    user_payload = json.dumps(
        {
            "ticker": ticker,
            "rating": sig["rating"],
            "composite": sig["score"],
            "signals_in_scope": [
                {"signal": b["signal"], "z": b.get("z"), "raw": b.get("raw")}
                for b in scoped
            ],
        },
        default=str,
    )

    system = render_system_prompt(persona, language)
    messages = [
        Message(role="system", content=system),
        Message(role="user", content=user_payload),
    ]

    fetched_date = sig["fetched_at"].date().isoformat()
    key = cache_key(
        model=getattr(llm, "_model", "byok"),
        messages=messages,
        variant=f"{ticker}|{persona.name}|{language}|{fetched_date}",
    )
    cached_text = await cached_response(pool, user_id, key)
    if cached_text is not None:
        return PersonaExplainResponse(
            ticker=ticker, persona=persona.name,
            explanation=cached_text, cache="hit",
        )

    try:
        resp = await llm.chat(messages, temperature=0.3, max_tokens=300)
    finally:
        close = getattr(llm, "close", None)
        if close is not None:
            await close()

    text = (resp.content or "").strip()
    if text:
        await store_response(
            pool, user_id, key,
            getattr(llm, "_model", "byok"), text,
            ttl=CACHE_TTL_DEFAULT,
        )
    return PersonaExplainResponse(
        ticker=ticker, persona=persona.name,
        explanation=text or "LLM 返回空响应。",
        cache="miss",
    )


@router.post("/{ticker}/persona/{persona_name}/explain/stream")
async def persona_explain_stream(
    ticker: str = Path(min_length=1, max_length=10),
    persona_name: str = Path(min_length=2, max_length=24),
    language: Literal["zh", "en"] = Query("en"),
    user_id: int = Depends(require_user),
):
    """SSE-streaming sibling of `persona_explain` (mirrors the Rich Brief
    streaming pattern).

    Token-streams the persona commentary as `{type: "explanation", delta}`
    events terminated by `{type: "done"}`. Auth is required; the BYOK key is
    fetched + decrypted server-side from the authenticated user's stored
    credentials, exactly like `post_brief_stream` — the key never leaves the
    server and decrypt / no-key failures degrade into an SSE `error` event
    rather than a 500 to a blank UI.

    The per-(user, ticker, persona, language, as_of_date) B3 cache is
    preserved: a re-click within 24h replays the cached text as one delta +
    done (sub-100ms, zero LLM spend), matching the non-streaming route's
    cache slot exactly.
    """
    import os
    import sys

    from fastapi.responses import StreamingResponse

    from alpha_agent.api.sse import SSE_HEADERS, sse_format
    from alpha_agent.auth.crypto_box import CryptoError, decrypt
    from alpha_agent.llm.cache import cache_key
    from alpha_agent.llm.persona_streamer import stream_persona
    from alpha_agent.personas import get_persona
    from alpha_agent.personas.registry import render_system_prompt

    ticker = ticker.upper()
    persona = get_persona(persona_name)
    if persona is None:
        raise HTTPException(
            status_code=404,
            detail=f"persona {persona_name!r} not registered",
        )

    pool = await get_db_pool()
    cal_map = await load_active_calibration(pool)
    sig = await fetch_latest_signal(pool, ticker, cal_map=cal_map)
    if sig is None:
        raise HTTPException(status_code=404, detail=f"no rating for {ticker}")

    # Subset the breakdown to the persona's scope (same as the non-stream route).
    scoped = [
        b for b in sig["breakdown"]
        if b.get("signal") in persona.signals
    ]

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

    system = render_system_prompt(persona, language)
    user_payload = json.dumps(
        {
            "ticker": ticker,
            "rating": sig["rating"],
            "composite": sig["score"],
            "signals_in_scope": [
                {"signal": b["signal"], "z": b.get("z"), "raw": b.get("raw")}
                for b in scoped
            ],
        },
        default=str,
    )
    fetched_date = sig["fetched_at"].date().isoformat()
    key = cache_key(
        model=byok["model"] or byok["provider"],
        messages=[Message(role="system", content=system),
                  Message(role="user", content=user_payload)],
        variant=f"{ticker}|{persona.name}|{language}|{fetched_date}",
    )

    async def generator():
        # No-data short-circuit: emit the graceful "no signals" line as a
        # single delta + done, never an error. Mirrors the non-stream route.
        if not scoped:
            yield sse_format({
                "type": "explanation",
                "delta": (
                    "该 persona 关注的信号当前为空。"
                    if language == "zh" else
                    "No data for this persona's signals right now."
                ),
            })
            yield sse_format({"type": "done", "cache": "miss"})
            return
        try:
            plaintext_key = decrypt(byok["ciphertext"], byok["nonce"], master.encode("utf-8"))
        except CryptoError:
            yield sse_format({
                "type": "error",
                "message": "Stored key cannot be decrypted. Please re-save it in /settings.",
            })
            return
        try:
            async for event in stream_persona(
                provider=byok["provider"],
                api_key=plaintext_key,
                system_prompt=system,
                user_payload=user_payload,
                model=byok["model"],
                base_url=byok["base_url"],
                pool=pool,
                user_id=user_id,
                cache_key_str=key,
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
                f"persona stream error: {type(e).__name__}: {e}",
                file=sys.stderr, flush=True,
            )
            yield sse_format({
                "type": "error",
                "message": f"LLM request failed ({type(e).__name__}). Check your key in /settings.",
            })

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


# ---------------------------------------------------------------------------
# Per-day news summary (2026-06-04) — LLM summary + sentiment read of the
# news the user sees after clicking a candle in the IntradayDrawer. Replaces
# the standalone NewsBlock analysis surface. Mirrors the persona streaming
# pattern exactly (SSE explanation deltas + done, BYOK key server-side,
# no-key/decrypt → SSE error event never a 500).
# ---------------------------------------------------------------------------


class NewsDaySummaryRequest(BaseModel):
    # The clicked candle's calendar date (UTC), YYYY-MM-DD.
    date: str
    # LLM output language follows the page locale (no manual picker).
    language: Literal["zh", "en"] = "en"


def _build_news_day_system_prompt(language: str) -> str:
    """System prompt for the per-day news summary. The model is asked for a
    short, plain-prose summary plus an overall sentiment read of the day's
    headlines. Single block (no section markers) so the consumer paints it
    exactly like persona commentary."""
    if language == "zh":
        return (
            "你是一名股票新闻分析师。给你某只股票在某一交易日窗口内的新闻标题列表,"
            "请用中文写一段简洁的总结(2 至 3 段):先概述当日新闻的主要内容,"
            "再给出整体情绪判断(偏多 / 偏空 / 中性)并说明理由。"
            "只依据所给标题,不要编造未提及的事实,不要给出投资建议。"
        )
    return (
        "You are an equity news analyst. Given a list of news headlines for "
        "one stock within a single trading-day window, write a concise "
        "summary (2-3 short paragraphs): first recap the main developments, "
        "then give an overall sentiment read (bullish / bearish / neutral) "
        "with a one-line rationale. Use only the supplied headlines, do not "
        "fabricate facts not present, and do not give investment advice."
    )


@router.post("/{ticker}/news-day-summary/stream")
async def news_day_summary_stream(
    payload: NewsDaySummaryRequest,
    ticker: str = Path(min_length=1, max_length=10),
    user_id: int = Depends(require_user),
):
    """SSE-streaming LLM summary + sentiment read of one day's news.

    Window / holiday backfill: the news window for a trading day D is
    (previous_trading_day, D] — every news_item with published_at strictly
    after the previous trading day and through the end of D (UTC). The
    previous trading day is the max daily_prices.date strictly < D (the
    trading calendar), so Friday-evening through Monday news folds into
    Monday and any holiday gap folds into the first trading day after it.

    Mirrors the persona streaming route exactly: BYOK key fetched +
    decrypted server-side, output streamed as `{type:"explanation",delta}`
    terminated by `{type:"done"}`, no-key/decrypt failures degrade into an
    SSE `error` event (never a 500 to a blank UI), and the per-(user,
    ticker, date, language) B3 cache makes a re-click within 24h instant.
    An empty window streams a graceful "no news this day" done event.
    """
    import os
    import sys

    from fastapi.responses import StreamingResponse

    from alpha_agent.api.sse import SSE_HEADERS, sse_format
    from alpha_agent.auth.crypto_box import CryptoError, decrypt
    from alpha_agent.llm.cache import cache_key
    from alpha_agent.llm.persona_streamer import stream_persona

    ticker = ticker.upper()
    try:
        date_obj = datetime.strptime(payload.date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date '{payload.date}', expected YYYY-MM-DD",
        ) from exc
    language = payload.language

    pool = await get_db_pool()

    # previous_trading_day = max trading-calendar date strictly before D.
    # daily_prices.date is the calendar; None when D is the earliest covered
    # day (or no history) → window opens from the start of D itself.
    prev_trading_day = await pool.fetchval(
        "SELECT max(date) FROM daily_prices WHERE date < $1::date",
        date_obj,
    )

    # Window = (previous_trading_day, D] in UTC. Open bound is the start of
    # the day AFTER prev_trading_day (i.e. published_at > prev_trading_day,
    # which for a DATE means "from 00:00 of the next day"); close bound is
    # the end of D (start of D+1, exclusive). When there is no previous
    # trading day, open from the start of D.
    if prev_trading_day is not None:
        window_start = datetime.combine(
            prev_trading_day + timedelta(days=1), datetime.min.time(), tzinfo=UTC
        )
    else:
        window_start = datetime.combine(date_obj, datetime.min.time(), tzinfo=UTC)
    window_end = datetime.combine(
        date_obj + timedelta(days=1), datetime.min.time(), tzinfo=UTC
    )

    news_rows = await pool.fetch(
        """
        SELECT headline, source, url, published_at,
               sentiment_score, sentiment_label
        FROM news_items
        WHERE ticker = $1 AND published_at >= $2 AND published_at < $3
        ORDER BY published_at DESC
        LIMIT 50
        """,
        ticker, window_start, window_end,
    )

    headlines = [
        {
            "headline": r["headline"],
            "source": r["source"],
            "published_at": r["published_at"].isoformat(),
            "sentiment_score": r["sentiment_score"],
            "sentiment_label": r["sentiment_label"],
        }
        for r in news_rows
    ]

    async def empty_generator():
        # Graceful "no news this day" — single done event, no LLM round trip,
        # no error. The consumer shows the no-news copy.
        yield sse_format({"type": "done", "cache": "empty"})

    if not headlines:
        return StreamingResponse(
            empty_generator(),
            media_type="text/event-stream",
            headers=SSE_HEADERS,
        )

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

    system = _build_news_day_system_prompt(language)
    user_payload = json.dumps(
        {
            "ticker": ticker,
            "date": payload.date,
            "headlines": headlines,
        },
        default=str,
    )
    # Cache slot per (user, ticker, date, language). The window is fully
    # determined by (ticker, date) via the trading calendar, so the date is
    # a sound cache key without folding the resolved window bounds in.
    key = cache_key(
        model=byok["model"] or byok["provider"],
        messages=[Message(role="system", content=system),
                  Message(role="user", content=user_payload)],
        variant=f"{ticker}|news-day|{payload.date}|{language}",
    )

    async def generator():
        try:
            plaintext_key = decrypt(byok["ciphertext"], byok["nonce"], master.encode("utf-8"))
        except CryptoError:
            yield sse_format({
                "type": "error",
                "message": "Stored key cannot be decrypted. Please re-save it in /settings.",
            })
            return
        try:
            async for event in stream_persona(
                provider=byok["provider"],
                api_key=plaintext_key,
                system_prompt=system,
                user_payload=user_payload,
                model=byok["model"],
                base_url=byok["base_url"],
                pool=pool,
                user_id=user_id,
                cache_key_str=key,
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
                f"news-day summary stream error: {type(e).__name__}: {e}",
                file=sys.stderr, flush=True,
            )
            yield sse_format({
                "type": "error",
                "message": f"LLM request failed ({type(e).__name__}). Check your key in /settings.",
            })

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


@router.get("/personas")
async def list_personas(language: Literal["zh", "en"] = Query("en")) -> dict:
    """Public discovery endpoint — UI uses this to render the persona
    chip row on the stock detail page."""
    from alpha_agent.personas import PERSONAS

    return {
        "personas": [
            {
                "name": p.name,
                "label": p.label_zh if language == "zh" else p.label_en,
                "signals": list(p.signals),
            }
            for p in PERSONAS.values()
        ],
    }


# ---------------------------------------------------------------------------


class OhlcvBar(BaseModel):
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int


class OhlcvResponse(BaseModel):
    ticker: str
    period: str
    bars: list[OhlcvBar]


# yfinance period vocabulary: 1d 5d 1mo 3mo 6mo 1y 2y 5y 10y ytd max.
# Restrict to the ones the chart UI offers to avoid surprises.
_AllowedPeriod = Literal["1mo", "3mo", "6mo", "1y", "2y", "5y"]

# In-process OHLCV cache. The old handler did a live, synchronous yfinance pull
# on EVERY chart open — slow (~200-500ms transpacific to Yahoo) and worst exactly
# while the cron pulls the same tickers from yfinance (rate-limit contention, the
# user's "slower when the backend is pulling data" symptom). Daily bars move once
# per session, so a short in-process TTL plus the edge cache means a re-open
# almost never re-hits Yahoo. Keyed (ticker, period); value (monotonic_ts, bars).
_OHLCV_TTL_SECONDS = 300.0
_ohlcv_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}


def _fetch_ohlcv_bars(ticker: str, period: str) -> list[dict]:
    """yfinance pull -> OHLCV row dicts. Indirection so the cache + tests can
    wrap the one slow, blocking call."""
    df = get_ticker(ticker).history(period=period)
    return extract_ohlcv(df)


def _cached_ohlcv_bars(ticker: str, period: str) -> list[dict]:
    key = (ticker, period)
    now = time.monotonic()
    hit = _ohlcv_cache.get(key)
    if hit is not None and (now - hit[0]) < _OHLCV_TTL_SECONDS:
        return hit[1]
    bars = _fetch_ohlcv_bars(ticker, period)
    _ohlcv_cache[key] = (now, bars)
    return bars


@router.get("/{ticker}/ohlcv", response_model=OhlcvResponse)
async def stock_ohlcv(
    response: Response,
    ticker: str,
    period: _AllowedPeriod = "6mo",
) -> OhlcvResponse:
    """Lazy OHLCV feed for the price chart. In-process TTL cache over the
    yfinance pull + an edge cache header so repeat opens are instant and never
    contend with the cron's yfinance pulls."""
    ticker = ticker.upper()
    bars = _cached_ohlcv_bars(ticker, period)
    set_public_cache(response, s_maxage=600, swr=3600)
    return OhlcvResponse(
        ticker=ticker,
        period=period,
        bars=[OhlcvBar(**b) for b in bars],
    )


class CompanyProfile(BaseModel):
    ticker: str
    name: str | None = None
    # Chinese company name (V019), backfilled offline. NULL until the name
    # backfill has considered the ticker; equals `name` when the company has no
    # established Chinese name. The frontend shows it in zh locale and treats
    # name_zh != name as "a real Chinese name exists".
    name_zh: str | None = None
    sector: str | None = None
    industry: str | None = None
    summary: str | None = None
    # Actual language of `summary` — lets the frontend show a "translation
    # pending" note when zh was requested but only en is available yet.
    summary_lang: Literal["zh", "en"] | None = None
    website: str | None = None
    country: str | None = None
    employees: int | None = None


@router.get("/{ticker}/profile", response_model=CompanyProfile)
async def stock_profile(
    response: Response,
    ticker: str,
    lang: Literal["zh", "en"] = Query("en"),
) -> CompanyProfile:
    """Company "About" card. DB-cached (company_profiles, V010): the first
    request per ticker pulls yfinance once and stores the EN fields;
    subsequent reads serve from the DB so we never re-scrape. `summary` is
    locale-appropriate — summary_zh when lang=zh and a translation exists
    (backfilled offline by scripts/backfill_company_profiles_zh.py), else
    summary_en. Never 500s: DB failures fall back to a direct yfinance pull,
    and a total failure returns all-null fields (the card hides)."""
    ticker = ticker.upper()
    # Company profile barely changes — cache it hard at the edge (long fresh +
    # day-long stale-while-revalidate).
    set_public_cache(response, s_maxage=3600, swr=86400)
    try:
        pool = await get_db_pool()
        row = await get_company_profile(pool, ticker)
        if row is None:
            # Cache miss → pull yfinance once, persist EN, serve EN.
            prof = extract_profile(get_ticker(ticker).info or {})
            await upsert_company_profile_en(
                pool, ticker,
                name=prof["name"], sector=prof["sector"],
                industry=prof["industry"], summary_en=prof["summary"],
                website=prof["website"], country=prof["country"],
                employees=prof["employees"],
            )
            return CompanyProfile(
                ticker=ticker,
                summary_lang="en" if prof["summary"] else None,
                **prof,
            )
        # Cache hit → resolve the summary for the requested locale.
        if lang == "zh" and row["summary_zh"]:
            summary, summary_lang = row["summary_zh"], "zh"
        else:
            summary = row["summary_en"]
            summary_lang = "en" if row["summary_en"] else None
        return CompanyProfile(
            ticker=ticker,
            name=row["name"],
            name_zh=row["name_zh"],
            sector=row["sector"],
            industry=row["industry"],
            summary=summary,
            summary_lang=summary_lang,
            website=row["website"],
            country=row["country"],
            employees=row["employees"],
        )
    except Exception as exc:  # noqa: BLE001 — profile is non-critical; never 500
        _log.warning(
            "profile DB path failed for %s: %s: %s",
            ticker, type(exc).__name__, exc,
        )
        # DB unavailable — still try a direct (uncached) yfinance pull so a
        # DB hiccup doesn't blank the card app-wide.
        try:
            prof = extract_profile(get_ticker(ticker).info or {})
            return CompanyProfile(
                ticker=ticker,
                summary_lang="en" if prof["summary"] else None,
                **prof,
            )
        except Exception:  # noqa: BLE001
            return CompanyProfile(ticker=ticker)


class MinuteBar(BaseModel):
    ts: str  # ISO 8601
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int


class MinuteBarsResponse(BaseModel):
    ticker: str
    date: str
    bars: list[MinuteBar]
    # True if the requested date is older than the 30d rolling retention
    # window of minute_bars (yfinance 1m retention limit). Frontend uses
    # this to distinguish a "no data, day out of coverage" message from a
    # "no data, weekend / holiday" message.
    out_of_range: bool


# Minute bars are kept on a rolling ~30 day window by minute_bars_puller.
# yfinance only retains 1m bars for the last 7-30 days, so older dates
# return an empty bars list with out_of_range=True instead of querying.
_MINUTE_BARS_RETENTION_DAYS = 30


@router.get("/{ticker}/minute_bars", response_model=MinuteBarsResponse)
async def stock_minute_bars(
    ticker: str,
    date: str,  # YYYY-MM-DD
) -> MinuteBarsResponse:
    """Return all minute_bars for one ticker on one calendar date (UTC).

    Returns empty bars list if date is older than the 30d rolling window
    or no bars exist (e.g. weekend / holiday / out-of-coverage ticker).
    Caller (frontend IntradayDrawer) renders an empty-state message.
    """
    ticker = ticker.upper()
    try:
        date_obj = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid date '{date}', expected YYYY-MM-DD",
        ) from exc

    today_utc = datetime.now(UTC).date()
    out_of_range = date_obj < (today_utc - timedelta(days=_MINUTE_BARS_RETENTION_DAYS))
    if out_of_range:
        return MinuteBarsResponse(
            ticker=ticker,
            date=date,
            bars=[],
            out_of_range=True,
        )

    pool = await get_db_pool()
    rows = await pool.fetch(
        """
        SELECT ts, open, high, low, close, volume FROM minute_bars
        WHERE ticker = $1
          AND (ts AT TIME ZONE 'UTC')::date = $2::date
        ORDER BY ts ASC
        """,
        ticker,
        date_obj,
    )
    bars = [
        MinuteBar(
            ts=r["ts"].isoformat(),
            open=float(r["open"]) if r["open"] is not None else None,
            high=float(r["high"]) if r["high"] is not None else None,
            low=float(r["low"]) if r["low"] is not None else None,
            close=float(r["close"]) if r["close"] is not None else None,
            volume=int(r["volume"]) if r["volume"] is not None else 0,
        )
        for r in rows
    ]
    return MinuteBarsResponse(
        ticker=ticker,
        date=date,
        bars=bars,
        out_of_range=False,
    )
