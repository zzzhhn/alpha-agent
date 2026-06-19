"""Run-health / abstention gates (roadmap step 2).

A run that finished is not automatically tradable truth. evaluate_gates scores
a run's emitted snapshots against hard gates and returns the GATED status:
'complete' (healthy, canonical, tradable) when every hard gate passes, else
'partial' (recorded for forensics but excluded by get_canonical_run, so L2 /
forward-IC never consume it). Reasons + metrics are machine-readable.

Honesty (UI/UX principle 9): only metrics actually computable from the
recorded data are reported. Gates the ledger cannot yet support (sector
concentration, failed-signal count) are intentionally absent rather than
fabricated; they arrive when their inputs are recorded.

Pure decision: the one DB-dependent input (benchmark availability) is passed in
as a bool by the caller, so this module has no DB coupling and is trivially
testable. benchmark_is_fresh() is the small async helper the writer uses to
compute that bool.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from alpha_agent.storage.product_ledger import RatingSnapshot

# A run with fewer than this many eligible names is not a trustworthy product
# state (the pipeline largely failed, or coverage collapsed). Tunable; chosen
# conservatively low so only genuinely degenerate runs are gated out.
MIN_ELIGIBLE = 20

# A held/recommended book is only measurable against a benchmark; a run with no
# fresh SPY close cannot anchor the L2 product test, so it is non-tradable.
_BENCHMARK_TICKER = "SPY"

_TIERS = ("BUY", "OW", "HOLD", "UW", "SELL")


@dataclass(frozen=True)
class GateResult:
    passed: bool
    status: str  # 'complete' when passed else 'partial'
    reasons: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def evaluate_gates(
    snapshots: list[RatingSnapshot],
    *,
    benchmark_fresh: bool,
    min_eligible: int = MIN_ELIGIBLE,
) -> GateResult:
    """Score a run. Returns the gated status + reasons + metrics.

    Hard gates (any failure -> non-tradable 'partial'):
      - insufficient_eligible: fewer than min_eligible eligible snapshots.
      - no_benchmark: benchmark_fresh is False.
    """
    eligible = [s for s in snapshots if s.eligible]
    eligible_count = len(eligible)

    tier_counts = {t: 0 for t in _TIERS}
    for s in eligible:
        if s.tier in tier_counts:
            tier_counts[s.tier] += 1

    reasons: list[str] = []
    if eligible_count < min_eligible:
        reasons.append(f"insufficient_eligible:{eligible_count}<{min_eligible}")
    if not benchmark_fresh:
        reasons.append("no_benchmark")

    passed = not reasons
    metrics = {
        "eligible_count": eligible_count,
        "tier_counts": tier_counts,
        "benchmark_fresh": benchmark_fresh,
    }
    return GateResult(
        passed=passed,
        status="complete" if passed else "partial",
        reasons=reasons,
        metrics=metrics,
    )


async def benchmark_is_fresh(
    pool,
    *,
    fresh_trading_days: int = 3,
    ticker: str = _BENCHMARK_TICKER,
) -> bool:
    """True if the benchmark has a close within the last `fresh_trading_days`
    distinct market dates in daily_prices. Uses the market's own latest dates
    (same idiom as the picks dead-feed guard) so it tolerates the normal
    price-vs-signal lag. False when there is no price history at all."""
    fresh_cutoff = await pool.fetchval(
        """
        SELECT min(date) FROM (
            SELECT DISTINCT date FROM daily_prices ORDER BY date DESC LIMIT $1
        ) t
        """,
        fresh_trading_days,
    )
    if fresh_cutoff is None:
        return False
    return bool(
        await pool.fetchval(
            "SELECT EXISTS (SELECT 1 FROM daily_prices "
            "WHERE ticker = $1 AND date >= $2)",
            ticker, fresh_cutoff,
        )
    )
