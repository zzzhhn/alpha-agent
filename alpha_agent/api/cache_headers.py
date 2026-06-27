"""Shared HTTP cache-header helper for read endpoints.

Context: the API function runs in Vercel hkg1 but Neon is in us-east-1, so every
DB round trip is a ~150-250ms transpacific hop, and the read path is slowest
exactly when the cron batch-writes contend for the 0.25-vCPU free tier. None of
the read endpoints set Cache-Control, so the Vercel edge (which sits in hkg1,
right next to the user) cannot serve a single repeat load — every click is a full
origin trip through the contended DB.

These endpoints serve GLOBAL data (ratings / picks / ohlcv / profile — identical
for every user, no per-user content), so a SHARED (`public`) edge cache is
correct. The server-side RSC fetches reach the backend WITHOUT the auth cookie
(middleware only runs client-side — see frontend client.ts), so they are
cacheable; client-side fetches that carry the cookie simply skip the cache (the
header is then a harmless no-op).

`stale-while-revalidate` lets the edge serve a slightly-stale response instantly
while refreshing in the background, so the user never waits on a cache miss after
the first one. Staleness windows are tiny next to the data's real update cadence
(intraday ratings refresh ~every 15 min, daily/profile far slower).
"""
from __future__ import annotations

from fastapi import Response


def set_public_cache(response: Response, *, s_maxage: int, swr: int) -> None:
    """Mark `response` shared-cacheable at the Vercel edge.

    s_maxage: seconds the edge may serve the cached response as fresh.
    swr: extra seconds the edge may serve it stale while revalidating in the
         background (stale-while-revalidate).
    """
    response.headers["Cache-Control"] = (
        f"public, s-maxage={s_maxage}, stale-while-revalidate={swr}"
    )
