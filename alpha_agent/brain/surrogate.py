"""Small, explainable pre-simulation proxy for options candidates.

This module deliberately avoids heavyweight ML dependencies.  Models are
regularized linear/logistic regressions fitted with NumPy, validated on the most
recent chronological holdout, and ignored unless they beat an intercept-only
baseline.  An unvalidated model never affects a BRAIN simulation decision.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
import numpy as np

from alpha_agent.brain.evolution import options_mechanism_of
from alpha_agent.brain.hypotheses import map_expression_fields, research_context_key

MIN_TRAIN_ROWS = 48
MIN_CLASS_ROWS = 8
MIN_REGRESSION_ROWS = 40

_MECHANISMS = (
    "iv_skew_level",
    "iv_skew_dynamics",
    "iv_momentum",
    "iv_term",
    "pcr_dynamics",
    "option_breakeven",
    "vrp",
    "skew_call_innovation_residual",
    "skew_term_residual",
    "options_composite",
    "options_other",
)


def candidate_features(
    expression: str, settings: dict, field_metadata: list[dict]
) -> np.ndarray:
    mapping = map_expression_fields(expression, field_metadata)
    mechanism = options_mechanism_of(expression)
    op_count = len(re.findall(r"[a-zA-Z_]\w*\(", expression or ""))
    decay = float(settings.get("decay", 0) or 0)
    truncation = float(settings.get("truncation", 0.08) or 0.08)
    universe = str(settings.get("universe") or "")
    neutralization = str(settings.get("neutralization") or "")
    values = [
        float(mapping["coverage"]),
        float(mapping["mapped_ratio"]),
        min(op_count / 20.0, 2.0),
        min(len(mapping["field_ids"]) / 6.0, 2.0),
        float("trade_when(" in (expression or "")),
        float("rank(" in (expression or "")),
        float("group_neutralize(" in (expression or "")),
        float("ts_regression(" in (expression or "")),
        min(decay / 40.0, 1.5),
        min(truncation / 0.10, 2.0),
        float(settings.get("delay", 1) == 0),
        float(universe == "TOP3000"),
        float(universe == "TOP1000"),
        float(universe == "TOP500"),
        float(neutralization == "SUBINDUSTRY"),
        float(neutralization == "INDUSTRY"),
        float(neutralization == "MARKET"),
    ]
    values.extend(float(mechanism == item) for item in _MECHANISMS)
    return np.asarray(values, dtype=np.float64)


@dataclass
class _LinearModel:
    mean: np.ndarray
    scale: np.ndarray
    weights: np.ndarray
    logistic: bool

    def predict(self, x: np.ndarray) -> float:
        z = np.concatenate(([1.0], (x - self.mean) / self.scale)) @ self.weights
        if self.logistic:
            return float(1.0 / (1.0 + math.exp(-float(np.clip(z, -30, 30)))))
        return float(z)


@dataclass
class OptionsSurrogate:
    active: bool
    reason: str
    sample_n: int
    models: dict[str, _LinearModel] = field(default_factory=dict)
    diagnostics: dict[str, dict[str, float | int | str]] = field(default_factory=dict)
    support_min: np.ndarray | None = None
    support_max: np.ndarray | None = None
    support_contexts: frozenset[str] = frozenset()
    drift_score: float = 0.0

    def supports(
        self, expression: str, settings: dict, field_metadata: list[dict]
    ) -> bool:
        """Return whether a candidate is inside observed training support."""
        if self.support_min is None or self.support_max is None:
            return False
        context = research_context_key(
            options_mechanism_of(expression), expression, field_metadata, settings
        )
        if self.support_contexts and context not in self.support_contexts:
            return False
        x = candidate_features(expression, settings, field_metadata)
        span = np.maximum(self.support_max - self.support_min, 1e-6)
        margin = np.maximum(span * 0.10, 0.05)
        return bool(
            np.all(x >= self.support_min - margin)
            and np.all(x <= self.support_max + margin)
        )

    def predict(
        self, expression: str, settings: dict, field_metadata: list[dict]
    ) -> dict[str, float]:
        if not self.active:
            return {}
        if not self.supports(expression, settings, field_metadata):
            return {}
        x = candidate_features(expression, settings, field_metadata)
        out = {name: model.predict(x) for name, model in self.models.items()}
        for name in ("self_corr", "marginal_proxy"):
            if name in out:
                out[name] = max(0.0, min(1.0, out[name]))
        return out


def _fit_logistic(x: np.ndarray, y: np.ndarray) -> _LinearModel:
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale < 1e-8] = 1.0
    design = np.column_stack((np.ones(len(x)), (x - mean) / scale))
    weights = np.zeros(design.shape[1], dtype=np.float64)
    for _ in range(400):
        logits = np.clip(design @ weights, -30, 30)
        pred = 1.0 / (1.0 + np.exp(-logits))
        grad = design.T @ (pred - y) / len(y)
        grad[1:] += 0.04 * weights[1:]
        weights -= 0.08 * grad
    return _LinearModel(mean, scale, weights, logistic=True)


def _fit_ridge(x: np.ndarray, y: np.ndarray) -> _LinearModel:
    mean = x.mean(axis=0)
    scale = x.std(axis=0)
    scale[scale < 1e-8] = 1.0
    design = np.column_stack((np.ones(len(x)), (x - mean) / scale))
    penalty = np.eye(design.shape[1]) * 0.30
    penalty[0, 0] = 0.0
    weights = np.linalg.pinv(design.T @ design + penalty) @ design.T @ y
    return _LinearModel(mean, scale, weights, logistic=False)


def _chronological_split(n: int) -> int:
    holdout = max(12, int(round(n * 0.20)))
    return max(1, n - min(holdout, n // 3))


def _fit_binary_target(
    x: np.ndarray, y: np.ndarray, name: str, groups: np.ndarray | None = None
) -> tuple[_LinearModel | None, dict[str, float | int | str]]:
    if len(y) < MIN_TRAIN_ROWS or min(int(y.sum()), int(len(y) - y.sum())) < MIN_CLASS_ROWS:
        return None, {"status": "insufficient", "n": len(y), "positive_n": int(y.sum())}
    split = _chronological_split(len(y))
    train_x, test_x = x[:split], x[split:]
    train_y, test_y = y[:split], y[split:]
    if groups is not None:
        train_groups = set(groups[:split].tolist())
        test_groups = set(groups[split:].tolist())
        if not train_groups.intersection(test_groups):
            return None, {
                "status": "rejected_unseen_context_holdout",
                "n": len(y),
                "holdout_n": len(test_y),
                "train_groups": len(train_groups),
                "holdout_groups": len(test_groups),
            }
    if min(int(train_y.sum()), int(len(train_y) - train_y.sum())) < MIN_CLASS_ROWS:
        return None, {"status": "insufficient_train_classes", "n": len(y)}
    model = _fit_logistic(train_x, train_y)
    pred = np.asarray([model.predict(row) for row in test_x])
    base = float(train_y.mean())
    brier = float(np.mean((pred - test_y) ** 2))
    baseline = float(np.mean((base - test_y) ** 2))
    diagnostics: dict[str, float | int | str] = {
        "status": "validated" if brier + 0.005 < baseline else "rejected_holdout",
        "n": len(y),
        "holdout_n": len(test_y),
        "brier": round(brier, 5),
        "baseline_brier": round(baseline, 5),
        "train_groups": len(set(groups[:split].tolist())) if groups is not None else 0,
        "holdout_groups": len(set(groups[split:].tolist())) if groups is not None else 0,
        "group_overlap": len(set(groups[:split].tolist()).intersection(set(groups[split:].tolist()))) if groups is not None else 0,
    }
    if diagnostics["status"] != "validated":
        return None, diagnostics
    return _fit_logistic(x, y), diagnostics


def _fit_regression_target(
    x: np.ndarray, y: np.ndarray, groups: np.ndarray | None = None
) -> tuple[_LinearModel | None, dict[str, float | int | str]]:
    if len(y) < MIN_REGRESSION_ROWS or float(np.std(y)) < 1e-6:
        return None, {"status": "insufficient", "n": len(y)}
    split = _chronological_split(len(y))
    if groups is not None:
        train_groups = set(groups[:split].tolist())
        test_groups = set(groups[split:].tolist())
        if not train_groups.intersection(test_groups):
            return None, {
                "status": "rejected_unseen_context_holdout",
                "n": len(y),
                "holdout_n": len(y) - split,
                "train_groups": len(train_groups),
                "holdout_groups": len(test_groups),
            }
    model = _fit_ridge(x[:split], y[:split])
    pred = np.asarray([model.predict(row) for row in x[split:]])
    baseline_value = float(y[:split].mean())
    mse = float(np.mean((pred - y[split:]) ** 2))
    baseline = float(np.mean((baseline_value - y[split:]) ** 2))
    diagnostics: dict[str, float | int | str] = {
        "status": "validated" if mse < baseline * 0.95 else "rejected_holdout",
        "n": len(y),
        "holdout_n": len(y) - split,
        "mse": round(mse, 5),
        "baseline_mse": round(baseline, 5),
        "train_groups": len(set(groups[:split].tolist())) if groups is not None else 0,
        "holdout_groups": len(set(groups[split:].tolist())) if groups is not None else 0,
        "group_overlap": len(set(groups[:split].tolist()).intersection(set(groups[split:].tolist()))) if groups is not None else 0,
    }
    if diagnostics["status"] != "validated":
        return None, diagnostics
    return _fit_ridge(x, y), diagnostics


def _holdout_drift(x: np.ndarray) -> float:
    """Measure chronological feature drift in standardized training units."""
    split = _chronological_split(len(x))
    if split <= 0 or split >= len(x):
        return 0.0
    train = x[:split]
    holdout = x[split:]
    scale = np.maximum(train.std(axis=0), 1e-6)
    return float(np.mean(np.abs(holdout.mean(axis=0) - train.mean(axis=0)) / scale))


def fit_options_surrogate(rows: list[dict], field_metadata: list[dict]) -> OptionsSurrogate:
    usable = [row for row in rows if row.get("expression") and row.get("settings")]
    usable.sort(key=lambda row: str(row.get("created_at") or ""))
    if len(usable) < MIN_TRAIN_ROWS:
        return OptionsSurrogate(False, f"sample {len(usable)} < {MIN_TRAIN_ROWS}", len(usable))

    x_all = np.vstack([
        candidate_features(row["expression"], row.get("settings") or {}, field_metadata)
        for row in usable
    ])
    contexts = np.asarray([
        research_context_key(
            options_mechanism_of(row["expression"]),
            row["expression"],
            field_metadata,
            row.get("settings") or {},
        )
        for row in usable
    ], dtype=object)
    drift_score = _holdout_drift(x_all)
    models: dict[str, _LinearModel] = {}
    diagnostics: dict[str, dict[str, float | int | str]] = {}

    binary_targets = {
        "good": np.asarray([
            str(row.get("grade") or "").upper() in {"GOOD", "EXCELLENT", "SPECTACULAR"}
            for row in usable
        ], dtype=np.float64),
        "concentration": np.asarray([
            "CONCENTRATED_WEIGHT" in str(row.get("fail_checks") or "")
            for row in usable
        ], dtype=np.float64),
        "low_sub_universe": np.asarray([
            "LOW_SUB_UNIVERSE_SHARPE" in str(row.get("fail_checks") or "")
            for row in usable
        ], dtype=np.float64),
    }
    for name, target in binary_targets.items():
        model, diag = _fit_binary_target(x_all, target, name, contexts)
        diagnostics[name] = diag
        if model is not None:
            models[name] = model

    for name, source, transform in (
        ("self_corr", "self_correlation", lambda value: float(value)),
        (
            "marginal_proxy",
            "self_correlation_adj",
            # This is a bounded diversification proxy, not a portfolio-level
            # incremental-return regression.  Keep the name explicit wherever
            # it is persisted or shown to users.
            lambda value: 1.0 - float(value) ** 2,
        ),
    ):
        indices = [i for i, row in enumerate(usable) if row.get(source) is not None]
        target = np.asarray([transform(usable[i][source]) for i in indices])
        model, diag = _fit_regression_target(x_all[indices], target, contexts[indices])
        diagnostics[name] = diag
        if model is not None:
            models[name] = model

    active = "good" in models and len(models) >= 2 and drift_score <= 3.0
    reason = (
        f"validated targets: {','.join(sorted(models))}"
        if active
        else "holdout validation did not support a quality-plus-risk proxy"
    )
    if drift_score > 3.0:
        reason = f"chronological feature drift {drift_score:.2f} exceeds guard"
    return OptionsSurrogate(
        active,
        reason,
        len(usable),
        models,
        diagnostics,
        support_min=x_all.min(axis=0),
        support_max=x_all.max(axis=0),
        support_contexts=frozenset(str(value) for value in contexts),
        drift_score=round(drift_score, 4),
    )


def proxy_composite(prediction: dict[str, float]) -> float | None:
    if not prediction or "good" not in prediction:
        return None
    parts = [(0.40, prediction["good"])]
    if "concentration" in prediction:
        parts.append((0.20, 1.0 - prediction["concentration"]))
    if "low_sub_universe" in prediction:
        parts.append((0.15, 1.0 - prediction["low_sub_universe"]))
    if "self_corr" in prediction:
        parts.append((0.10, 1.0 - prediction["self_corr"]))
    if "marginal_proxy" in prediction:
        parts.append((0.15, prediction["marginal_proxy"]))
    total_weight = sum(weight for weight, _ in parts)
    return 10.0 * sum(weight * value for weight, value in parts) / total_weight
