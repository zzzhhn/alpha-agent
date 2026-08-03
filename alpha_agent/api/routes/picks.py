"""GET /api/picks/lean — top N picks by composite_score, read-only from DB.

SLA: < 500ms p95.  No synchronous signal fetch on the request path.
Spec §7.2.

build_lean_view() is the assembly (DB read -> ranked LeanCards). The endpoint
is a thin wrapper over it; the product ledger (alpha_agent/ledger.py) calls the
SAME function so the immutable record is byte-identical to what the user saw
(one code path, no drift).
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel

from alpha_agent.api.cache_headers import set_public_cache
from alpha_agent.api.dependencies import get_db_pool
from alpha_agent.fusion.attribution import top_drivers, top_drags
from alpha_agent.fusion.grades import grade_dimensions
from alpha_agent.fusion.grade_thresholds import get_dimension_thresholds
from alpha_agent.fusion.rating import compute_confidence, map_to_tier
from alpha_agent.fusion.combine import combine
from alpha_agent.fusion.policy import get_policy
from alpha_agent.market_session import latest_completed_xnys_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/picks", tags=["picks"])

_STALE_THRESHOLD_HOURS = 24

# A ticker with no close in the last N trading sessions has a dead price feed
# (delisting / ticker change / halt — e.g. HOLX/SEE return nothing on Yahoo,
# BK/CTRA stopped on a date). It is untradeable AND its signal is computed on
# stale prices, so it must not be recommended. The guard excludes such tickers
# from the default ranking only — an explicit ticker search still surfaces it
# (so you can look one up). Reversible: raise to re-admit slower-updating names.
_PRICE_FRESH_TRADING_DAYS = 3


class LeanCard(BaseModel):
    """Lean projection of a signal row, no heavy breakdown list.

    `partial` marks a slow-only row: it comes from daily_signals_slow,
    which stores composite_partial + breakdown but no rating/confidence,
    so those two are derived here. Partial rows exclude the fast factors
    and can be up to ~1 day old.
    """

    ticker: str
    company_name: str | None = None
    company_name_zh: str | None = None
    # Latest available daily close, never presented as a real-time quote.
    latest_price: float | None = None
    price_date: str | None = None
    daily_change_pct: float | None = None
    rating: str
    # Calibrated directional hit-rate (isotonic map over realized 5d outcomes).
    # Honest "edge", structurally modest (~50%); also feeds Kelly position sizing.
    confidence: float | None
    # Raw signal-agreement = 1/(1+variance(z)). The conviction headline: how
    # aligned the underlying signals are on this name. NOT a hit-rate.
    agreement: float = 0.0
    composite_score: float
    as_of: str
    top_drivers: list[str]
    top_drags: list[str]
    partial: bool = False
    # B2 (2026-05-19): true when the no-trade band saved a tier flip today
    # (raw_tier differed from sticky rating). UI surfaces a small indicator
    # so the user knows hysteresis is currently absorbing wobble.
    tier_flip_today: bool = False
    # B8 (2026-05-19): per-dimension letter grades from breakdown z's so
    # the picks table can show A+/A/B/.../F at-a-glance per row.
    dimension_grades: dict[str, str] = {}
    # Per-ticker directional consistency = next-day hit-rate of the predicted
    # tier over trailing windows {d5, m1, y1, hist}. Each value is a fraction in
    # [0,1], or None when the window has too little realized history (UI shows a
    # dash). See alpha_agent/backtest/consistency.py for the exact definition.
    consistency: dict[str, float | None] = {}
    # Evaluated sample count per window (how many realized directional
    # predictions back each rate). Lets the UI explain a dash ("n/N 样本不足")
    # and distinguish 50% (2/4) from 50% (40/80) instead of leaving the user
    # guessing — same value for dashed windows shows how close they are.
    consistency_n: dict[str, int] = {}
    # HOLD-inclusive 口径 (2026-07-26): same shape as `consistency` but a HOLD
    # prediction counts as a hit when the next day stayed within the flat band
    # (see alpha_agent/backtest/consistency.py HOLD_FLAT_BAND). Only d5/m1 are
    # ever non-None; y1/hist are structurally unavailable (see that module).
    consistency_hold: dict[str, float | None] = {}
    consistency_hold_n: dict[str, int] = {}
    # Immutable recommendation provenance.  Null on exploratory live/search
    # rows; populated for every card read from one canonical product-ledger run.
    run_id: int | None = None
    market_date: str | None = None
    # The two recommendation views are independently frozen policies.  These
    # fields make the selected sleeve explicit all the way to the browser and
    # prevent a horizon toggle from masquerading as a cosmetic factor switch.
    sleeve: str = "tactical"
    horizon_days: int = 5
    policy_id: str | None = None
    validation_status: str = "production"
    policy_rank: int | None = None


class RecommendationRunState(BaseModel):
    run_id: int
    market_date: str
    generated_at: datetime | None
    data_cutoff: datetime | None
    policy_id: str | None
    coverage: float
    health: dict
    sleeve: str = "tactical"
    horizon_days: int = 5
    validation_status: str = "production"


class PickChange(BaseModel):
    ticker: str
    prior_rank: int | None = None
    current_rank: int | None = None
    prior_tier: str | None = None
    current_tier: str | None = None


class RecommendationChanges(BaseModel):
    available: bool
    prior_run_id: int | None = None
    turnover: float | None = None
    added: list[PickChange] = []
    removed: list[PickChange] = []
    tier_changes: list[PickChange] = []
    reason: str | None = None


class PicksResponse(BaseModel):
    picks: list[LeanCard]
    as_of: datetime | None
    stale: bool
    canonical: bool = False
    ranked: bool = False
    tradable: bool = False
    run: RecommendationRunState | None = None
    changes: RecommendationChanges | None = None


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _strategic_projection(raw_breakdown) -> dict:
    """Re-fuse one stored signal set under the independent 60d policy.

    The tactical row remains immutable.  We clone its auditable signal
    observations, replace only the factor observation with the separately
    evaluated 252d/126d value, and then run the full strategic weight and
    coverage policy.  Missing long-factor data is an explicit dropped signal,
    never a fallback to the tactical score.
    """
    envelope = _json_object(raw_breakdown)
    entries = [dict(entry) for entry in envelope.get("breakdown", [])]
    for entry in entries:
        if entry.get("confidence") is None:
            entry["confidence"] = (
                1.0 if _safe_float(entry.get("weight_effective"), 0.0) > 0 else 0.0
            )
    for entry in entries:
        if entry.get("signal") != "factor":
            continue
        raw = entry.get("raw")
        if isinstance(raw, dict) and isinstance(raw.get("z_long"), (int, float)):
            entry["z"] = float(raw["z_long"])
        else:
            entry["z"] = None
            entry["confidence"] = 0.0
            entry["error"] = "strategic_factor_unavailable"
        break
    policy = get_policy("strategic")
    return combine(
        entries,
        policy.weights,
        coverage_core=policy.core_set(),
        caps=policy.caps_dict(),
    )


def _top_policy_rows(rows, *, mode: str, policy_id: str, top_n: int = 50) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for row in rows:
        if not row["eligible"]:
            continue
        payload = _json_object(row["user_visible_payload_json"])
        if mode == "long":
            payload = _json_object(_json_object(payload.get("_mode_payloads")).get("long"))
            if payload.get("policy_id") != policy_id:
                continue
            rank = payload.get("policy_rank")
        else:
            rank = row["rank"]
        if not isinstance(rank, int) or rank > top_n:
            continue
        result[row["ticker"]] = {
            "rank": rank,
            "tier": payload.get("rating") or row["tier"],
        }
    return result


def _recommendation_changes(
    current_rows,
    previous_rows,
    *,
    mode: str,
    policy_id: str,
    prior_run_id: int | None,
) -> RecommendationChanges:
    current = _top_policy_rows(current_rows, mode=mode, policy_id=policy_id)
    previous = _top_policy_rows(previous_rows, mode=mode, policy_id=policy_id)
    if not previous:
        return RecommendationChanges(
            available=False,
            prior_run_id=prior_run_id,
            reason="no_prior_snapshot_for_same_policy",
        )
    added_names = sorted(set(current) - set(previous), key=lambda ticker: current[ticker]["rank"])
    removed_names = sorted(set(previous) - set(current), key=lambda ticker: previous[ticker]["rank"])
    tier_names = sorted(
        (
            ticker for ticker in set(current) & set(previous)
            if current[ticker]["tier"] != previous[ticker]["tier"]
        ),
        key=lambda ticker: current[ticker]["rank"],
    )
    def change(ticker: str) -> PickChange:
        before = previous.get(ticker, {})
        after = current.get(ticker, {})
        return PickChange(
            ticker=ticker,
            prior_rank=before.get("rank"),
            current_rank=after.get("rank"),
            prior_tier=before.get("tier"),
            current_tier=after.get("tier"),
        )
    return RecommendationChanges(
        available=True,
        prior_run_id=prior_run_id,
        turnover=len(added_names) / max(len(current), 1),
        added=[change(ticker) for ticker in added_names[:10]],
        removed=[change(ticker) for ticker in removed_names[:10]],
        tier_changes=[change(ticker) for ticker in tier_names[:10]],
    )


async def _build_canonical_view(
    pool,
    *,
    limit: int,
    mode: str,
    side: str,
) -> PicksResponse | None:
    """Read one immutable recommendation run, never a mixture of live rows."""
    from alpha_agent.storage.product_ledger import (
        get_latest_canonical_run,
        get_run_snapshots,
    )

    run = await get_latest_canonical_run(pool)
    if run is None:
        return None
    snapshots, previous_run = await asyncio.gather(
        get_run_snapshots(pool, int(run["id"])),
        pool.fetchrow(
            """
            SELECT * FROM research_run
            WHERE run_type=$1 AND status='complete' AND id<>$2
              AND scheduled_for_date < $3
            ORDER BY scheduled_for_date DESC, finished_at DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            run["run_type"],
            int(run["id"]),
            run["scheduled_for_date"],
        ),
    )
    previous_snapshots = (
        await get_run_snapshots(pool, int(previous_run["id"]))
        if previous_run is not None else []
    )
    eligible = [row for row in snapshots if row["eligible"] and row["rank"] is not None]
    cards: list[LeanCard] = []
    mode_supported = True
    market_date: date = run["scheduled_for_date"]
    selected_policy = get_policy("strategic" if mode == "long" else "tactical")
    for row in eligible:
        payload = _json_object(row["user_visible_payload_json"])
        if mode == "long":
            long_payload = _json_object(payload.get("_mode_payloads")).get("long")
            if (
                not isinstance(long_payload, dict)
                or long_payload.get("policy_id") != selected_policy.policy_id
            ):
                mode_supported = False
                break
            payload = long_payload
        try:
            card = LeanCard.model_validate(payload).model_copy(
                update={"run_id": int(run["id"]), "market_date": market_date.isoformat()}
            )
        except Exception as exc:
            logger.warning(
                "invalid canonical snapshot run=%s ticker=%s: %s",
                run["id"],
                row["ticker"],
                exc,
            )
            mode_supported = False
            break
        cards.append(card)

    if not mode_supported:
        return None

    cards.sort(
        key=lambda card: card.composite_score,
        reverse=(side == "long"),
    )
    if side == "long":
        cards = [
            card.model_copy(update={"policy_rank": index})
            for index, card in enumerate(cards, start=1)
        ]
    cards = cards[:limit]

    generated_at = run["finished_at"] or run["data_asof"]
    if generated_at is not None and generated_at.tzinfo is None:
        generated_at = generated_at.replace(tzinfo=UTC)
    expected_market_date = latest_completed_xnys_session()
    health = _json_object(run["health_json"])
    same_market_date = bool(cards) and all(
        card.price_date == market_date.isoformat() for card in cards
    )
    age_stale = generated_at is None or (
        datetime.now(UTC) - generated_at > timedelta(hours=_STALE_THRESHOLD_HOURS)
    )
    stale = bool(
        age_stale
        or market_date != expected_market_date
        or not same_market_date
        or not health.get("passed", False)
    )
    coverage = len(eligible) / len(snapshots) if snapshots else 0.0
    changes = _recommendation_changes(
        snapshots,
        previous_snapshots,
        mode=mode,
        policy_id=selected_policy.policy_id,
        prior_run_id=int(previous_run["id"]) if previous_run is not None else None,
    )
    return PicksResponse(
        picks=cards,
        as_of=generated_at,
        stale=stale,
        canonical=True,
        ranked=True,
        tradable=not stale,
        run=RecommendationRunState(
            run_id=int(run["id"]),
            market_date=market_date.isoformat(),
            generated_at=generated_at,
            data_cutoff=run["input_data_cutoff"],
            policy_id=(
                cards[0].policy_id if cards and cards[0].policy_id
                else selected_policy.policy_id
            ),
            coverage=coverage,
            health=health,
            sleeve="strategic" if mode == "long" else "tactical",
            horizon_days=60 if mode == "long" else 5,
            validation_status=(
                "forward_validation" if mode == "long" else "production"
            ),
        ),
        changes=changes,
    )


