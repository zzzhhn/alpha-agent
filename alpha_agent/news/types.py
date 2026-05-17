"""Canonical NewsItem + MacroEvent shapes shared by every adapter, and
the dedup_hash helper that makes the news_items.dedup_hash UNIQUE
constraint do its job.
"""
from __future__ import annotations

import hashlib
import string
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse, urlunparse


@dataclass(frozen=True)
class NewsItem:
    """Normalized per-ticker news item written into news_items."""
    ticker: str
    source: str
    source_id: str | None
    headline: str
    url: str
    published_at: datetime
    summary: str | None = None
    raw: Any = None

    def dedup(self) -> str:
        return dedup_hash(self.ticker, self.url, self.headline)


@dataclass(frozen=True)
class MacroEvent:
    """Normalized market-wide event written into macro_events."""
    source: str
    source_id: str | None
    author: str
    title: str
    url: str | None
    body: str | None
    published_at: datetime
    raw: Any = None

    def dedup(self) -> str:
        return dedup_hash(None, self.url or self.title, self.title)


_PUNCT_TABLE = str.maketrans({c: " " for c in string.punctuation})


def _normalize_url(url: str) -> str:
    p = urlparse(url)
    # Drop query + fragment entirely; most upstreams add UTM/tracking
    # params that would otherwise defeat dedup.
    return urlunparse((p.scheme.lower(), p.netloc.lower(), p.path, "", "", ""))


def _normalize_headline(headline: str) -> str:
    s = headline.lower().translate(_PUNCT_TABLE)
    return " ".join(s.split())


def dedup_hash(ticker: str | None, url: str, headline: str) -> str:
    """sha256(ticker|normalized_url|normalized_headline).

    ticker scope is in the hash so a multi-ticker story returned via
    per-symbol fetches produces one row per ticker (rather than the
    second ticker losing its row to the first). Macro events pass
    ticker=None.
    """
    tk = (ticker or "").upper()
    norm_url = _normalize_url(url)
    norm_hl = _normalize_headline(headline)
    return hashlib.sha256(f"{tk}|{norm_url}|{norm_hl}".encode()).hexdigest()
