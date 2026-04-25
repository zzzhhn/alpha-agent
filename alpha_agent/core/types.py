"""Shared Pydantic types for the AlphaCore system.

FactorSpec is the grammar-constrained output target of the T1 HypothesisTranslator
(see REFACTOR_PLAN.md section 3.1). Grammar enforcement at this boundary is the
difference between "LLM-generated maybe-executable code" and "LLM-generated
guaranteed-parseable FactorSpec".
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# Whitelist of operators allowed in a FactorSpec.expression.
# Gate against LLM hallucinated operators by checking FactorSpec.operators_used
# against this Literal at Pydantic validation time.
#
# Source of truth: alpha_agent/data/wq_catalog/operators_augmented.json. The
# subset below is the union of T1 operators (now implemented) plus the legacy
# short aliases (sub/mul/div/pow) kept for backward compat with existing
# FACTOR_EXAMPLES and saved Hypothesis history.
AllowedOperator = Literal[
    # arithmetic — canonical BRAIN names
    "abs", "add", "subtract", "multiply", "divide", "inverse", "log", "sqrt",
    "power", "sign", "signed_power", "max", "min", "reverse", "densify",
    # arithmetic — legacy aliases (do not remove without migrating saved factors)
    "sub", "mul", "div", "pow",
    # logical
    "if_else", "and_", "or_", "not_", "is_nan",
    "equal", "not_equal", "less", "greater", "less_equal", "greater_equal",
    # time-series
    "ts_delay", "ts_delta", "ts_mean", "ts_std", "ts_std_dev", "ts_sum",
    "ts_product", "ts_min", "ts_max", "ts_rank", "ts_zscore", "ts_arg_min",
    "ts_arg_max", "ts_corr", "ts_covariance", "ts_quantile", "ts_decay_linear",
    "ts_decay_exp", "ts_count_nans", "last_diff_value",
    # cross-section
    "rank", "zscore", "scale", "normalize", "quantile", "winsorize",
    # group (T2 — second arg must be a group operand like `sector` / `industry`)
    "group_rank", "group_zscore", "group_mean", "group_scale",
    "group_neutralize", "group_backfill",
]


class FactorSpec(BaseModel):
    """A single factor specification, the output of HypothesisTranslator.

    Downstream pipeline (W2):
        Pydantic validate -> AST parse -> 10-day smoke test -> registry
    """

    name: str = Field(max_length=40, description="Short identifier, snake_case")
    hypothesis: str = Field(max_length=200, description="Human hypothesis statement")
    expression: str = Field(description="WorldQuant-style expression using allowed ops")
    operators_used: list[AllowedOperator]
    lookback: int = Field(ge=5, le=252)
    universe: Literal["CSI300", "CSI500", "SP500", "custom"]
    justification: str = Field(max_length=400)


class RouterHealth(BaseModel):
    """One row of /healthz/routers response.

    Surfaces silent ImportError failures caught by api/index.py try/except
    per feedback_silent_trycatch_antipattern.md.
    """

    name: str
    loaded: bool
    error: str | None = None