class ScoreboardResponse(BaseModel):
    """Portfolio-level evaluation of the picks themselves (the honest headline):
    the daily top-K basket's compounded forward return vs the universe average,
    the long-minus-short spread, and the long basket's directional hit-rate vs
    the always-guess-up base rate. None fields = not enough realized history.

    2026-07-12 additions (display-only — does not affect ranking/selection):
      - spy_cum: SPY compounded over the same dates.
      - mean_daily_turnover: mean one-sided daily name-overlap turnover (long basket).
      - long_net_cum: cost-adjusted net cumulative return (cost_bps default 10bps).
      - cost_bps_used: the cost_bps parameter that produced long_net_cum.
      - breakeven_cost_bps: cost at which net return equals SPY return.
      - beta, alpha_ann, alpha_t: OLS regression of daily long returns on SPY.
    """

    days: int
    top_n: int
    long_cum: float
    short_cum: float
    market_cum: float
    spread_cum: float
    long_hit_rate: float | None
    base_rate: float | None
    # --- 2026-07-12 additions ---
    spy_cum: float | None = None
    mean_daily_turnover: float | None = None
    long_net_cum: float | None = None
    cost_bps_used: float = 10.0
    breakeven_cost_bps: float | None = None
    beta: float | None = None
    alpha_ann: float | None = None
    alpha_t: float | None = None


