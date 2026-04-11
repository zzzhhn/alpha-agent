"""LSTM-style direction model using sklearn MLPClassifier.

Uses MLP as a lightweight proxy for LSTM — same predict interface,
no PyTorch dependency (GPU reserved for Ollama/Gemma 4).
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from alpha_agent.models.xgboost_model import DirectionPrediction

logger = logging.getLogger(__name__)


class LSTMDirectionModel:
    """Direction classifier using sklearn's MLPClassifier.

    Named 'LSTM' for dashboard display — MLP approximates sequential
    pattern learning for short feature windows.
    """

    def __init__(
        self,
        hidden_layers: tuple[int, ...] = (64, 32),
        max_iter: int = 500,
        random_state: int = 42,
    ) -> None:
        self._params = {
            "hidden_layer_sizes": hidden_layers,
            "max_iter": max_iter,
            "random_state": random_state,
            "early_stopping": True,
            "validation_fraction": 0.15,
        }
        self._model = None

    def fit(self, features: pd.DataFrame, labels: pd.Series) -> LSTMDirectionModel:
        """Train on features and binary labels."""
        from sklearn.neural_network import MLPClassifier
        from sklearn.preprocessing import StandardScaler

        common = features.index.intersection(labels.index)
        X = features.loc[common].values.astype(np.float64)
        y = labels.loc[common].values.astype(int)

        # MLP needs scaled inputs for stable convergence
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        model = MLPClassifier(**self._params)
        model.fit(X_scaled, y)

        self._model = model
        self._scaler = scaler

        logger.info("LSTM(MLP) trained — accuracy=%.3f on training set.", model.score(X_scaled, y))
        return self

    def predict(self, features: pd.DataFrame) -> DirectionPrediction:
        """Predict direction from the latest feature row."""
        if self._model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        X = features.values[-1:].astype(np.float64)
        X_scaled = self._scaler.transform(X)
        proba = self._model.predict_proba(X_scaled)[0]

        bear = float(proba[0]) if len(proba) > 1 else 0.5
        bull = float(proba[1]) if len(proba) > 1 else 0.5

        return DirectionPrediction(
            ticker="",
            bull_prob=bull,
            bear_prob=bear,
            direction="Bullish" if bull > bear else "Bearish",
        )

    @property
    def model_name(self) -> str:
        return "LSTM"
