"""OFAC Recent Actions RSS adapter (macro channel).

URL verification (2026-05-16): the spec listed ofac.treasury.gov/recent-actions
but every variant on that domain returns HTTP 404 (the public-facing page is
a Drupal app with no inline RSS link). Treasury exposes per-program feeds via
GovDelivery. Topic USTREAS_61 is titled "OFAC: Recent Actions" and returns
HTTP 200 with Content-Type: application/rss+xml. That is the canonical feed
we use here.

If GovDelivery shuts this topic down, fall back to per-program feeds
(USTREAS_115 Balkans, USTREAS_117 Burma, USTREAS_120 Iran, USTREAS_123
North Korea, etc.) and aggregate. The schema returned by all those feeds
is RSS 2.0, so feedparser handles them identically.
"""
from __future__ import annotations

from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import feedparser

from alpha_agent.news.base import make_client
from alpha_agent.news.types import MacroEvent

_SOURCE_URL = "https://public.govdelivery.com/topics/USTREAS_61/feed.rss"


class OFACRSSAdapter:
    name = "ofac_rss"
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
                    source="ofac_rss",
                    source_id=getattr(entry, "id", None),
                    author="ofac",
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