def _safe_float(v: float | None, default: float = 0.0) -> float:
    """NaN/Inf/None → default. PG DOUBLE PRECISION columns can hold NaN
    if cron wrote it; Pydantic + JSON serialization both choke on NaN."""
    import math
    if v is None:
        return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


async def _load_market_context(pool, tickers: list[str]) -> dict[str, dict]:
    """Load company names and the latest two closes in one batched query."""
    if not tickers:
        return {}
    rows = await pool.fetch(
        """
        WITH ranked_prices AS (
            SELECT ticker, date, close,
                   row_number() OVER (PARTITION BY ticker ORDER BY date DESC) AS rn
            FROM daily_prices
            WHERE ticker = ANY($1::text[])
        ), price_context AS (
            SELECT ticker,
                   max(close) FILTER (WHERE rn = 1) AS latest_price,
                   max(date) FILTER (WHERE rn = 1) AS price_date,
                   max(close) FILTER (WHERE rn = 2) AS previous_price
            FROM ranked_prices
            WHERE rn <= 2
            GROUP BY ticker
        )
        SELECT requested.ticker,
               profiles.name AS company_name,
               profiles.name_zh AS company_name_zh,
               prices.latest_price,
               prices.price_date,
               prices.previous_price
        FROM unnest($1::text[]) AS requested(ticker)
        LEFT JOIN price_context prices USING (ticker)
        LEFT JOIN company_profiles profiles USING (ticker)
        """,
        tickers,
    )
    result: dict[str, dict] = {}
    for row in rows:
        latest = row["latest_price"]
        previous = row["previous_price"]
        change = None
        if latest is not None and previous not in (None, 0):
            change = (float(latest) / float(previous) - 1.0) * 100.0
        result[row["ticker"]] = {
            "company_name": row["company_name"],
            "company_name_zh": row["company_name_zh"],
            "latest_price": float(latest) if latest is not None else None,
            "price_date": row["price_date"].isoformat() if row["price_date"] else None,
            "daily_change_pct": change,
        }
    return result


