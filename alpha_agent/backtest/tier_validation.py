"""Signal pruning by incremental contribution + tier monotonicity (step 7).

Two NON-destructive diagnostics — they flag/report, they never delete a signal.
The council was explicit (split-5): prune a signal ONLY if it is weak on EVERY
axis at once; never hard-drop on low IC alone, because a decorrelated, cheap,
low-turnover signal that still contributes (RSRS) earns its keep. And tiers that
look authoritative must be statistically monotone (BUY > OW > HOLD > UW > SELL
by forward return) or the product is lying with confidence.
"""
from __future__ import annotations

# Pruning thresholds. A signal must clear ALL of these (weak on every axis) to
# be a prune candidate. Conservative on purpose: the cost of dropping a useful
# decorrelated signal is higher than keeping a marginal one.
_IC_LOW = 0.02            # |IC| below this is "low"
_CORR_HIGH = 0.7          # max pairwise correlation above this is "redundant"
_COVERAGE_LOW = 0.5       # present on < half the universe is "poor coverage"
_MAINT_HIGH = 0.7         # normalized maintenance cost above this is "high"
_FWD_NONE = 0.0           # forward / L2 contribution at or below this is "none"

# Tier order, strongest to weakest. Monotonicity = each >= the next.
_TIER_ORDER = ("BUY", "OW", "HOLD", "UW", "SELL")
_BULLISH = frozenset({"BUY", "OW"})
_BEARISH = frozenset({"UW", "SELL"})


def prune_candidates(metrics: dict[str, dict], *, thresholds: dict | None = None) -> list[dict]:
    """Flag signals weak on EVERY axis. metrics[name] = {ic, max_corr, coverage,
    maintenance, forward_contribution}. Returns [{signal, reasons[]}] only for
    signals that meet ALL five criteria. A single strong axis spares the signal."""
    t = {
        "ic_low": _IC_LOW, "corr_high": _CORR_HIGH, "coverage_low": _COVERAGE_LOW,
        "maint_high": _MAINT_HIGH, "fwd_none": _FWD_NONE, **(thresholds or {}),
    }
    out: list[dict] = []
    for name, m in metrics.items():
        reasons = []
        if abs(m.get("ic", 0.0)) < t["ic_low"]:
            reasons.append("low_ic")
        if m.get("max_corr", 0.0) > t["corr_high"]:
            reasons.append("redundant")
        if m.get("coverage", 1.0) < t["coverage_low"]:
            reasons.append("poor_coverage")
        if m.get("maintenance", 0.0) > t["maint_high"]:
            reasons.append("high_maintenance")
        if m.get("forward_contribution", 0.0) <= t["fwd_none"]:
            reasons.append("no_forward_contribution")
        # ALL five must hold — never prune on a subset (e.g. low IC alone).
        if len(reasons) == 5:
            out.append({"signal": name, "reasons": reasons})
    return out


async def tier_monotonicity(pool, *, horizon_days: int = 5) -> dict:
    """Per-tier forward return / hit-rate / count from the ledger's complete-run
    snapshots vs daily_prices, and whether BUY >= OW >= HOLD >= UW >= SELL holds.

    Forward return uses LEAD(close, horizon) over each ticker's price series at
    the snapshot's run date. Only eligible snapshots from COMPLETE runs count.
    """
    rows = await pool.fetch(
        """
        WITH snap AS (
            SELECT rs.tier, rs.ticker, rr.scheduled_for_date AS d
            FROM rating_snapshot rs
            JOIN research_run rr ON rr.id = rs.run_id
            WHERE rr.status = 'complete' AND rs.eligible AND rs.tier IS NOT NULL
        ),
        fwd AS (
            SELECT ticker, date, close AS c0,
                   LEAD(close, $1) OVER (PARTITION BY ticker ORDER BY date) AS ch
            FROM daily_prices
        )
        SELECT s.tier, (f.ch / f.c0 - 1.0) AS ret
        FROM snap s
        JOIN fwd f ON f.ticker = s.ticker AND f.date = s.d
        WHERE f.ch IS NOT NULL AND f.c0 > 0
        """,
        horizon_days,
    )

    by_tier: dict[str, list[float]] = {}
    for r in rows:
        by_tier.setdefault(r["tier"], []).append(float(r["ret"]))

    tiers: dict[str, dict] = {}
    for tier, rets in by_tier.items():
        n = len(rets)
        mean_ret = sum(rets) / n if n else None
        hit_rate = _hit_rate(tier, rets)
        tiers[tier] = {"mean_ret": mean_ret, "hit_rate": hit_rate, "n": n}

    # Monotonicity over the tiers actually present, in canonical order.
    present = [t for t in _TIER_ORDER if t in tiers]
    violations = []
    for a, b in zip(present, present[1:]):
        if tiers[a]["mean_ret"] is not None and tiers[b]["mean_ret"] is not None:
            if tiers[a]["mean_ret"] < tiers[b]["mean_ret"]:
                violations.append({"higher": a, "lower": b,
                                   "higher_ret": tiers[a]["mean_ret"],
                                   "lower_ret": tiers[b]["mean_ret"]})

    return {"tiers": tiers, "monotonic": not violations, "violations": violations,
            "horizon_days": horizon_days}


def _hit_rate(tier: str, rets: list[float]) -> float | None:
    """Fraction of snapshots whose return sign matches the tier's direction.
    HOLD is non-directional -> None."""
    if not rets:
        return None
    if tier in _BULLISH:
        return sum(1 for r in rets if r > 0) / len(rets)
    if tier in _BEARISH:
        return sum(1 for r in rets if r < 0) / len(rets)
    return None  # HOLD
