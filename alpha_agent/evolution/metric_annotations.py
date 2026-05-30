"""Metric-change annotation compute (Traceability, UI/UX principle 11).

P0 covers signal IC. For each signal's IC time-series, flag the days where
the value moved materially (|delta| >= threshold) or crossed zero, and record
the change as a structured, correlation-grounded annotation: prev/curr/delta
+ sign-flip + any real co-occurring system events (weight-config changes
logged the same day). No LLM, no causal speculation — an empty co_occurring
list honestly means "no recorded system cause" (market-driven).

The narrative sentence is templated on the frontend from these facts, so the
record is bilingual for free and never editorializes beyond what happened.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

# Materiality bar for an IC move. IC is a rank correlation in [-1, 1]; a 0.05
# day-over-day shift is a meaningful change in a signal's predictive power.
# Sign flips are always flagged regardless of magnitude (crossing zero means
# the signal switched from helping to hurting, or vice versa).
_DEFAULT_THRESHOLD = 0.05


def _sign_flip(prev: float, curr: float) -> bool:
    return (prev > 0 and curr < 0) or (prev < 0 and curr > 0)


async def _weight_changes_by_date(pool) -> dict[str, list[dict[str, Any]]]:
    """Map YYYY-MM-DD -> list of same-day weight-config changes. These are the
    only cleanly day-specific system events we can attribute to an IC move."""
    rows = await pool.fetch(
        "SELECT id, source, changed_at FROM config_change_log "
        "WHERE field = 'signal_weights' AND source LIKE 'auto_%' "
        "ORDER BY changed_at"
    )
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        day = r["changed_at"].date().isoformat()
        by_date[day].append(
            {"type": "weight_change", "source": r["source"], "change_id": r["id"]}
        )
    return by_date


async def compute_ic_annotations(
    pool, window_days: int = 30, threshold: float = _DEFAULT_THRESHOLD
) -> int:
    """Scan signal_ic_history for material IC moves and upsert annotations.
    Idempotent: re-running refreshes existing (metric, key, window, day) rows.
    Returns the number of annotations written."""
    rows = await pool.fetch(
        "SELECT signal_name, computed_at, ic FROM signal_ic_history "
        "WHERE window_days = $1 ORDER BY signal_name, computed_at",
        window_days,
    )
    by_signal: dict[str, list[tuple]] = defaultdict(list)
    for r in rows:
        by_signal[r["signal_name"]].append((r["computed_at"], float(r["ic"])))

    weight_changes = await _weight_changes_by_date(pool)

    written = 0
    for signal_name, series in by_signal.items():
        for i in range(1, len(series)):
            prev_at, prev_ic = series[i - 1]
            curr_at, curr_ic = series[i]
            delta = curr_ic - prev_ic
            flip = _sign_flip(prev_ic, curr_ic)
            if abs(delta) < threshold and not flip:
                continue

            day = curr_at.date().isoformat()
            co_occurring = list(weight_changes.get(day, []))

            await pool.execute(
                "INSERT INTO metric_change_annotation "
                "(metric_type, metric_key, window_days, as_of, prev_value, "
                " curr_value, delta, sign_flip, co_occurring) "
                "VALUES ('signal_ic', $1, $2, $3, $4, $5, $6, $7, $8::jsonb) "
                "ON CONFLICT (metric_type, metric_key, window_days, as_of) "
                "DO UPDATE SET prev_value = EXCLUDED.prev_value, "
                "  curr_value = EXCLUDED.curr_value, delta = EXCLUDED.delta, "
                "  sign_flip = EXCLUDED.sign_flip, "
                "  co_occurring = EXCLUDED.co_occurring",
                signal_name,
                window_days,
                curr_at,
                round(prev_ic, 5),
                round(curr_ic, 5),
                round(delta, 5),
                flip,
                json.dumps(co_occurring),
            )
            written += 1
    return written


async def fetch_ic_annotations(pool, window_days: int = 30) -> list[dict[str, Any]]:
    """Return IC annotations for the chart overlay, keyed so the frontend can
    match each to its (signal, computed_at) point."""
    rows = await pool.fetch(
        "SELECT metric_key, as_of, prev_value, curr_value, delta, sign_flip, "
        "co_occurring FROM metric_change_annotation "
        "WHERE metric_type = 'signal_ic' AND window_days = $1 "
        "ORDER BY as_of",
        window_days,
    )
    out: list[dict[str, Any]] = []
    for r in rows:
        co = r["co_occurring"]
        if isinstance(co, str):
            co = json.loads(co)
        out.append(
            {
                "signal_name": r["metric_key"],
                "as_of": r["as_of"].isoformat(),
                "prev": float(r["prev_value"]) if r["prev_value"] is not None else None,
                "curr": float(r["curr_value"]) if r["curr_value"] is not None else None,
                "delta": float(r["delta"]) if r["delta"] is not None else None,
                "sign_flip": bool(r["sign_flip"]),
                "co_occurring": co or [],
            }
        )
    return out
