"""Federal Reserve press_all RSS adapter (macro channel).

Source: https://www.federalreserve.gov/feeds/press_all.xml
Combined feed of press releases, FOMC statements, speeches, testimony.
"""
from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import feedparser

from alpha_agent.news.base import make_client
from alpha_agent.news.types import MacroEvent

_SOURCE_URL = "https://www.federalreserve.gov/feeds/press_all.xml"


class FedRSSAdapter:
    name = "fed_rss"
    channel = "macro"
    priority = 1

    def __init__(self) -> None:
        self._client = make_client()

    async def fetch(
        self,
        *,
        ticker: str | None = None,
        since: datetime,
    ) -> list[MacroEvent]:
        resp = await self._client.get(_SOURCE_URL)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.text)
        out: list[MacroEvent] = []
        for entry in parsed.entries:
            title = getattr(entry, "title", "") or ""
            link = getattr(entry, "link", "") or ""
            if not title:
                continue
            pubdate_str = getattr(entry, "published", None) or getattr(entry, "updated", None)
            try:
                published = parsedate_to_datetime(pubdate_str) if pubdate_str else datetime.now(UTC)
                if published.tzinfo is None:
                    published = published.replace(tzinfo=UTC)
            except (TypeError, ValueError):
                published = datetime.now(UTC)
            if published < since:
                continue
            summary = getattr(entry, "summary", None) or getattr(entry, "description", None)
            out.append(
                MacroEvent(
                    source="fed_rss",
                    source_id=getattr(entry, "id", None),
                    author="fed",
                    title=title,
                    url=link or None,
                    body=summary,
                    published_at=published,
                    raw={"title": title, "link": link, "published": pubdate_str,
                         "summary": summary},
                )
            )
        return out

    async def is_available(self) -> bool:
        try:
            r = await self._client.get(_SOURCE_URL)
            return r.status_code == 200
        except Exception:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
