"""Financial Modeling Prep stock_news per-ticker adapter (failover-only).

Free tier: 250 calls/day. The aggregator only calls this adapter when
the primary (Finnhub) returned empty/errored for the ticker. Without
that discipline a full 557-ticker cycle would burn the entire daily
quota.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from alpha_agent.news.base import make_client
from alpha_agent.news.types import NewsItem

_ENDPOINT = "https://financialmodelingprep.com/api/v3/stock_news"


class FMPAdapter:
    name = "fmp"
    channel = "per_ticker"
    priority = 2  # failover-only; enforced by PerTickerAggregator

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = make_client()

    async def fetch(
        self,
        *,
        ticker: str | None = None,
        since: datetime,
    ) -> list[NewsItem]:
        assert ticker is not None
        params = {"tickers": ticker.upper(), "limit": 20, "apikey": self._api_key}
        resp = await self._client.get(_ENDPOINT, params=params)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            return []
        out: list[NewsItem] = []
        for it in payload:
            url = it.get("url") or ""
            title = it.get("title") or ""
            if not url or not title:
                continue
            raw_ts = it.get("publishedDate")
            try:
                published = datetime.strptime(raw_ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            except (TypeError, ValueError):
                published = datetime.now(UTC)
            out.append(
                NewsItem(
                    ticker=ticker.upper(),
                    source="fmp",
                    source_id=None,  # FMP does not expose stable IDs
                    headline=title,
                    url=url,
                    published_at=published,
                    summary=it.get("text"),
                    raw=it,
                )
            )
        return out

    async def is_available(self) -> bool:
        try:
            r = await self._client.get(
                _ENDPOINT,
                params={"tickers": "AAPL", "limit": 1, "apikey": self._api_key},
            )
            return r.status_code == 200
        except Exception:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
