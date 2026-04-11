"""Model fusion — weighted voting across sub-models."""

from __future__ import annotations

from dataclasses import dataclass

from alpha_agent.models.xgboost_model import DirectionPrediction


@dataclass(frozen=True)
class FusionResult:
    """Immutable fused prediction across all sub-models."""

    direction: str  # "Bullish" or "Bearish"
    confidence: float  # 0.0 - 1.0
    bull_prob: float
    bear_prob: float
    model_weights: dict[str, float]
    per_model: dict[str, DirectionPrediction]


# Default weights — HMM informs regime, XGBoost/LSTM predict direction
DEFAULT_WEIGHTS: dict[str, float] = {
    "XGBoost": 0.45,
    "LSTM": 0.35,
    "HMM": 0.20,
}


def fuse_predictions(
    predictions: dict[str, DirectionPrediction],
    hmm_bull_bias: float = 0.5,
    weights: dict[str, float] | None = None,
) -> FusionResult:
    """Weighted average fusion of sub-model predictions.

    Parameters
    ----------
    predictions : dict
        Model name → DirectionPrediction for that model.
    hmm_bull_bias : float
        HMM regime-derived bull probability (0-1).
        Arbitrage/Trend → higher, Crash → lower.
    weights : dict, optional
        Custom weights; defaults to DEFAULT_WEIGHTS.
    """
    w = weights or DEFAULT_WEIGHTS

    # Build probability map including HMM's regime-derived signal
    prob_map: dict[str, float] = {}
    for name, pred in predictions.items():
        prob_map[name] = pred.bull_prob

    prob_map["HMM"] = hmm_bull_bias

    # Weighted average of bull probabilities
    total_weight = sum(w.get(name, 0.0) for name in prob_map)
    if total_weight == 0:
        total_weight = 1.0

    bull_prob = sum(
        prob_map[name] * w.get(name, 0.0) for name in prob_map
    ) / total_weight

    bear_prob = 1.0 - bull_prob
    direction = "Bullish" if bull_prob > 0.5 else "Bearish"
    confidence = abs(bull_prob - 0.5) * 2.0  # scale to 0-1

    return FusionResult(
        direction=direction,
        confidence=confidence,
        bull_prob=bull_prob,
        bear_prob=bear_prob,
        model_weights=w,
        per_model=predictions,
    )
