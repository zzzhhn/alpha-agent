"""Typed CRUD helpers backed by raw SQL. Imported by cron/API code only;
direct asyncpg usage outside this module is a code smell.
"""
from __future__ import annotations

import json
import math
from typing import Any

import asyncpg


def _json_safe(obj: Any) -> Any:
    """Walk a dict/list/scalar, replacing NaN/+Inf/-Inf with None.

    Postgres JSONB rejects NaN/Inf (per JSON spec) but Python json.dumps
    happily emits them as literal `NaN`/`Infinity` tokens. Sanitize at the
    storage boundary so callers don't have to remember to filter NaNs out
    of every signal breakdown."""
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    return obj


def _dumps(obj: Any) -> str:
    return json.dumps(_json_safe(obj))


def _safe_num(x: float | None, default: float = 0.0) -> float:
    """NaN/Inf/None → default. PG DOUBLE PRECISION accepts NaN but it
    propagates wrong-direction bias through map_to_tier() and chokes
    Pydantic JSON serialization downstream."""
    if x is None:
        return default
    try:
        f = float(x)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


async def insert_signal_slow(
    pool: asyncpg.Pool,
    ticker: str,
    date: str,
    composite_partial: float,
    breakdown: dict[str, Any],
) -> None:
    await pool.execute(
        """
        INSERT INTO daily_signals_slow
            (ticker, date, composite_partial, breakdown, fetched_at)
        VALUES ($1, $2::text::date, $3, $4::jsonb, now())
        ON CONFLICT (ticker, date) DO UPDATE SET
            composite_partial = EXCLUDED.composite_partial,
            breakdown = EXCLUDED.breakdown,
            fetched_at = EXCLUDED.fetched_at
        """,
        ticker, date, _safe_num(composite_partial), _dumps(breakdown),
    )


async def upsert_signal_fast(
    pool: asyncpg.Pool,
    ticker: str,
    date: str,
    composite: float,
    rating: str,
    confidence: float,
    breakdown: dict[str, Any],
    partial: bool = False,
) -> None:
    await pool.execute(
        """
        INSERT INTO daily_signals_fast
            (ticker, date, composite, rating, confidence, breakdown, partial, fetched_at)
        VALUES ($1, $2::text::date, $3, $4, $5, $6::jsonb, $7, now())
        ON CONFLICT (ticker, date) DO UPDATE SET
            composite = EXCLUDED.composite,
            rating = EXCLUDED.rating,
            confidence = EXCLUDED.confidence,
            breakdown = EXCLUDED.breakdown,
            partial = EXCLUDED.partial,
            fetched_at = EXCLUDED.fetched_at
        """,
        ticker, date, _safe_num(composite), rating, _safe_num(confidence), _dumps(breakdown), partial,
    )


async def enqueue_alert(
    pool: asyncpg.Pool,
    ticker: str,
    type_: str,
    payload: dict[str, Any],
    dedup_bucket: int,
) -> None:
    """Idempotent within (ticker, type, dedup_bucket). Caller computes bucket
    as floor(epoch / 1800) for 30-min windows."""
    await pool.execute(
        """
        INSERT INTO alert_queue (ticker, type, payload, dedup_bucket)
        VALUES ($1, $2, $3::jsonb, $4)
        ON CONFLICT (ticker, type, dedup_bucket) DO NOTHING
        """,
        ticker, type_, _dumps(payload), dedup_bucket,
    )


async def list_pending_alerts(pool: asyncpg.Pool, limit: int) -> list[asyncpg.Record]:
    return await pool.fetch(
        """
        SELECT id, ticker, type, payload, created_at
        FROM alert_queue
        WHERE dispatched = false
        ORDER BY created_at ASC
        LIMIT $1
        """,
        limit,
    )


async def mark_alert_dispatched(pool: asyncpg.Pool, alert_id: int) -> None:
    await pool.execute("UPDATE alert_queue SET dispatched = true WHERE id = $1", alert_id)


async def log_error(
    pool: asyncpg.Pool,
    *,
    layer: str,
    component: str,
    ticker: str | None = None,
    err_type: str | None = None,
    err_message: str | None = None,
    context: dict[str, Any] | None = None,
) -> None:
    await pool.execute(
        """
        INSERT INTO error_log (layer, component, ticker, err_type, err_message, context)
        VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        """,
        layer, component, ticker, err_type, err_message, _dumps(context or {}),
    )


# ── company_profiles (V010): cached stock-detail "About" card ───────────────


async def get_company_profile(
    pool: asyncpg.Pool, ticker: str
) -> asyncpg.Record | None:
    """Return the cached profile row, or None if this ticker isn't cached yet."""
    return await pool.fetchrow(
        "SELECT * FROM company_profiles WHERE ticker = $1", ticker.upper()
    )


async def upsert_company_profile_en(
    pool: asyncpg.Pool,
    ticker: str,
    *,
    name: str | None,
    sector: str | None,
    industry: str | None,
    summary_en: str | None,
    website: str | None,
    country: str | None,
    employees: int | None,
) -> None:
    """Insert/refresh the English (yfinance-sourced) fields. Leaves
    summary_zh + translated_at untouched so an existing translation
    survives an EN refresh."""
    await pool.execute(
        """
        INSERT INTO company_profiles
            (ticker, name, sector, industry, summary_en, website, country,
             employees, fetched_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, now())
        ON CONFLICT (ticker) DO UPDATE SET
            name = EXCLUDED.name,
            sector = EXCLUDED.sector,
            industry = EXCLUDED.industry,
            summary_en = EXCLUDED.summary_en,
            website = EXCLUDED.website,
            country = EXCLUDED.country,
            employees = EXCLUDED.employees,
            fetched_at = now()
        """,
        ticker.upper(), name, sector, industry, summary_en, website,
        country, employees,
    )


