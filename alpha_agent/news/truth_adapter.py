"""Trump Truth Social via CNN's public JSON mirror.

Source: https://ix.cnn.io/data/truth-social/truth_archive.json
Refreshed by CNN every ~5 minutes; we poll on the same cadence.

No API key, no rate limit observed. If CNN takes the mirror down,
fall back to trumpstruth.org RSS or stiles/trump-truth-social-archive
GitHub by swapping the URL constant.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from alpha_agent.news.base import make_client
from alpha_agent.news.types import MacroEvent

_SOURCE_URL = "https://ix.cnn.io/data/truth-social/truth_archive.json"


class TruthSocialAdapter:
    name = "truth_social"
    channel = "macro"
    priority = 1

    def __init__(self) -> None:
        self._client = make_client(timeout_seconds=15.0)

    async def fetch(
        self,
        *,
        ticker: str | None = None,
        since: datetime,
    ) -> list[MacroEvent]:
        resp = await self._client.get(_SOURCE_URL)
        resp.raise_for_status()
        payload = resp.json()
        # CNN mirror returns a bare array of truth objects at the top
        # level. Earlier versions (and the spec fixture) used
        # {"truths": [...]}; keep both shapes supported defensively.
        if isinstance(payload, list):
            truths = payload
        elif isinstance(payload, dict):
            truths = payload.get("truths") or payload.get("data") or []
        else:
            truths = []
        out: list[MacroEvent] = []
        for t in truths:
            ts = t.get("created_at")
            try:
                published = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except (AttributeError, ValueError):
                continue
            if published < since:
                continue
            body = t.get("content") or ""
            if not body:
                continue
            tid = t.get("id")
            url = t.get("url") or (
                f"https://truthsocial.com/@realDonaldTrump/posts/{tid}" if tid else None
            )
            out.append(
                MacroEvent(
                    source="truth_social",
                    source_id=str(tid) if tid is not None else None,
                    author="trump",
                    title=body[:140] + ("..." if len(body) > 140 else ""),
                    url=url,
                    body=body,
                    published_at=published,
                    raw=t,
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
