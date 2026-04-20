"""Shared Pydantic types for the AlphaCore system.

FactorSpec is the grammar-constrained output target of the T1 HypothesisTranslator
(see REFACTOR_PLAN.md section 3.1). Grammar enforcement at this boundary is the
difference between "LLM-generated maybe-executable code" and "LLM-generated
guaranteed-parseable FactorSpec".

B+ whitelist (2026-04-18): operator/operand membership is validated against
the generated `brain_registry` frozensets rather than a hand-maintained
`Literal[...]`. The generator script `scripts/build_brain_registry.py` is the
single point of change when the source-of-truth Bitable is updated.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from alpha_agent.core.brain_registry import OPERAND_NAMES, OPERATOR_NAMES


class FactorSpec(BaseModel):
    """A single factor specification, the output of HypothesisTranslator.

    Downstream pipeline (W2):
        Pydantic validate -> AST parse -> 10-day smoke test -> registry

    `operators_used` is the LLM's declaration of which operators its expression
    invokes. The AST validator (alpha_agent.core.factor_ast) cross-checks this
    claim against what the expression actually uses; drift in either direction
    raises FactorSpecValidationError. This field is retained (rather than
    recomputed) so that the LLM commits to an explicit operator budget at
    generation time.
    """

    name: str = Field(max_length=40, description="Short identifier, snake_case")
    hypothesis: str = Field(max_length=200, description="Human hypothesis statement")
    expression: str = Field(description="Factor expression in BRAIN-style grammar")
    operators_used: list[str] = Field(
        description="Operators invoked by expression (validated against OPERATOR_NAMES)"
    )
    lookback: int = Field(ge=5, le=252)
    universe: Literal["CSI300", "CSI500", "SP500", "custom"]
    justification: str = Field(max_length=400)

    @field_validator("operators_used")
    @classmethod
    def _operators_in_whitelist(cls, value: list[str]) -> list[str]:
        unknown = sorted(set(value) - OPERATOR_NAMES)
        if unknown:
            raise ValueError(
                f"unknown operators {unknown}; see brain_registry.OPERATOR_NAMES "
                f"({len(OPERATOR_NAMES)} total)"
            )
        return value


class RouterHealth(BaseModel):
    """One row of /healthz/routers response.

    Surfaces silent ImportError failures caught by api/index.py try/except
    per feedback_silent_trycatch_antipattern.md.
    """

    name: str
    loaded: bool
    error: str | None = None


__all__ = ["FactorSpec", "RouterHealth", "OPERAND_NAMES", "OPERATOR_NAMES"]
