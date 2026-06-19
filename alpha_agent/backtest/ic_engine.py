"""Walk-forward IC backtest engine + adaptive weight orchestration.

For each active signal x window in {30, 60, 90} days, computes Spearman
rank IC between (signal value at as_of, forward 5-day return) over the
window of as_of dates. Strict walk-forward: never uses any data from
after as_of in either side of the IC calculation.

Weight production (Phase 1b): after the IC-history loop, calls
``apply_adaptive_weights`` (EWMA-ICIR + change-cap + floor/hard-drop +
shadow/promote/rollback). The old inline mean-IC rule has been removed.

Citation: walk-forward methodology follows MacKinlay (1997). Spearman
chosen over Pearson per Tetlock 2007 convention (more robust to
heavy-tailed return distributions).

Schema adaptation note (plan vs reality):
  - Plan example SQL assumed daily_signals_fast(ticker, as_of, signal_name, z)
    and daily_prices(ticker, ts, close). Real V001 schema is
    daily_signals_fast(ticker, date, composite, breakdown JSONB, ...)
    where individual signal entries live inside breakdown as a JSON list
    of objects {signal, z, confidence, ...}.

  - The walk-forward query unnests the breakdown JSONB, filters by signal
    name, and computes the forward return via LEAD(close, 5) OVER
    (PARTITION BY ticker ORDER BY date) on daily_prices. Because
    daily_prices only ever holds trading days, LEAD(close, 5) is exactly
    5 trading days ahead. Rows where close_exit IS NULL (no observable
    exit yet) are naturally excluded, enforcing the walk-forward guarantee.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np

from alpha_agent.signals.horizons import DEFAULT_HORIZON_DAYS, native_horizon


def _spearman_rho(xs, ys):
    """Spearman rank correlation via numpy only (no scipy).
    Returns NaN if degenerate (constant input)."""
    xs = np.asarray(xs, dtype=float)
    ys = np.asarray(ys, dtype=float)
    if len(xs) < 2 or len(ys) < 2:
        return float("nan")
    rxs = np.argsort(np.argsort(xs)).astype(float)
    rys = np.argsort(np.argsort(ys)).astype(float)
    if np.std(rxs) == 0 or np.std(rys) == 0:
        return float("nan")
    return float(np.corrcoef(rxs, rys)[0, 1])


# Active signals to backtest. Sourced from the production signal map
# (alpha_agent.signals.*) plus the Phase 6a T6 political_impact signal.
# Must be kept in lockstep with the registry used in fusion.combine.
_ACTIVE_SIGNALS: tuple[str, ...] = (
    "factor",
    "technicals",
    "rsrs",  # forward IC tracking for the RSRS timing tilt (native horizon 20d)
    "analyst",
    "earnings",
    "news",
    "insider",
    "options",
    "premarket",
    "macro",
    "calendar",
    "political_impact",
    # serenity seam #2 (2026-06-17): start forward IC tracking for the
    # supply_chain bottleneck signal. compute_walk_forward_ic returns None
    # (insufficient) until the daily fast cron has accumulated enough
    # supply_chain z history for a 5d-forward-observable window, so nothing is
    # written to signal_ic_history yet. apply_adaptive_weights treats a no-IC
    # signal as "bad" and would shrink it toward the floor, but it writes only
    # to signal_weight_current, which NO live cron reads (fast_intraday +
    # slow_daily both fuse on DEFAULT_WEIGHTS), so the live 0.05 weight is
    # untouched. This is pure measurement: it lets ic_backtest_monthly emit a
    # real IC for supply_chain once ~3-4 weeks of history exist, so the weight
    # can later be tuned on evidence instead of a guess.
    "supply_chain",
)

_WINDOWS: tuple[int, ...] = (30, 60, 90)
_FWD_RET_DAYS: int = 5
_IC_THRESHOLD: float = 0.02
_MIN_OBS: int = 10
_DEFAULT_NORMALIZE: float = 1.0  # rolling-vol normalization is a future enhancement


async def compute_walk_forward_ic(
    pool,
    signal_name: str,
    window_days: int,
    horizon_days: int = _FWD_RET_DAYS,
) -> tuple[float, int] | None:
    """Return (Spearman rank IC, n_observations) for `signal_name` over
    `window_days` of as_of dates, against a `horizon_days`-trading-day forward
    return. None if fewer than `_MIN_OBS` observations or if Spearman is NaN.

    Decision-time contract (council #3 — IC pipeline correctness):
      - The z is read from the daily_signals_fast row stored ON its as_of
        date; entry is that date's close, exit is the close `horizon_days`
        trading rows later. The IC assumes a decision made at the as_of close
        from only that day's (and earlier) data. Signals must NOT be backfilled
        with later-arriving data, or a past as_of would leak the future.
      - Walk-forward: as_of is restricted to [now - window_days,
        now - horizon_days] so every forward window is fully in the past.
      - daily_prices.close is split/dividend adjusted, so entry/exit is a
        clean total return.
      - Missing-row guard (council #3): LEAD counts ROWS, not calendar days, so
        a halted/holiday-gapped ticker could stretch the real interval. Rows
        whose exit date is more than ~2x the horizon in calendar days ahead are
        excluded so a stale exit price cannot pollute the IC.
    """
    if not isinstance(horizon_days, int) or horizon_days < 1:
        raise ValueError(
            f"horizon_days must be a positive int, got {horizon_days!r}"
        )
    now = datetime.now(UTC)
    window_start = (now - timedelta(days=window_days)).date()
    # as_of must be early enough that the horizon-forward exit is itself in the
    # past; otherwise we would be peeking ahead.
    fwd_cutoff = (now - timedelta(days=horizon_days)).date()
    # Reject exits where missing rows stretched the real window too far: at most
    # horizon_days trading days (~horizon_days*7/5 calendar days); allow a
    # weekend + holiday buffer.
    max_span_days = horizon_days * 2 + 4

    # horizon_days is a validated positive int (not user input) so interpolating
    # it into LEAD()'s offset is injection-safe; LEAD offsets cannot be bound.
    rows = await pool.fetch(
        f"""
        WITH sig AS (
            SELECT
                f.ticker,
                f.date AS as_of,
                (elem->>'z')::double precision AS signal_z
            FROM daily_signals_fast f
            CROSS JOIN LATERAL jsonb_array_elements(f.breakdown->'breakdown') AS elem
            WHERE elem->>'signal' = $1
              AND f.date >= $2
              AND f.date <= $3
              AND (elem->>'z') IS NOT NULL
        ),
        fwd AS (
            SELECT
                ticker,
                date,
                close AS close_entry,
                LEAD(close, {horizon_days}) OVER (PARTITION BY ticker ORDER BY date) AS close_exit,
                LEAD(date, {horizon_days}) OVER (PARTITION BY ticker ORDER BY date) AS date_exit
            FROM daily_prices
        )
        SELECT
            s.signal_z,
            (fwd.close_exit / fwd.close_entry - 1)::double precision AS fwd_ret
        FROM sig s
        JOIN fwd
          ON fwd.ticker = s.ticker
         AND fwd.date = s.as_of
        WHERE fwd.close_entry > 0
          AND fwd.close_exit IS NOT NULL
          AND fwd.date_exit IS NOT NULL
          AND (fwd.date_exit - fwd.date) <= $4
        """,
        signal_name,
        window_start,
        fwd_cutoff,
        max_span_days,
    )
    if len(rows) < _MIN_OBS:
        return None
    xs = np.array([float(r["signal_z"]) for r in rows])
    ys = np.array([float(r["fwd_ret"]) for r in rows])
    rho = _spearman_rho(xs, ys)
    if rho is None or np.isnan(rho):
        return None
    return float(rho), len(xs)


async def run_monthly_ic_backtest(pool) -> int:
    """For each active signal: compute IC over 3 windows at BOTH the 5d
    reference horizon (cross-signal comparison) and the signal's native horizon
    (council #4 — horizon-coherent validation), writing each successful
    (signal, window, horizon) to signal_ic_history. Returns the count of
    signals processed.

    Weight production is delegated entirely to the Phase 1b adaptive layer
    (EWMA-ICIR + change-cap + floor/hard-drop + shadow/promote/rollback)
    via ``apply_adaptive_weights``, which is called once after the IC-history
    loop completes.  The old inline mean-IC weight rule has been removed.

    Skip-recent guard: signals whose weight row was updated within the last
    hour are skipped so multiple short-lived cron invocations can resume
    from where the previous one was killed (Vercel hobby 5-min function cap).
    """
    now = datetime.now(UTC)
    updated = 0
    skip_threshold = now - timedelta(hours=1)
    for sig_name in _ACTIVE_SIGNALS:
        existing = await pool.fetchval(
            "SELECT last_updated FROM signal_weight_current "
            "WHERE signal_name = $1 AND status = 'live'",
            sig_name,
        )
        if existing is not None and existing > skip_threshold:
            continue
        # Evaluate at the 5d reference horizon + the signal's native horizon
        # (deduped). Judging a 60d signal like factor only on 5d IC is
        # horizon-incoherent (council #4).
        horizons = sorted({DEFAULT_HORIZON_DAYS, native_horizon(sig_name)})
        for w in _WINDOWS:
            for h in horizons:
                result = await compute_walk_forward_ic(
                    pool, sig_name, w, horizon_days=h
                )
                if result is None:
                    continue
                ic, n_obs = result
                await pool.execute(
                    """
                    INSERT INTO signal_ic_history
                        (signal_name, window_days, horizon_days, ic,
                         n_observations, computed_at)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (signal_name, window_days, horizon_days, computed_at)
                    DO NOTHING
                    """,
                    sig_name, w, h, ic, n_obs, now,
                )
        updated += 1

    from alpha_agent.backtest.adaptive_weights import (
        apply_adaptive_weights,
        compute_guarded_shadow,
    )
    await apply_adaptive_weights(pool, _ACTIVE_SIGNALS)
    # council #6: compute the guarded-shrinkage shadow (prior = the uncapped
    # static baseline, evidence = the aggressive adaptive candidate) for
    # side-by-side comparison. NOT promoted live; nothing reads guarded_shadow
    # for fusion. Live weighting stays the explicit static policy.
    from alpha_agent.fusion.policy import STATIC_V1
    await compute_guarded_shadow(pool, dict(STATIC_V1.weights), _ACTIVE_SIGNALS)
    return updated
