"""Finnhub /company-news per-ticker adapter (per_ticker channel, priority 1).

Free tier: 60 req/min. We deliberately make one request per ticker per
cycle; with 557 tickers/hour this is ~9.3 req/min sustained, well inside
the limit. Errors propagate to the caller so PerTickerAggregator can
trigger the FMP fallback.
"""
from __future__ import annotations

from datetime import UTC, datetime

from alpha_agent.news.base import make_client
from alpha_agent.news.types import NewsItem

_ENDPOINT = "https://finnhub.io/api/v1/company-news"


class FinnhubAdapter:
    name = "finnhub"
    channel = "per_ticker"
    priority = 1

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._client = make_client()

    async def fetch(
        self,
        *,
        ticker: str | None = None,
        since: datetime,
    ) -> list[NewsItem]:
        assert ticker is not None, "finnhub adapter requires a ticker"
        to = datetime.now(UTC).date().isoformat()
        params = {
            "symbol": ticker.upper(),
            "from": since.date().isoformat(),
            "to": to,
            "token": self._api_key,
        }
        resp = await self._client.get(_ENDPOINT, params=params)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            return []
        out: list[NewsItem] = []
        for it in payload:
            url = it.get("url") or ""
            headline = it.get("headline") or ""
            if not url or not headline:
                continue
            ts = it.get("datetime")
            try:
                published = datetime.fromtimestamp(int(ts), tz=UTC) if ts else datetime.now(UTC)
            except (TypeError, ValueError):
                published = datetime.now(UTC)
            out.append(
                NewsItem(
                    ticker=ticker.upper(),
                    source="finnhub",
                    source_id=str(it.get("id")) if it.get("id") is not None else None,
                    headline=headline,
                    url=url,
                    published_at=published,
                    summary=it.get("summary"),
                    raw=it,
                )
            )
        return out

    async def is_available(self) -> bool:
        try:
            r = await self._client.get(
                _ENDPOINT,
                params={"symbol": "AAPL", "from": "2026-05-01",
                        "to": "2026-05-02", "token": self._api_key},
            )
            return r.status_code == 200
        except Exception:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
