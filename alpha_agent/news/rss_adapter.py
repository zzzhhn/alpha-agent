"""Per-ticker RSS adapter (Yahoo Finance per-symbol feed).

Tertiary in the per_ticker failover chain. Free, keyless. Used when
Finnhub returns empty AND FMP returns empty (or both errored). Yahoo's
per-symbol RSS URL is the only one that maps cleanly to a single
ticker; Google News keyword search adds too much noise to be worth
parsing here.
"""
from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import feedparser

from alpha_agent.news.base import make_client
from alpha_agent.news.types import NewsItem

_YAHOO_FEED = "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"


class RSSAdapter:
    name = "rss_yahoo"
    channel = "per_ticker"
    priority = 3

    def __init__(self) -> None:
        self._client = make_client()

    async def fetch(
        self,
        *,
        ticker: str | None = None,
        since: datetime,
    ) -> list[NewsItem]:
        assert ticker is not None
        url = _YAHOO_FEED.format(ticker=ticker.upper())
        resp = await self._client.get(url)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.text)
        out: list[NewsItem] = []
        for entry in parsed.entries:
            title = getattr(entry, "title", "") or ""
            link = getattr(entry, "link", "") or ""
            if not title or not link:
                continue
            pubdate_str = getattr(entry, "published", None) or getattr(entry, "updated", None)
            try:
                published = (
                    parsedate_to_datetime(pubdate_str) if pubdate_str else datetime.now(UTC)
                )
                if published.tzinfo is None:
                    published = published.replace(tzinfo=UTC)
            except (TypeError, ValueError):
                published = datetime.now(UTC)
            if published < since:
                continue
            out.append(
                NewsItem(
                    ticker=ticker.upper(),
                    source="rss_yahoo",
                    source_id=getattr(entry, "id", None),
                    headline=title,
                    url=link,
                    published_at=published,
                    summary=getattr(entry, "summary", None),
                    raw={"title": title, "link": link,
                         "published": pubdate_str, "id": getattr(entry, "id", None)},
                )
            )
        return out

    async def is_available(self) -> bool:
        try:
            r = await self._client.get(_YAHOO_FEED.format(ticker="AAPL"))
            return r.status_code == 200
        except Exception:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
