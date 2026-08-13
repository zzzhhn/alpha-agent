"""Evidence registry and context mapping for BRAIN options research.

The registry separates a paper's measured variable and target from the local
FASTEXPR approximation.  It is intentionally static and reviewable: an LLM may
help discover candidates, but it cannot silently invent a paper-to-field map.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class OptionHypothesis:
    id: str
    mechanism: str
    title: str
    source_url: str | None
    source_construction: str
    target: str
    required_semantics: tuple[str, ...]
    alternative_explanations: tuple[str, ...]
    falsification: str
    confidence: str


_REGISTRY = {
    "iv_skew_level": OptionHypothesis(
        id="cremers-weinbaum-call-put-iv-spread",
        mechanism="iv_skew_level",
        title="Deviations from Put-Call Parity and Stock Return Predictability",
        source_url="https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/abs/deviations-from-putcall-parity-and-stock-return-predictability/D9BA8F97580328AAFD7988B092FE5D50",
        source_construction="moneyness-matched call IV minus put IV",
        target="future cross-sectional stock returns",
        required_semantics=("call IV", "put IV", "matched tenor or moneyness"),
        alternative_explanations=("option liquidity", "short-sale constraints", "event risk"),
        falsification="fails after liquidity and coverage controls or remains concentrated",
        confidence="high",
    ),
    "iv_momentum": OptionHypothesis(
        id="an-ang-bali-cakici-iv-innovations",
        mechanism="iv_momentum",
        title="The Joint Cross Section of Stocks and Options",
        source_url="https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12181",
        source_construction="separate call-IV and put-IV innovations",
        target="future cross-sectional stock returns",
        required_semantics=("call IV change", "put IV change"),
        alternative_explanations=("earnings jumps", "volatility level", "liquidity"),
        falsification="direction is unstable across years or only works in event windows",
        confidence="high",
    ),
    "skew_call_innovation_residual": OptionHypothesis(
        id="an-iv-innovation-residual",
        mechanism="skew_call_innovation_residual",
        title="Call-IV innovation residual to the existing skew anchor",
        source_url="https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.12181",
        source_construction="call-IV innovation orthogonalized to call-put IV skew",
        target="future cross-sectional stock returns",
        required_semantics=("call IV change", "call IV", "put IV"),
        alternative_explanations=("anchor leakage", "earnings jumps", "coverage bias"),
        falsification="official or adjusted self-correlation remains at least 0.70",
        confidence="medium",
    ),
    "pcr_dynamics": OptionHypothesis(
        id="pan-poteshman-option-flow",
        mechanism="pcr_dynamics",
        title="The Information in Option Volume for Future Stock Prices",
        source_url="https://academic.oup.com/rfs/article-abstract/19/3/871/1646711",
        source_construction="buyer-initiated opening put-call volume ratio",
        target="future cross-sectional stock returns",
        required_semantics=("buyer initiated flow", "opening volume", "put-call ratio"),
        alternative_explanations=("ordinary open interest", "market making", "liquidity"),
        falsification="only open-interest proxies are available or the sign fails out of sample",
        confidence="low",
    ),
    "iv_term": OptionHypothesis(
        id="vasquez-equity-volatility-term-structure",
        mechanism="iv_term",
        title="Equity Volatility Term Structures and the Cross Section of Option Returns",
        source_url="https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/abs/equity-volatility-term-structures-and-the-cross-section-of-option-returns/F0A40E99FD2458367DD9A56A89783D38",
        source_construction="short-minus-long implied-volatility term slope",
        target="future option-strategy returns, not directly stock returns",
        required_semantics=("short tenor IV", "long tenor IV"),
        alternative_explanations=("volatility level", "earnings term structure"),
        falsification="stock-return alignment remains weak after faithful field mapping",
        confidence="low",
    ),
    "skew_term_residual": OptionHypothesis(
        id="term-slope-residual-exploration",
        mechanism="skew_term_residual",
        title="IV-term residual to the existing skew anchor",
        source_url=None,
        source_construction="IV term slope orthogonalized to call-put IV skew",
        target="exploratory future cross-sectional stock returns",
        required_semantics=("short tenor IV", "long tenor IV", "call IV", "put IV"),
        alternative_explanations=("outcome mismatch", "anchor leakage", "event risk"),
        falsification="weak Sharpe persists or correlation remains at least 0.70",
        confidence="low",
    ),
    "vrp": OptionHypothesis(
        id="bollerslev-tauchen-zhou-vrp",
        mechanism="vrp",
        title="Expected Stock Returns and Variance Risk Premia",
        source_url="https://academic.oup.com/rfs/article-abstract/22/11/4463/1565787",
        source_construction="model-free implied variance minus realized variance",
        target="aggregate market returns",
        required_semantics=("model-free implied variance", "realized variance"),
        alternative_explanations=("IV-HV proxy error", "market versus single-stock mismatch"),
        falsification="daily single-stock proxy fails across universes and years",
        confidence="low",
    ),
}

_EXPLORATORY = {
    "iv_skew_dynamics": ("call-put IV skew change", "future stock returns"),
    "option_breakeven": ("option breakeven relative to forward", "future stock returns"),
    "options_other": ("unregistered options construction", "unknown"),
}

_OPTION_FIELD_RE = re.compile(
    r"\b(?:implied_volatility\w*|historical_volatility\w*|pcr_oi_\w+|"
    r"call_breakeven_\w+|forward_price_\w+)\b"
)


def option_field_ids(expression: str) -> tuple[str, ...]:
    return tuple(sorted(set(_OPTION_FIELD_RE.findall(expression or ""))))


def hypothesis_for(mechanism: str) -> OptionHypothesis:
    if mechanism in _REGISTRY:
        return _REGISTRY[mechanism]
    construction, target = _EXPLORATORY.get(
        mechanism, ("unregistered options construction", "unknown")
    )
    return OptionHypothesis(
        id=f"exploratory-{mechanism}",
        mechanism=mechanism,
        title=f"Exploratory {mechanism}",
        source_url=None,
        source_construction=construction,
        target=target,
        required_semantics=(),
        alternative_explanations=("field semantics", "coverage", "data mining"),
        falsification="no stable performance or incremental contribution",
        confidence="low",
    )


def map_expression_fields(expression: str, field_metadata: list[dict]) -> dict[str, Any]:
    fields = option_field_ids(expression)
    metadata = {str(item.get("id")): item for item in field_metadata}
    matched = [metadata[field] for field in fields if field in metadata]
    datasets = sorted({str(item.get("dataset")) for item in matched if item.get("dataset")})
    coverage = min(
        (float(item.get("coverage") or 0.0) for item in matched),
        default=0.50 if not field_metadata else 0.0,
    )
    return {
        "field_ids": list(fields),
        "dataset_ids": datasets,
        "coverage": coverage,
        "mapped_ratio": len(matched) / len(fields) if fields else 0.0,
    }


def settings_context(settings: dict) -> str:
    decay = int(settings.get("decay", 0) or 0)
    decay_bucket = "0" if decay == 0 else "1-8" if decay <= 8 else "9-16" if decay <= 16 else "17+"
    truncation = float(settings.get("truncation", 0.08) or 0.08)
    trunc_bucket = "<=.04" if truncation <= 0.04 else ".04-.08" if truncation < 0.08 else ">=.08"
    return "|".join((
        str(settings.get("universe") or "unknown"),
        str(settings.get("neutralization") or "unknown"),
        f"d{settings.get('delay', 'unknown')}",
        f"decay:{decay_bucket}",
        f"trunc:{trunc_bucket}",
    ))


def research_context_key(
    mechanism: str, expression: str, field_metadata: list[dict], settings: dict
) -> str:
    mapping = map_expression_fields(expression, field_metadata)
    datasets = "+".join(mapping["dataset_ids"]) or "unmapped"
    return f"{mechanism}|{datasets}|{settings_context(settings)}"


def hypothesis_payload(
    mechanism: str, expression: str, field_metadata: list[dict], settings: dict
) -> dict[str, Any]:
    hypothesis = hypothesis_for(mechanism)
    return {
        "hypothesis": asdict(hypothesis),
        "field_mapping": map_expression_fields(expression, field_metadata),
        "context_key": research_context_key(
            mechanism, expression, field_metadata, settings
        ),
    }
