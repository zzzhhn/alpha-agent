"""HMM-based market regime recognition using hmmlearn."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

RegimeName = Literal["Trend", "Oscillation", "Arbitrage", "Crash"]

REGIME_NAMES: list[RegimeName] = ["Trend", "Oscillation", "Arbitrage", "Crash"]

# Map regime names to Chinese labels
REGIME_LABELS_ZH: dict[RegimeName, str] = {
    "Trend": "趋势",
    "Oscillation": "震荡",
    "Arbitrage": "套利",
    "Crash": "暴跌",
}


@dataclass(frozen=True)
class MarketState:
    """Immutable result of HMM regime prediction."""

    current_regime: RegimeName
    regime_probabilities: dict[RegimeName, float]
    transition_probability: float  # probability of staying in current regime
    model_scores: dict[str, float]  # per-model raw scores


class HMMRegimeModel:
    """4-state Gaussian HMM for market regime detection.

    States are assigned semantic labels post-training based on
    the mean return and volatility of each hidden state.
    """

    def __init__(self, n_states: int = 4, n_iter: int = 100, random_state: int = 42) -> None:
        self._n_states = n_states
        self._n_iter = n_iter
        self._random_state = random_state
        self._model = None
        self._state_map: dict[int, RegimeName] = {}

    def fit(self, features: pd.DataFrame) -> HMMRegimeModel:
        """Train the HMM on feature matrix. Returns self (new state, not mutation)."""
        from hmmlearn.hmm import GaussianHMM

        X = features.values.astype(np.float64)

        model = GaussianHMM(
            n_components=self._n_states,
            covariance_type="full",
            n_iter=self._n_iter,
            random_state=self._random_state,
        )
        model.fit(X)

        self._model = model
        self._state_map = self._assign_labels(model, features.columns.tolist())
        return self

    def predict(self, features: pd.DataFrame) -> MarketState:
        """Predict current market regime from the latest feature row."""
        if self._model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        X = features.values.astype(np.float64)

        # State probabilities for the last observation
        log_prob, posteriors = self._model.score_samples(X)
        last_probs = posteriors[-1]

        # Most likely current state
        current_idx = int(np.argmax(last_probs))
        current_regime = self._state_map.get(current_idx, "Oscillation")

        # Transition probability (staying in current state)
        trans_prob = float(self._model.transmat_[current_idx, current_idx])

        regime_probs = {
            self._state_map.get(i, REGIME_NAMES[i % 4]): float(last_probs[i])
            for i in range(self._n_states)
        }

        # Model scores (scaled to 0-100)
        model_scores = {
            "HMM": float(last_probs[current_idx] * 100),
        }

        return MarketState(
            current_regime=current_regime,
            regime_probabilities=regime_probs,
            transition_probability=trans_prob,
            model_scores=model_scores,
        )

    def _assign_labels(self, model, feature_names: list[str]) -> dict[int, RegimeName]:
        """Assign semantic labels to hidden states based on learned means.

        Heuristic: sort states by (mean_return, mean_volatility) to map
        to Crash (low return, high vol), Trend (high return, low vol), etc.
        """
        means = model.means_  # shape (n_states, n_features)

        # Find return and volatility feature indices
        ret_idx = feature_names.index("log_return") if "log_return" in feature_names else 0
        vol_idx = feature_names.index("volatility_20d") if "volatility_20d" in feature_names else 1

        state_info = []
        for i in range(self._n_states):
            state_info.append((i, means[i, ret_idx], means[i, vol_idx]))

        # Sort by return ascending
        state_info.sort(key=lambda x: x[1])

        # Lowest return + high vol → Crash
        # Low return + low vol → Oscillation
        # High return + low vol → Trend
        # Highest return → Arbitrage (momentum capture)
        mapping: dict[int, RegimeName] = {}
        mapping[state_info[0][0]] = "Crash"
        mapping[state_info[1][0]] = "Oscillation"
        mapping[state_info[2][0]] = "Trend"
        mapping[state_info[3][0]] = "Arbitrage"

        logger.info("HMM state mapping: %s", mapping)
        return mapping
