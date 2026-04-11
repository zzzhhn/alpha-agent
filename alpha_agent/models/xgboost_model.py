"""XGBoost-style direction classifier using sklearn GradientBoosting."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DirectionPrediction:
    """Immutable per-ticker direction prediction."""

    ticker: str
    bull_prob: float
    bear_prob: float
    direction: str  # "Bullish" or "Bearish"


class XGBoostDirectionModel:
    """Direction classifier using sklearn's GradientBoostingClassifier.

    Named 'XGBoost' for dashboard display — uses sklearn's gradient boosting
    which implements the same GBDT algorithm without the xgboost C library.
    """

    def __init__(
        self,
        n_estimators: int = 100,
        max_depth: int = 4,
        learning_rate: float = 0.1,
        random_state: int = 42,
    ) -> None:
        self._params = {
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "learning_rate": learning_rate,
            "random_state": random_state,
        }
        self._model = None

    def fit(self, features: pd.DataFrame, labels: pd.Series) -> XGBoostDirectionModel:
        """Train on features and binary direction labels (1=up, 0=down)."""
        from sklearn.ensemble import GradientBoostingClassifier

        # Align indices
        common = features.index.intersection(labels.index)
        X = features.loc[common].values.astype(np.float64)
        y = labels.loc[common].values.astype(int)

        model = GradientBoostingClassifier(**self._params)
        model.fit(X, y)
        self._model = model

        logger.info("XGBoost trained — accuracy=%.3f on training set.", model.score(X, y))
        return self

    def predict(self, features: pd.DataFrame) -> DirectionPrediction:
        """Predict direction from the latest feature row."""
        if self._model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        X = features.values[-1:].astype(np.float64)
        proba = self._model.predict_proba(X)[0]

        # proba[0] = P(down), proba[1] = P(up)
        bear = float(proba[0]) if len(proba) > 1 else 0.5
        bull = float(proba[1]) if len(proba) > 1 else 0.5

        return DirectionPrediction(
            ticker="",  # caller fills in
            bull_prob=bull,
            bear_prob=bear,
            direction="Bullish" if bull > bear else "Bearish",
        )

    @property
    def model_name(self) -> str:
        return "XGBoost"
