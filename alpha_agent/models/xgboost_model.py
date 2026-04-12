"""XGBoost direction classifier using the real xgboost library.

Falls back to sklearn GradientBoostingClassifier if xgboost is not installed.
"""

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
    """Direction classifier using XGBoost (with sklearn fallback).

    Tries real xgboost first for better performance and native feature
    importance. Falls back to sklearn GradientBoosting if unavailable.
    """

    def __init__(
        self,
        n_estimators: int = 200,
        max_depth: int = 5,
        learning_rate: float = 0.05,
        random_state: int = 42,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
    ) -> None:
        self._n_estimators = n_estimators
        self._max_depth = max_depth
        self._learning_rate = learning_rate
        self._random_state = random_state
        self._subsample = subsample
        self._colsample_bytree = colsample_bytree
        self._model = None
        self._using_real_xgb = False
        self._feature_names: list[str] = []

    def fit(self, features: pd.DataFrame, labels: pd.Series) -> XGBoostDirectionModel:
        """Train on features and binary direction labels (1=up, 0=down)."""
        common = features.index.intersection(labels.index)
        X = features.loc[common]
        y = labels.loc[common].values.astype(int)
        self._feature_names = list(X.columns)

        X_arr = X.values.astype(np.float64)

        # Try real xgboost first
        model = self._try_real_xgboost(X_arr, y)
        if model is not None:
            self._model = model
            self._using_real_xgb = True
            logger.info(
                "XGBoost (real) trained — %d estimators, depth=%d",
                self._n_estimators,
                self._max_depth,
            )
            return self

        # Fallback to sklearn
        model = self._fit_sklearn(X_arr, y)
        self._model = model
        self._using_real_xgb = False
        logger.info("XGBoost (sklearn fallback) trained.")
        return self

    def predict(self, features: pd.DataFrame) -> DirectionPrediction:
        """Predict direction from the latest feature row."""
        if self._model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        X = features.values[-1:].astype(np.float64)

        if self._using_real_xgb:
            import xgboost as xgb
            dmat = xgb.DMatrix(X, feature_names=self._feature_names)
            raw_pred = self._model.predict(dmat)[0]
            bull = float(raw_pred)
            bear = 1.0 - bull
        else:
            proba = self._model.predict_proba(X)[0]
            bear = float(proba[0]) if len(proba) > 1 else 0.5
            bull = float(proba[1]) if len(proba) > 1 else 0.5

        return DirectionPrediction(
            ticker="",
            bull_prob=bull,
            bear_prob=bear,
            direction="Bullish" if bull > bear else "Bearish",
        )

    def feature_importance(self) -> dict[str, float]:
        """Return feature importance scores (real xgb: gain, sklearn: impurity)."""
        if self._model is None:
            return {}

        if self._using_real_xgb:
            scores = self._model.get_score(importance_type="gain")
            return {k: float(v) for k, v in scores.items()}

        importances = self._model.feature_importances_
        return dict(zip(self._feature_names, importances.tolist()))

    def _try_real_xgboost(
        self, X: np.ndarray, y: np.ndarray
    ) -> object | None:
        """Try training with real xgboost. Returns None if not available."""
        try:
            import xgboost as xgb
        except ImportError:
            logger.debug("xgboost not installed, using sklearn fallback.")
            return None

        dtrain = xgb.DMatrix(X, label=y, feature_names=self._feature_names)
        params = {
            "objective": "binary:logistic",
            "eval_metric": "logloss",
            "max_depth": self._max_depth,
            "learning_rate": self._learning_rate,
            "subsample": self._subsample,
            "colsample_bytree": self._colsample_bytree,
            "seed": self._random_state,
            "tree_method": "hist",
            "verbosity": 0,
        }
        return xgb.train(params, dtrain, num_boost_round=self._n_estimators)

    def _fit_sklearn(self, X: np.ndarray, y: np.ndarray) -> object:
        """Fallback: train with sklearn GradientBoostingClassifier."""
        from sklearn.ensemble import GradientBoostingClassifier

        model = GradientBoostingClassifier(
            n_estimators=self._n_estimators,
            max_depth=self._max_depth,
            learning_rate=self._learning_rate,
            random_state=self._random_state,
            subsample=self._subsample,
        )
        model.fit(X, y)
        return model

    @property
    def model_name(self) -> str:
        suffix = "real" if self._using_real_xgb else "sklearn"
        return f"XGBoost ({suffix})"