async def build_lean_view(
    pool,
    *,
    limit: int = 50,
    search: str | None = None,
    mode: str = "short",
    side: str = "long",
) -> tuple[list[LeanCard], datetime | None, bool]:
    """Assemble the ranked LeanCard view. Returns (cards, as_of, stale).

    This is the picks read path, extracted so the product ledger can record
    the exact same view. It performs NO error wrapping — the caller (the HTTP
    endpoint, or the ledger writer) decides how to surface failures.

    `side` (P1-2 two-sided view): "long" (default) returns the top-N by
    composite DESC — the highest-conviction longs. "short" returns the
    bottom-N by composite ASC — the most bearish names (UW/SELL tier),
    which the default long view never surfaces because they rank at the
    bottom of the universe. Same data + same pipeline; only the sort
    direction + LIMIT slice differ.

    Unions two sources so the full ~557-ticker universe is reachable:
      - daily_signals_fast: the 15-min intraday pipeline (~100 tickers),
        full cards with stored rating + confidence.
      - daily_signals_slow: the daily pipeline (full universe). It stores
        only composite_partial + breakdown, so rating is derived via
        map_to_tier and confidence via compute_confidence from the
        breakdown z's. These rows are flagged partial=True.

    A ticker present in fast is taken from fast (fresher and complete).
    `search` does a case-insensitive substring match on the ticker.

    `mode` is kept as a backwards-compatible query name. "short" selects the
    tactical 5d production policy. "long" selects the independently frozen
    60d strategic policy, including its own weights, coverage core and rank.
    """
    from alpha_agent.backtest.confidence_calibration import (
        apply_calibration,
        load_active_calibration,
    )
    # cal_map and dim_thresholds are cached global config; fresh_cutoff is an
    # independent aggregate. None depends on another, so collapse what were three
    # serial transpacific round trips into one gathered wave (matters most on a
    # cold instance, where all three miss their in-process cache). fresh_cutoff is
    # the price-feed freshness cutoff: the oldest of the last N distinct trading
    # dates in daily_prices; a recommended ticker must have a close on/after it
    # (a dead/delisted feed is dropped from the default ranking below). NULL when
    # there is no price history yet -> guard disabled.
    cal_map, fresh_cutoff, dim_thresholds = await asyncio.gather(
        load_active_calibration(pool),
        pool.fetchval(
            """
            SELECT min(date) FROM (
                SELECT DISTINCT date FROM daily_prices ORDER BY date DESC LIMIT $1
            ) t
            """,
            _PRICE_FRESH_TRADING_DAYS,
        ),
        get_dimension_thresholds(pool),
    )
    search_norm = search.strip().upper() if search and search.strip() else None
    # side=short surfaces the bottom of the ranking (most bearish). The
    # direction is a controlled literal derived from the pattern-validated
    # `side`, never raw user input, so the f-string interpolation is safe.
    score_dir = "ASC" if side == "short" else "DESC"
    # DISTINCT ON reduces each table to its latest row per ticker, then
    # UNION ALL stitches them with fast taking precedence (NOT EXISTS
    # drops slow rows whose ticker already came from fast). Dedup, the
    # search filter, sort, and limit all run in SQL so only the rows we
    # actually return get their breakdown JSON parsed below.
    #
    # ORDER BY partial ASC first: a slow-only composite_partial is not
    # on the same scale as a full fast composite, so real fast cards
    # must always outrank partial ones. Within each group, score DESC.
    # Net effect: the default top-N view stays all-real (240 fast
    # cards), partial rows only surface on search or a high limit.
    # Long mode must rank the full eligible universe before applying the
    # requested limit. PostgreSQL treats LIMIT NULL as no limit. Short mode can
    # retain the efficient SQL-side slice because its stored score is already
    # the active ranking score.
    query_limit = None if mode == "long" else limit
    rows = await pool.fetch(
        f"""
        WITH fast_latest AS (
            SELECT DISTINCT ON (ticker)
                ticker, composite AS score, rating,
                confidence, breakdown, fetched_at, false AS partial
            FROM daily_signals_fast
            WHERE composite IS NOT NULL AND composite = composite
            ORDER BY ticker, date DESC, fetched_at DESC
        ),
        slow_latest AS (
            SELECT DISTINCT ON (ticker)
                ticker, composite_partial AS score, NULL::text AS rating,
                NULL::double precision AS confidence, breakdown,
                fetched_at, true AS partial
            FROM daily_signals_slow
            WHERE composite_partial IS NOT NULL
                AND composite_partial = composite_partial
            ORDER BY ticker, date DESC, fetched_at DESC
        ),
        combined AS (
            -- Recency wins, not table-preference: a ticker that dropped out
            -- of the intraday fast set keeps a stale fast row; the old
            -- "fast unless absent" rule let that stale fast shadow a fresher
            -- daily slow row (the 2026-06-01 misaligned-timestamp bug). Take
            -- whichever row is genuinely newest per ticker; the partial flag
            -- stays correct so the ORDER BY below still ranks full fast
            -- cards above partial ones.
            SELECT DISTINCT ON (ticker)
                ticker, score, rating, confidence, breakdown, fetched_at, partial
            FROM (
                SELECT * FROM fast_latest
                UNION ALL
                SELECT * FROM slow_latest
            ) u
            ORDER BY ticker, fetched_at DESC
        )
        SELECT ticker, score, rating, confidence, breakdown,
               fetched_at, partial
        FROM combined
        WHERE ($2::text IS NULL OR ticker ILIKE '%' || $2 || '%')
          -- Drop dead-price-feed tickers from the DEFAULT ranking only (an
          -- explicit search, $2 not null, still surfaces them). Keep a
          -- ticker only if it has a close in the last N sessions. $3 NULL
          -- (no price history) disables the guard.
          AND (
            $2::text IS NOT NULL
            OR $3::date IS NULL
            OR EXISTS (
                SELECT 1 FROM daily_prices dp
                WHERE dp.ticker = combined.ticker AND dp.date >= $3::date
            )
          )
        ORDER BY partial ASC, score {score_dir}
        LIMIT $1
        """,
        query_limit,
        search_norm,
        fresh_cutoff,
    )
    if not rows:
        return [], None, False

    strategic_by_ticker: dict[str, dict] = {}
    if mode == "long":
        def long_mode_score(row) -> float:
            projection = _strategic_projection(row["breakdown"])
            strategic_by_ticker[row["ticker"]] = projection
            return _safe_float(projection.get("composite_score"), 0.0)

        if side == "short":
            rows = sorted(rows, key=lambda r: (r["partial"], long_mode_score(r)))[:limit]
        else:
            rows = sorted(rows, key=lambda r: (r["partial"], -long_mode_score(r)))[:limit]

    # dim_thresholds (universe-wide band breakpoints, so each dimension is graded
    # against its own cross-sectional distribution) was fetched in the gather above.

    # Per-ticker directional consistency (5d/1m/1y/all-time next-day
    # hit-rate) for the returned tickers, in one batched query. Mode/side
    # independent: it reads the stored historical predictions (fast∪slow),
    # not the current card's (possibly long-mode re-ranked) rating. Tallies
    # give both the rates and the evaluated sample counts (for the UI's
    # dash-explanation hover) from a single query.
    from alpha_agent.backtest.consistency import (
        compute_window_tallies,
        rates_from_tallies,
    )
    # HOLD-inclusive consistency (2026-07-26): a second, opt-in 口径 alongside
    # the directional-only rate above (alpha_agent/backtest/consistency.py).
    # d5/m1 only, live-computed — never 500s the picks endpoint: any DB error
    # (or a not-yet-migrated backend) degrades to all-dash rather than taking
    # the whole response down.
    from alpha_agent.backtest.consistency import compute_hold_inclusive_consistency
    tickers = [r["ticker"] for r in rows]

    async def safe_hold_consistency() -> tuple[dict, dict]:
        try:
            return await compute_hold_inclusive_consistency(pool, tickers)
        except Exception as exc:  # noqa: BLE001 — degrade to dash, never 500 the picks page
            # MUST log: a dash from a DB error is indistinguishable on screen
            # from a dash for "not enough samples".
            logger.warning(
                "hold-inclusive consistency unavailable: %s: %s",
                type(exc).__name__,
                exc,
            )
            return {}, {}

    # These enrichments are independent. Run them in one wave so adding the
    # visible price context does not add another transpacific DB round trip.
    tallies_by_ticker, hold_result, market_context_by_ticker = await asyncio.gather(
        compute_window_tallies(pool, tickers),
        safe_hold_consistency(),
        _load_market_context(pool, tickers),
    )
    consistency_by_ticker = rates_from_tallies(tallies_by_ticker)
    cons_hold_by_ticker, cons_hold_n_by_ticker = hold_result

    cards: list[LeanCard] = []
    for r in rows:
        market = market_context_by_ticker.get(r["ticker"], {})
        try:
            parsed_breakdown: dict = json.loads(r["breakdown"])
            breakdown_data: list[dict] = parsed_breakdown.get("breakdown", [])
            tier_flip_today: bool = bool(parsed_breakdown.get("tier_flip_today", False))
        except (TypeError, json.JSONDecodeError):
            breakdown_data = []
            tier_flip_today = False
        score = _safe_float(r["score"], 0.0)
        is_partial = bool(r["partial"])
        if is_partial:
            # Slow-only row: derive rating + confidence the same way the
            # fast cron does, from the partial composite + breakdown z's.
            rating = map_to_tier(score)
            z_values = [
                z for e in breakdown_data
                if isinstance((z := e.get("z")), (int, float))
            ]
            # agreement = raw signal-agreement (conviction headline);
            # confidence = the same value passed through the calibration
            # map (honest hit-rate). Both are surfaced separately.
            agreement = compute_confidence(z_values)
            confidence = apply_calibration(agreement, cal_map)
        else:
            # Fast row: the stored "confidence" column is a raw
            # compute_confidence value from write time -> that IS the
            # agreement. Pass it through the calibration map once to get
            # the displayed hit-rate (single application, not double).
            rating = r["rating"] or "HOLD"
            agreement = _safe_float(r["confidence"], 0.0)
            confidence = apply_calibration(agreement, cal_map)
        if mode == "long":
            projection = strategic_by_ticker.get(r["ticker"])
            if projection is None:
                projection = _strategic_projection(r["breakdown"])
            score = _safe_float(projection.get("composite_score"), 0.0)
            breakdown_data = projection.get("breakdown", [])
            rating = map_to_tier(score)
            z_values = [
                float(entry["z"])
                for entry in breakdown_data
                if _safe_float(entry.get("weight_effective"), 0.0) > 0
                and isinstance(entry.get("z"), (int, float))
            ]
            agreement = compute_confidence(z_values)
            # The existing calibration map is trained on 5d outcomes.  Showing
            # it as a strategic 60d hit rate would be false precision.
            confidence = None

        cards.append(
            LeanCard(
                ticker=r["ticker"],
                company_name=market.get("company_name"),
                company_name_zh=market.get("company_name_zh"),
                latest_price=market.get("latest_price"),
                price_date=market.get("price_date"),
                daily_change_pct=market.get("daily_change_pct"),
                rating=rating,
                confidence=confidence,
                agreement=agreement,
                composite_score=score,
                as_of=r["fetched_at"].isoformat(),
                top_drivers=top_drivers(breakdown_data),
                top_drags=top_drags(breakdown_data),
                partial=is_partial,
                tier_flip_today=tier_flip_today,
                dimension_grades=grade_dimensions(breakdown_data, dim_thresholds),
                consistency=consistency_by_ticker.get(r["ticker"], {}),
                consistency_n={
                    w: n
                    for w, (_h, n) in tallies_by_ticker.get(r["ticker"], {}).items()
                },
                consistency_hold=cons_hold_by_ticker.get(r["ticker"], {}),
                consistency_hold_n=cons_hold_n_by_ticker.get(r["ticker"], {}),
                sleeve="strategic" if mode == "long" else "tactical",
                horizon_days=60 if mode == "long" else 5,
                policy_id=get_policy(
                    "strategic" if mode == "long" else "tactical"
                ).policy_id,
                validation_status=(
                    "forward_validation" if mode == "long" else "production"
                ),
                policy_rank=len(cards) + 1 if side == "long" else None,
            )
        )

    # SQL ordered by short-mode composite; after long-mode swap the
    # short order is stale. Re-sort in Python (partial-last preserved),
    # respecting side: long = score DESC, short = score ASC.
    # Report freshness for the exact visible board. A single recent row must
    # not make older visible recommendations look fresh.
    fetched_times = [datetime.fromisoformat(card.as_of) for card in cards]
    most_recent = max(fetched_times)
    now = datetime.now(UTC)
    stale = any(
        now - fetched_at > timedelta(hours=_STALE_THRESHOLD_HOURS)
        for fetched_at in fetched_times
    )

    return cards, most_recent, stale


