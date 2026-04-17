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
AllowedOperator = Literal[
    "ts_mean",
    "ts_rank",
    "ts_corr",
    "ts_std",
    "ts_zscore",
    "rank",
    "scale",
    "log",
    "sign",
    "winsorize",
    "div",
    "sub",
    "mul",
    "add",
    "pow",
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
