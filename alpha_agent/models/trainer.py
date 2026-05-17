"""Model trainer — fits all ML models and persists via joblib."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import joblib
import pandas as pd

from alpha_agent.config import get_settings
from alpha_agent.data.cache import ParquetCache
from alpha_agent.data.us_provider import YFinanceProvider
from alpha_agent.models.features import compute_features, compute_forward_returns
from alpha_agent.models.hmm import HMMRegimeModel
from alpha_agent.models.lstm_model import LSTMDirectionModel
from alpha_agent.models.xgboost_model import XGBoostDirectionModel

logger = logging.getLogger(__name__)

_MODEL_STALENESS_HOURS = 24


@dataclass(frozen=True)
class TrainedModels:
    """Immutable container of fitted model instances."""

    hmm: HMMRegimeModel
    xgboost: XGBoostDirectionModel
    lstm: LSTMDirectionModel


def get_or_train_models(force: bool = False) -> TrainedModels:
    """Load persisted models or train fresh ones.

    Parameters
    ----------
    force : bool
        If True, retrain regardless of cache freshness.
    """
    settings = get_settings()
    model_dir = Path(settings.model_dir)
    model_dir.mkdir(parents=True, exist_ok=True)

    hmm_path = model_dir / "hmm.joblib"
    xgb_path = model_dir / "xgboost.joblib"
    lstm_path = model_dir / "lstm.joblib"

    if not force and all(
        _is_fresh(p) for p in [hmm_path, xgb_path, lstm_path]
    ):
        logger.info("Loading cached models from %s", model_dir)
        return TrainedModels(
            hmm=joblib.load(hmm_path),
            xgboost=joblib.load(xgb_path),
            lstm=joblib.load(lstm_path),
        )

    logger.info("Training models — tickers=%s", settings.dashboard_tickers)

    # Fetch training data
    ohlcv = _fetch_training_data(settings.dashboard_tickers)

    # Use the first ticker as the primary training target
    primary = settings.dashboard_tickers[0]
    features = compute_features(ohlcv, primary)
    labels = compute_forward_returns(ohlcv, primary, horizon=5)

    # Train each model
    hmm = HMMRegimeModel().fit(features)
    xgb = XGBoostDirectionModel().fit(features, labels)
    lstm = LSTMDirectionModel().fit(features, labels)

    # Persist
    joblib.dump(hmm, hmm_path)
    joblib.dump(xgb, xgb_path)
    joblib.dump(lstm, lstm_path)
    logger.info("Models saved to %s", model_dir)

    return TrainedModels(hmm=hmm, xgboost=xgb, lstm=lstm)


def _fetch_training_data(tickers: list[str]) -> pd.DataFrame:
    """Fetch OHLCV data for training."""
    settings = get_settings()
    cache = ParquetCache(settings.data_cache_dir)
    provider = YFinanceProvider(cache=cache)
    return provider.fetch(
        stock_codes=tickers,
        start_date=settings.backtest_start,
        end_date=settings.backtest_end,
    )


def _is_fresh(path: Path) -> bool:
    """Check if a model file exists and is less than 24h old."""
    if not path.exists():
        return False
    import time
    age_hours = (time.time() - path.stat().st_mtime) / 3600
    return age_hours < _MODEL_STALENESS_HOURS