@router.get("/lean", response_model=PicksResponse)
async def picks_lean(
    response: Response,
    limit: int = Query(50, ge=1, le=600),
    search: str | None = Query(None, max_length=12),
    mode: str = Query("short", pattern="^(short|long)$"),
    side: str = Query("long", pattern="^(long|short)$"),
) -> PicksResponse:
    """Return tickers ranked by composite score.

    `side` (P1-2 two-sided view): "long" (default) returns the top-N by
    composite DESC — the highest-conviction longs. "short" returns the
    bottom-N by composite ASC — the most bearish names (UW/SELL tier),
    which the default long view never surfaces because they rank at the
    bottom of the universe. Same data + same pipeline; only the sort
    direction + LIMIT slice differ.

    Unions two sources so the full ~557-ticker universe is reachable:
      - daily_signals_fast: the 15-min intraday pipeline (~100 tickers),
        full cards with stored rating + confidence.
      - daily_signals_slow: the daily pipeline (full universe). It stores
        only composite_partial + breakdown, so rating is derived via
        map_to_tier and confidence via compute_confidence from the
        breakdown z's. These rows are flagged partial=True.

    A ticker present in fast is taken from fast (fresher and complete).
    `search` does a case-insensitive substring match on the ticker.

    `mode` (Phase 2 dual-factor): "short" (default, 12d/60d momentum-vol,
    aligned with the rest of the short-window composite) or "long"
    (252d/126d academic Jegadeesh-Titman/Daniel-Moskowitz framework). When
    "long", the full eligible universe is re-ranked in Python using
    factor.raw.z_long (populated by fast_intraday's universe-wide eval) before
    the response limit is applied. Rows without z_long (legacy / partial) keep
    their original composite under either mode.
    """
    try:
        pool = await get_db_pool()
        # The default board is a published product, not a query over mutable
        # ticker rows.  Search remains an explicitly exploratory live view so
        # partial/dead-feed names are still discoverable without gaining a
        # misleading daily rank or an order action.
        if search is None:
            canonical = await _build_canonical_view(
                pool, limit=limit, mode=mode, side=side
            )
            if canonical is not None:
                set_public_cache(response, s_maxage=45, swr=300)
                return canonical

        cards, most_recent, stale = await build_lean_view(
            pool, limit=limit, search=search, mode=mode, side=side
        )
        # 今日推荐 is a global, slow-moving ranked list (intraday cron refreshes
        # ~every 15 min). Edge-cache it so the four serial DB waves in
        # build_lean_view run at most once per window instead of on every open —
        # this is the surface that queues worst behind cron writes.
        set_public_cache(response, s_maxage=45, swr=300)
        return PicksResponse(
            picks=cards,
            as_of=most_recent,
            stale=stale,
            canonical=False,
            ranked=False,
            tradable=False,
        )
    except Exception as e:
        from fastapi import HTTPException

        request_id = uuid.uuid4().hex[:12]
        logger.exception("picks_lean failed request_id=%s", request_id)
        raise HTTPException(
            status_code=500,
            detail={
                "code": "PICKS_UNAVAILABLE",
                "message": "Recommendation data is temporarily unavailable",
                "request_id": request_id,
                "retryable": True,
            },
        ) from e