async def set_company_profile_zh(
    pool: asyncpg.Pool, ticker: str, summary_zh: str
) -> None:
    """Backfill the Chinese translation (run by the offline translate script)."""
    await pool.execute(
        """
        UPDATE company_profiles
        SET summary_zh = $2, translated_at = now()
        WHERE ticker = $1
        """,
        ticker.upper(), summary_zh,
    )


async def list_profiles_missing_zh(
    pool: asyncpg.Pool, limit: int = 1000
) -> list[asyncpg.Record]:
    """Rows that have an English summary but no Chinese translation yet —
    the work queue for the offline backfill script."""
    return await pool.fetch(
        """
        SELECT ticker, summary_en FROM company_profiles
        WHERE summary_en IS NOT NULL AND summary_en <> ''
          AND (summary_zh IS NULL OR summary_zh = '')
        ORDER BY ticker
        LIMIT $1
        """,
        limit,
    )


async def set_company_name_zh(
    pool: asyncpg.Pool, ticker: str, name_zh: str | None
) -> None:
    """Backfill the Chinese company name (offline translate script). An empty
    or None value clears it (company has no established Chinese name)."""
    await pool.execute(
        "UPDATE company_profiles SET name_zh = $2 WHERE ticker = $1",
        ticker.upper(), (name_zh or None),
    )


async def list_profiles_missing_name_zh(
    pool: asyncpg.Pool, limit: int = 1000
) -> list[asyncpg.Record]:
    """Rows with an English name but no name_zh decision yet — work queue for
    the name backfill. name_zh stays NULL until the backfill has CONSIDERED the
    ticker, so re-running doesn't re-translate already-decided rows."""
    return await pool.fetch(
        """
        SELECT ticker, name FROM company_profiles
        WHERE name IS NOT NULL AND name <> '' AND name_zh IS NULL
        ORDER BY ticker
        LIMIT $1
        """,
        limit,
    )


# ── insider_form4 (V020): precomputed SEC Form 4 net value per ticker ────────


async def upsert_insider_form4(
    pool: asyncpg.Pool, ticker: str, net_value: float, n_filings: int
) -> None:
    """Store one ticker's net insider value (run by the Form 4 ingestion job)."""
    await pool.execute(
        """
        INSERT INTO insider_form4 (ticker, net_value, n_filings, computed_at)
        VALUES ($1, $2, $3, now())
        ON CONFLICT (ticker) DO UPDATE
        SET net_value = EXCLUDED.net_value,
            n_filings = EXCLUDED.n_filings,
            computed_at = now()
        """,
        ticker.upper(), float(net_value), int(n_filings),
    )


async def load_all_insider_form4(
    pool: asyncpg.Pool,
) -> dict[str, tuple[float, int]]:
    """All precomputed insider net values as {ticker: (net_value, n_filings)}.
    Loaded once per signal cron run to prime the insider signal cache, so the
    signal path makes no SEC calls."""
    rows = await pool.fetch("SELECT ticker, net_value, n_filings FROM insider_form4")
    return {r["ticker"]: (r["net_value"], r["n_filings"]) for r in rows}


# ── earnings_finnhub (V021): precomputed earnings-surprise inputs per ticker ──


async def upsert_earnings_finnhub(
    pool: asyncpg.Pool,
    ticker: str,
    recent_surprise: float | None,
    sigma: float | None,
    report_date,
    next_date,
    eps_estimate: float | None,
    revenue_estimate: float | None,
) -> None:
    """Store one ticker's earnings-surprise inputs (run by the Finnhub job)."""
    await pool.execute(
        """
        INSERT INTO earnings_finnhub (ticker, recent_surprise, sigma, report_date,
            next_date, eps_estimate, revenue_estimate, computed_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, now())
        ON CONFLICT (ticker) DO UPDATE
        SET recent_surprise = EXCLUDED.recent_surprise,
            sigma = EXCLUDED.sigma,
            report_date = EXCLUDED.report_date,
            next_date = EXCLUDED.next_date,
            eps_estimate = EXCLUDED.eps_estimate,
            revenue_estimate = EXCLUDED.revenue_estimate,
            computed_at = now()
        """,
        ticker.upper(), recent_surprise, sigma, report_date,
        next_date, eps_estimate, revenue_estimate,
    )


async def load_all_earnings_finnhub(pool: asyncpg.Pool) -> dict[str, dict]:
    """All precomputed earnings inputs as {ticker: {...}}. Loaded once per
    signal cron run to prime the earnings signal (no Finnhub call on the
    signal path)."""
    rows = await pool.fetch(
        """SELECT ticker, recent_surprise, sigma, report_date, next_date,
                  eps_estimate, revenue_estimate FROM earnings_finnhub"""
    )
    return {r["ticker"]: dict(r) for r in rows}


# ── daily_prices (V011): one close per ticker per calendar day ───────────────


async def upsert_daily_close(
    pool: asyncpg.Pool, ticker: str, date: str, close: float | None
) -> None:
    """Insert/replace one daily close. Skips None / non-positive closes
    (yfinance gap rows) so the IC engine's return ratio never divides by
    zero. None is annotated explicitly because yfinance history rows can
    carry a missing Close."""
    if close is None or close <= 0:
        return
    await pool.execute(
        """
        INSERT INTO daily_prices (ticker, date, close)
        VALUES ($1, $2::text::date, $3)
        ON CONFLICT (ticker, date) DO UPDATE SET close = EXCLUDED.close
        """,
        ticker.upper(), date, float(close),
    )
