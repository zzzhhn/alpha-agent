"""Local BRAIN diversity evidence on exact cumulative-PnL return intervals."""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from alpha_agent.brain.pnl import ReturnIntervals
from alpha_agent.evolution.correlation_gate import _pairwise_pearson

METHOD = "brain_exact_return_intervals_v1"
_MAX_NEIGHBOURS = 8
_MIN_CONTRIBUTION_OBS = 60


@dataclass(frozen=True)
class AdjustedCorrelation:
    value: float | None
    against: str | None
    n: int


@dataclass(frozen=True)
class IncrementalContribution:
    value: float | None
    references: tuple[str, ...]
    n: int


@dataclass(frozen=True)
class DiversityEvidence:
    adjusted: AdjustedCorrelation
    marginal: IncrementalContribution

    def decision_evidence(self) -> dict:
        return {
            "adjusted_correlation": asdict(self.adjusted),
            "incremental_contribution": asdict(self.marginal),
        }


def _pairwise_scores(
    candidate: ReturnIntervals, book: dict[str, ReturnIntervals],
) -> tuple[AdjustedCorrelation, list[str]]:
    ranked: list[tuple[float, str, int]] = []
    most_overlap = 0
    for name, returns in book.items():
        common = sorted(candidate.keys() & returns.keys())
        n = len(common)
        most_overlap = max(most_overlap, n)
        if n < 3:
            continue
        cand = np.array([candidate[interval] for interval in common])
        ref = np.array([returns[interval] for interval in common])
        # Both arrays are already paired on the same interval keys.
        corr = _pairwise_pearson(cand, ref)
        if corr is not None and np.isfinite(corr):
            ranked.append((min(1.0, abs(corr)), name, n))

    if not ranked:
        return AdjustedCorrelation(None, None, most_overlap), []
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    value, name, n = ranked[0]
    return AdjustedCorrelation(value, name, n), [name for _, name, _ in ranked]


def adjusted_correlation(
    candidate: ReturnIntervals, book: dict[str, ReturnIntervals],
) -> AdjustedCorrelation:
    """Largest absolute correlation and overlap count, or the largest attempted overlap."""
    return _pairwise_scores(candidate, book)[0]


def compare_returns(
    candidate: ReturnIntervals, book: dict[str, ReturnIntervals],
) -> DiversityEvidence:
    """Score pairs on exact shared intervals and fit marginal variance jointly."""
    adjusted, ranked = _pairwise_scores(candidate, book)
    references = tuple(ranked[:_MAX_NEIGHBOURS])
    if not references:
        return DiversityEvidence(adjusted, IncrementalContribution(None, (), 0))

    common = sorted(candidate.keys() & book[references[0]].keys())
    for name in references[1:]:
        common = [interval for interval in common if interval in book[name]]
    n = len(common)
    value = None
    # At 60 observations, eight regressors plus the intercept are overdetermined.
    if n >= _MIN_CONTRIBUTION_OBS:
        y = np.array([candidate[interval] for interval in common])
        columns = [[book[name][interval] for interval in common] for name in references]
        design = np.column_stack([np.ones(n), *columns])
        ss_total = float(((y - y.mean()) ** 2).sum())
        if ss_total < 1e-18:
            value = 0.0
        elif np.isfinite(ss_total):
            try:
                beta, *_ = np.linalg.lstsq(design, y, rcond=None)
                fraction = float(((y - design @ beta) ** 2).sum() / ss_total)
                if np.isfinite(fraction):
                    value = max(0.0, min(1.0, fraction))
            except np.linalg.LinAlgError:
                pass
    return DiversityEvidence(adjusted, IncrementalContribution(value, references, n))
