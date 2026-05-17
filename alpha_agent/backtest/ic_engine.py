"""Walk-forward IC backtest engine + dynamic signal weight writer.

For each active signal x window in {30, 60, 90} days, computes Spearman
rank IC between (signal value at as_of, forward 5-day return) over the
window of as_of dates. Strict walk-forward: never uses any data from
after as_of in either side of the IC calculation.

Weight rule (Phase 6a spec decision 6):
  - if min(ic_30d, ic_60d, ic_90d) < 0.02 -> weight = 0 (auto_dropped_low_ic)
  - else weight = mean(ics) * vol_normalize_factor(signal_name)

Citation: walk-forward methodology follows MacKinlay (1997). Spearman
chosen over Pearson per Tetlock 2007 convention (more robust to
heavy-tailed return distributions).

Schema adaptation note (plan vs reality):
  - Plan example SQL assumed daily_signals_fast(ticker, as_of, signal_name, z)
    and daily_prices(ticker, ts, close). Real V001 schema is
    daily_signals_fast(ticker, date, composite, breakdown JSONB, ...)
    where individual signal entries live inside breakdown as a JSON list
    of objects {signal, z, confidence, ...}. There is no daily_prices
    table; V005 minute_bars(ticker, ts, close) is the only price store.

  - The walk-forward query therefore unnests the breakdown JSONB, filters
    by signal name, and joins entry/exit minute_bars rows at ts = date
    and ts = date + 5 days. If callers need intra-day price granularity
    they can extend the entry/exit join to take the last close on the day.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np


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
    "analyst",
    "earnings",
    "news",
    "insider",
    "options",
    "premarket",
    "macro",
    "calendar",
    "political_impact",
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
) -> tuple[float, int] | None:
    """Return (Spearman rank IC, n_observations) for the signal over
    `window_days`. None if fewer than `_MIN_OBS` observations
    (insufficient statistical power) or if Spearman returns NaN.

    Walk-forward guarantee:
      - signal as_of (date) is restricted to [now - window_days, now - 5d]
        so every forward return ts (= as_of + 5d) is observable in the past.
      - forward return uses minute_bars at as_of (entry) and as_of + 5d
        (exit). The engine never references now() in the return leg.
    """
    now = datetime.now(UTC)
    window_start = (now - timedelta(days=window_days)).date()
    # Signal as_of must be early enough that the 5d-forward exit price
    # is itself in the past; otherwise we would be peeking ahead.
    fwd_cutoff = (now - timedelta(days=_FWD_RET_DAYS)).date()

    rows = await pool.fetch(
        """
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
        )
        SELECT
            s.signal_z,
            (p_end.close / p_start.close - 1)::double precision AS fwd_5d
        FROM sig s
        JOIN minute_bars p_start
          ON p_start.ticker = s.ticker
         AND (p_start.ts AT TIME ZONE 'UTC')::date = s.as_of
        JOIN minute_bars p_end
          ON p_end.ticker = s.ticker
         AND (p_end.ts AT TIME ZONE 'UTC')::date = (s.as_of + interval '5 days')::date
        WHERE p_start.close > 0
        """,
        signal_name,
        window_start,
        fwd_cutoff,
    )
    if len(rows) < _MIN_OBS:
        return None
    xs = np.array([float(r["signal_z"]) for r in rows])
    ys = np.array([float(r["fwd_5d"]) for r in rows])
    rho = _spearman_rho(xs, ys)
    if rho is None or np.isnan(rho):
        return None
    return float(rho), len(xs)


async def run_monthly_ic_backtest(pool) -> int:
    """For each active signal: compute IC over 3 windows, write each
    successful (signal, window) to signal_ic_history, then upsert the
    aggregated weight to signal_weight_current. Returns the count of
    signals whose weight row was upserted.

    Weight rule:
      - no window produced an IC at all (insufficient observations across
        every window) -> weight = 0, reason = "insufficient_data". This
        is the framework's "data accumulating" state; the UI distinguishes
        it from auto_dropped_low_ic so users do not misread early-life
        signals as "broken".
      - any IC was computed but min(IC) < threshold -> weight = 0,
        reason = "auto_dropped_low_ic". The signal had a fair shot and
        failed.
      - else weight = mean(IC) * _DEFAULT_NORMALIZE, reason "ic_above_threshold".
    """
    now = datetime.now(UTC)
    updated = 0
    # Skip signals whose weight row was upserted within the last hour to
    # let multiple short-lived cron invocations resume from where the
    # previous one was killed (Vercel hobby 5-min function cap, full
    # 11-signal scan takes longer on a large daily_signals_fast table).
    # Monthly cron fires once per month; the recent-skip is harmless then
    # because last_updated will be ~30 days old by next fire.
    skip_threshold = now - timedelta(hours=1)
    for sig_name in _ACTIVE_SIGNALS:
        existing = await pool.fetchval(
            "SELECT last_updated FROM signal_weight_current WHERE signal_name = $1",
            sig_name,
        )
        if existing is not None and existing > skip_threshold:
            continue
        ics: dict[int, float | None] = {}
        for w in _WINDOWS:
            result = await compute_walk_forward_ic(pool, sig_name, w)
            if result is None:
                ics[w] = None
                continue
            ic, n_obs = result
            ics[w] = ic
            await pool.execute(
                """
                INSERT INTO signal_ic_history
                    (signal_name, window_days, ic, n_observations, computed_at)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (signal_name, window_days, computed_at) DO NOTHING
                """,
                sig_name, w, ic, n_obs, now,
            )

        valid_ics = [v for v in ics.values() if v is not None]
        if not valid_ics:
            weight = 0.0
            reason = "insufficient_data"
        elif min(valid_ics) < _IC_THRESHOLD:
            weight = 0.0
            reason = "auto_dropped_low_ic"
        else:
            weight = float(np.mean(valid_ics) * _DEFAULT_NORMALIZE)
            reason = "ic_above_threshold"
        await pool.execute(
            """
            INSERT INTO signal_weight_current
                (signal_name, weight, last_updated, reason)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (signal_name) DO UPDATE SET
                weight = EXCLUDED.weight,
                last_updated = EXCLUDED.last_updated,
                reason = EXCLUDED.reason
            """,
            sig_name, weight, now, reason,
        )
        updated += 1
    return updated