@router.get("/scoreboard", response_model=ScoreboardResponse | None)
async def picks_scoreboard(
    response: Response,
    top_n: int = Query(10, ge=3, le=50),
    days: int = Query(21, ge=5, le=63),
) -> ScoreboardResponse | None:
    """Portfolio-level picks evaluation over the trailing window. Reconstructs
    each day's top/bottom-K basket from the signals as stored THAT day (no
    lookahead) and scores realized next-day returns against the universe
    average + the always-up base rate. Returns null (not an error) when there
    is too little realized history to say anything. Changes ~once per trading
    day -> cached aggressively at the edge."""
    from alpha_agent.backtest.scoreboard import compute_picks_scoreboard

    pool = await get_db_pool()
    sb = await compute_picks_scoreboard(pool, top_n=top_n, days=days)
    set_public_cache(response, s_maxage=3600, swr=86400)
    if sb is None:
        return None
    return ScoreboardResponse(
        days=sb.days, top_n=sb.top_n, long_cum=sb.long_cum,
        short_cum=sb.short_cum, market_cum=sb.market_cum,
        spread_cum=sb.spread_cum, long_hit_rate=sb.long_hit_rate,
        base_rate=sb.base_rate,
        spy_cum=sb.spy_cum,
        mean_daily_turnover=sb.mean_daily_turnover,
        long_net_cum=sb.long_net_cum,
        cost_bps_used=sb.cost_bps_used,
        breakeven_cost_bps=sb.breakeven_cost_bps,
        beta=sb.beta,
        alpha_ann=sb.alpha_ann,
        alpha_t=sb.alpha_t,
    )
