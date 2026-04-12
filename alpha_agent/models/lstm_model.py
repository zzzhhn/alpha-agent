"""LSTM direction model using PyTorch (CPU only).

Falls back to sklearn MLPClassifier if torch is not installed.
GPU is reserved for Ollama/Gemma 4, so LSTM runs on CPU.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from alpha_agent.models.xgboost_model import DirectionPrediction

logger = logging.getLogger(__name__)

# LSTM hyperparameters
_HIDDEN_SIZE = 64
_NUM_LAYERS = 2
_SEQUENCE_LENGTH = 20  # lookback window for LSTM
_EPOCHS = 50
_BATCH_SIZE = 32
_LR = 0.001


class LSTMDirectionModel:
    """Direction classifier using PyTorch LSTM (with MLP fallback).

    Converts tabular features into sequences of length _SEQUENCE_LENGTH
    using a sliding window, then feeds through a 2-layer LSTM.

    Runs on CPU to avoid GPU conflict with Ollama.
    """

    def __init__(
        self,
        hidden_size: int = _HIDDEN_SIZE,
        num_layers: int = _NUM_LAYERS,
        seq_length: int = _SEQUENCE_LENGTH,
        random_state: int = 42,
    ) -> None:
        self._hidden_size = hidden_size
        self._num_layers = num_layers
        self._seq_length = seq_length
        self._random_state = random_state
        self._model = None
        self._scaler = None
        self._using_pytorch = False
        self._n_features = 0

    def fit(self, features: pd.DataFrame, labels: pd.Series) -> LSTMDirectionModel:
        """Train on features and binary labels."""
        common = features.index.intersection(labels.index)
        X = features.loc[common].values.astype(np.float64)
        y = labels.loc[common].values.astype(int)
        self._n_features = X.shape[1]

        # Scale features
        from sklearn.preprocessing import StandardScaler
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        self._scaler = scaler

        # Try PyTorch LSTM first
        model = self._try_pytorch_lstm(X_scaled, y)
        if model is not None:
            self._model = model
            self._using_pytorch = True
            logger.info(
                "LSTM (PyTorch) trained — hidden=%d, layers=%d, seq=%d",
                self._hidden_size,
                self._num_layers,
                self._seq_length,
            )
            return self

        # Fallback to sklearn MLP
        model = self._fit_sklearn_mlp(X_scaled, y)
        self._model = model
        self._using_pytorch = False
        logger.info("LSTM (sklearn MLP fallback) trained.")
        return self

    def predict(self, features: pd.DataFrame) -> DirectionPrediction:
        """Predict direction from the latest feature rows."""
        if self._model is None or self._scaler is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        X = features.values.astype(np.float64)
        X_scaled = self._scaler.transform(X)

        if self._using_pytorch:
            bull = self._predict_pytorch(X_scaled)
        else:
            proba = self._model.predict_proba(X_scaled[-1:])
            bull = float(proba[0][1]) if proba.shape[1] > 1 else 0.5

        bear = 1.0 - bull
        return DirectionPrediction(
            ticker="",
            bull_prob=bull,
            bear_prob=bear,
            direction="Bullish" if bull > bear else "Bearish",
        )

    def _try_pytorch_lstm(
        self, X: np.ndarray, y: np.ndarray
    ) -> object | None:
        """Try training with PyTorch LSTM. Returns None if torch unavailable."""
        try:
            import torch
            import torch.nn as nn
        except ImportError:
            logger.debug("torch not installed, using sklearn MLP fallback.")
            return None

        # Create sequences using sliding window
        sequences, seq_labels = _create_sequences(X, y, self._seq_length)
        if len(sequences) < _BATCH_SIZE:
            logger.warning("Not enough data for LSTM sequences, falling back.")
            return None

        # Build model
        model = _LSTMNet(
            input_size=self._n_features,
            hidden_size=self._hidden_size,
            num_layers=self._num_layers,
        )

        # Train
        torch.manual_seed(self._random_state)
        optimizer = torch.optim.Adam(model.parameters(), lr=_LR)
        criterion = nn.BCELoss()

        X_tensor = torch.FloatTensor(sequences)
        y_tensor = torch.FloatTensor(seq_labels)

        model.train()
        for epoch in range(_EPOCHS):
            # Mini-batch training
            indices = torch.randperm(len(X_tensor))
            total_loss = 0.0
            n_batches = 0

            for i in range(0, len(indices), _BATCH_SIZE):
                batch_idx = indices[i : i + _BATCH_SIZE]
                batch_X = X_tensor[batch_idx]
                batch_y = y_tensor[batch_idx]

                optimizer.zero_grad()
                output = model(batch_X).squeeze(-1)
                loss = criterion(output, batch_y)
                loss.backward()
                optimizer.step()

                total_loss += loss.item()
                n_batches += 1

            if (epoch + 1) % 10 == 0:
                avg_loss = total_loss / max(n_batches, 1)
                logger.debug("LSTM epoch %d/%d, loss=%.4f", epoch + 1, _EPOCHS, avg_loss)

        model.eval()
        return model

    def _predict_pytorch(self, X_scaled: np.ndarray) -> float:
        """Predict using PyTorch LSTM model."""
        import torch

        # Use the last seq_length rows as the sequence
        if len(X_scaled) >= self._seq_length:
            seq = X_scaled[-self._seq_length:]
        else:
            # Pad with zeros if not enough data
            pad = np.zeros((self._seq_length - len(X_scaled), X_scaled.shape[1]))
            seq = np.vstack([pad, X_scaled])

        X_tensor = torch.FloatTensor(seq).unsqueeze(0)  # (1, seq_len, features)

        with torch.no_grad():
            output = self._model(X_tensor)

        return float(output.squeeze().item())

    def _fit_sklearn_mlp(self, X: np.ndarray, y: np.ndarray) -> object:
        """Fallback: train with sklearn MLPClassifier."""
        from sklearn.neural_network import MLPClassifier

        model = MLPClassifier(
            hidden_layer_sizes=(64, 32),
            max_iter=500,
            random_state=self._random_state,
            early_stopping=True,
            validation_fraction=0.15,
        )
        model.fit(X, y)
        return model

    @property
    def model_name(self) -> str:
        suffix = "PyTorch" if self._using_pytorch else "sklearn MLP"
        return f"LSTM ({suffix})"


def _create_sequences(
    X: np.ndarray, y: np.ndarray, seq_length: int
) -> tuple[np.ndarray, np.ndarray]:
    """Create sliding window sequences from feature matrix.

    Returns (sequences, labels) where sequences has shape
    (n_samples - seq_length, seq_length, n_features).
    """
    sequences: list[np.ndarray] = []
    labels: list[float] = []

    for i in range(seq_length, len(X)):
        sequences.append(X[i - seq_length : i])
        labels.append(float(y[i]))

    return np.array(sequences), np.array(labels)


# PyTorch LSTM network definition (guarded by import)
try:
    import torch
    import torch.nn as nn

    class _LSTMNet(nn.Module):
        """2-layer LSTM → Linear → Sigmoid for binary classification."""

        def __init__(
            self,
            input_size: int,
            hidden_size: int = _HIDDEN_SIZE,
            num_layers: int = _NUM_LAYERS,
        ) -> None:
            super().__init__()
            self.lstm = nn.LSTM(
                input_size=input_size,
                hidden_size=hidden_size,
                num_layers=num_layers,
                batch_first=True,
                dropout=0.2 if num_layers > 1 else 0.0,
            )
            self.fc = nn.Linear(hidden_size, 1)
            self.sigmoid = nn.Sigmoid()

        def forward(self, x: torch.Tensor) -> torch.Tensor:
            lstm_out, _ = self.lstm(x)
            last_hidden = lstm_out[:, -1, :]  # Take last timestep
            return self.sigmoid(self.fc(last_hidden))

except ImportError:
    pass  # _LSTMNet not available without torch
