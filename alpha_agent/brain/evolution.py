"""Phase F3: self-evolution for the BRAIN miner.

The failure mode of a static generator is homogenization: it keeps proposing the
same structures/ratios, so new alphas correlate with ones already mined and fail
BRAIN's SELF_CORRELATION threshold. This module reads the mining HISTORY
(brain_alphas — every past candidate, its outcome, and its self-correlation) and
distills evolution hints that steer the next round toward diversity:

  - avoid_signatures: structure fingerprints already tried (cross-round dedup),
    so the miner doesn't re-walk ground it has covered.
  - ratio_usage: how often each economic ratio has been used, so the generator
    can prefer under-explored ones.
  - prefer_industry: when the recent SELF_CORRELATION-flagged rate is high, rotate
    neutralization SUBINDUSTRY -> INDUSTRY — the documented escape (different
    peer grouping decorrelates from existing SUBINDUSTRY-neutral alphas).

The loop is self-reinforcing: this round's results become next round's memory,
with no human retuning."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field


def expr_signature(expr: str) -> str:
    """A structure fingerprint of an expression STRING that ignores window/param
    numbers and whitespace, so two alphas differing only by a window collapse to
    the same signature. Grammar-free (works on BRAIN fundamental fields the local
    parser doesn't know)."""
    return re.sub(r"\d+", "N", expr).replace(" ", "")


_RATIO_RE = re.compile(r"divide\(\s*([a-z0-9_]+)\s*,\s*([a-z0-9_]+)\s*\)")


def ratios_in(expr: str) -> list[tuple[str, str]]:
    """The (numerator, denominator) field pairs of every divide() in an
    expression — the economic ratios it uses."""
    return [(m.group(1), m.group(2)) for m in _RATIO_RE.finditer(expr)]


@dataclass(frozen=True)
class EvolutionState:
    avoid_signatures: frozenset = frozenset()
    ratio_usage: dict = field(default_factory=dict)
    flagged_rate: float = 0.0
    prefer_industry: bool = False


# This is NOT the self-correlation cutoff (that's 0.7, matching BRAIN, in
# mining_loop._SELF_CORR_THRESHOLD). It's a RATE: only once this fraction of
# recent alphas has been self-corr-flagged do we start rotating neutralization
# to INDUSTRY. Kept modest (0.4) so a couple of flagged alphas don't over-eagerly
# rotate the whole book.
_FLAG_ROTATE_THRESHOLD = 0.4


def build_evolution_state(rows: list[dict]) -> EvolutionState:
    """Distill hints from recent brain_alphas rows (each: expression, outcome).
    Pure — the DB read lives in load_evolution_state so this is unit-testable."""
    if not rows:
        return EvolutionState()
    sigs = {expr_signature(r["expression"]) for r in rows if r.get("expression")}
    ratio_counts: Counter = Counter()
    for r in rows:
        for pair in ratios_in(r.get("expression") or ""):
            ratio_counts[pair] += 1
    gated = sum(1 for r in rows if r.get("outcome") == "flagged")
    considered = sum(
        1 for r in rows if r.get("outcome") in ("flagged", "passed", "rejected")
    )
    flagged_rate = (gated / considered) if considered else 0.0
    return EvolutionState(
        avoid_signatures=frozenset(sigs),
        ratio_usage=dict(ratio_counts),
        flagged_rate=flagged_rate,
        prefer_industry=flagged_rate >= _FLAG_ROTATE_THRESHOLD,
    )


async def load_evolution_state(pool, user_id: int, *, lookback: int = 300):
    """Read the user's recent mined alphas and build the evolution state.
    Best-effort — a read failure yields an empty state (no steering)."""
    try:
        rows = await pool.fetch(
            "SELECT expression, outcome FROM brain_alphas "
            "WHERE user_id=$1 ORDER BY created_at DESC LIMIT $2",
            user_id, lookback,
        )
    except Exception:  # noqa: BLE001 — evolution is auxiliary
        return EvolutionState()
    return build_evolution_state([dict(r) for r in rows])


def family_of(expr: str) -> str:
    """Coarse economic family of an alpha expression, for the #1/#2 book-saturation
    cap. options/revision are the value-orthogonal new sources; everything built on
    fundamental ratios collapses into the co-moving 'value' cluster."""
    e = expr or ""
    if re.search(r"implied_volatility|pcr_oi|historical_volatility", e):
        return "options"
    if re.search(r"beta_last|systematic_risk|unsystematic_risk|correlation_last", e):
        return "lowvol"
    if re.search(r"scl12_|snt_|snt1_|mood_indicator", e):
        return "sentiment"
    if re.search(r"_day_price_ratio|_week_price_ratio|earnings_momentum", e):
        return "momentum"
    if re.search(r"_score|_rank_derivative|distress_risk|asset_growth_rate|"
                 r"consensus_analyst_rating|earnings_revision_magnitude", e):
        return "score"
    if "anl4_" in e:
        return "revision"
    if re.search(r"cap|enterprise_value|assets|equity|debt|operating_income|"
                 r"ebit|ebitda|cashflow|\beps\b|bookvalue|fscore", e):
        return "value"
    if re.search(r"ts_std_dev\(returns", e):
        return "lowvol"
    if re.search(r"returns|ts_delta\(close|ts_arg_m|vwap", e):
        return "momentum"
    return "other"
