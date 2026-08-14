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
    r"\b(?:implied_volatility\w*|historical_volatility\w*|pcr_oi\w*|"
    r"pcr\w*|call_breakeven\w*|forward_price\w*)\b"
)
_IDENTIFIER_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*\b")
_TENOR_RE = re.compile(
    r"(?<![A-Za-z])(?P<n>\d{1,4})\s*(?P<u>d|day|days|w|wk|week|weeks|m|mo|month|months)?(?![A-Za-z])",
    re.IGNORECASE,
)


def option_field_ids(
    expression: str, field_metadata: list[dict] | None = None
) -> tuple[str, ...]:
    """Return option operands, including IDs discovered from the official catalog.

    The legacy regex remains a safe fallback.  When metadata is present, exact
    catalog IDs are preferred so fields whose naming does not follow our old
    hand-curated prefixes are still audited instead of silently treated as
    unmapped.
    """
    found = set(_OPTION_FIELD_RE.findall(expression or ""))
    if field_metadata:
        catalog_ids = {
            str(item.get("id")) for item in field_metadata if item.get("id")
        }
        found.update(
            token for token in _IDENTIFIER_RE.findall(expression or "")
            if token in catalog_ids
        )
    return tuple(sorted(found))


def classify_field_semantics(field: dict) -> dict[str, Any]:
    """Normalize auditable semantics from official field metadata.

    This intentionally does not infer buyer-initiated flow from an ordinary
    put-call open-interest ratio.  Descriptions are evidence, not decoration:
    an unclassified field remains ``unknown`` and is never upgraded by name
    alone to a stronger economic measure.
    """
    field_id = str(field.get("id") or "")
    name = str(field.get("name") or "")
    description = str(field.get("description") or "")
    text = " ".join((field_id, name, description)).lower()
    id_text = field_id.lower()
    side = "call" if re.search(r"(?:^|[_\- ])call(?:$|[_\- ])", text) else None
    if side is None and re.search(r"(?:^|[_\- ])put(?:$|[_\- ])", text):
        side = "put"

    opening = bool(re.search(r"opening|buyer[\s_-]*initiated|initiated[\s_-]*flow", text))
    if "pcr_oi" in id_text or re.search(r"put[\s_-]*call.*open[\s_-]*interest", text):
        measure_kind = "open_interest"
        opening = False
    elif opening and re.search(r"volume|flow|trade", text):
        measure_kind = "opening_flow"
    elif re.search(r"open[\s_-]*interest|\boi\b", text):
        measure_kind = "open_interest"
    elif re.search(r"implied[\s_-]*(?:vol|volatility)|\biv\b", text):
        measure_kind = (
            "implied_variance"
            if re.search(r"model[\s_-]*free|variance", text)
            else "implied_volatility"
        )
    elif re.search(r"historical[\s_-]*(?:vol|volatility)|realized[\s_-]*vol", text):
        measure_kind = (
            "realized_variance"
            if re.search(r"realized|variance", text)
            else "historical_volatility"
        )
    elif re.search(r"breakeven|break[\s_-]*even", text):
        measure_kind = "breakeven"
    elif re.search(r"forward[\s_-]*price|forward", text):
        measure_kind = "forward_price"
    elif re.search(r"volume|flow", text):
        measure_kind = "volume"
    else:
        measure_kind = "unknown"

    tenors: set[str] = set()
    for match in _TENOR_RE.finditer(text):
        number = int(match.group("n"))
        unit = (match.group("u") or "d").lower()
        if unit.startswith("w"):
            number *= 5
        elif unit.startswith("m"):
            number *= 21
        tenors.add(str(number))
    # Bare suffixes such as ``_60`` are common in the official option catalog.
    if not tenors:
        for match in re.finditer(r"[_\-](\d{1,4})(?:$|[_\-])", field_id):
            tenors.add(match.group(1))

    moneyness = sorted(
        set(re.findall(r"\b(?:atm|otm|itm|moneyness|delta|strike[_ -]?\d+)\b", text))
    )
    liquidity = sorted(
        set(
            re.findall(
                r"\b(?:liquid(?:ity)?|open_interest|volume|adv\d*|dollar_volume|bid[_ -]?ask|spread|traded)\b",
                text,
            )
        )
    )
    # MATRIX/VECTOR type alone does not identify call/put, tenor, or measure;
    # require human-readable official metadata before declaring semantics absent.
    semantic_available = bool(name or description)
    return {
        "field_id": field_id,
        "name": name,
        "description": description,
        "type": field.get("type"),
        "dataset": field.get("dataset"),
        "side": side,
        "measure_kind": measure_kind,
        "opening_flow": measure_kind == "opening_flow",
        "tenor": sorted(tenors, key=lambda value: int(value)),
        "moneyness_delta": moneyness,
        "liquidity": liquidity,
        "semantic_available": semantic_available,
    }


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
    fields = option_field_ids(expression, field_metadata)
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


def _required_semantic_match(
    required: str,
    details: list[dict[str, Any]],
    expression: str,
) -> bool:
    text = (expression or "").lower()
    iv_calls = [
        item for item in details
        if item["side"] == "call" and item["measure_kind"] == "implied_volatility"
    ]
    iv_puts = [
        item for item in details
        if item["side"] == "put" and item["measure_kind"] == "implied_volatility"
    ]
    if required == "call IV":
        return bool(iv_calls)
    if required == "put IV":
        return bool(iv_puts)
    if required in {"call IV change", "put IV change"}:
        side = "call" if required.startswith("call") else "put"
        return bool(re.search(r"\bts_delta\s*\(", text) and any(
            item["side"] == side and item["measure_kind"] == "implied_volatility"
            for item in details
        ))
    if required == "matched tenor or moneyness":
        for call in iv_calls:
            for put in iv_puts:
                if set(call["tenor"]) & set(put["tenor"]):
                    return True
                if set(call["moneyness_delta"]) & set(put["moneyness_delta"]):
                    return True
        return False
    if required == "buyer initiated flow":
        return any(item["measure_kind"] == "opening_flow" for item in details)
    if required == "opening volume":
        return any(item["measure_kind"] == "opening_flow" for item in details)
    if required == "put-call ratio":
        return bool(re.search(r"\bpcr\w*\b|put[\s_-]*call", text)) or any(
            item["measure_kind"] == "open_interest" and "pcr" in item["field_id"].lower()
            for item in details
        )
    if required in {"short tenor IV", "long tenor IV"}:
        tenors = sorted({int(tenor) for item in details
                          if item["measure_kind"] == "implied_volatility"
                          for tenor in item["tenor"]})
        return len(tenors) >= 2
    if required == "model-free implied variance":
        return any(item["measure_kind"] == "implied_variance" for item in details)
    if required == "realized variance":
        return any(item["measure_kind"] == "realized_variance" for item in details)
    return False


def audit_expression_semantics(
    mechanism: str,
    expression: str,
    field_metadata: list[dict],
) -> dict[str, Any]:
    """Build a conservative, serializable semantic audit for one hypothesis.

    A catalog row with only id/coverage is intentionally ``unverified`` rather
    than falsely marked missing.  Once official name/description/type evidence
    is available, missing required semantics become an explicit mismatch.
    """
    hypothesis = hypothesis_for(mechanism)
    fields = option_field_ids(expression, field_metadata)
    metadata_by_id = {str(item.get("id")): item for item in field_metadata}
    details = [
        classify_field_semantics(metadata_by_id[field])
        for field in fields
        if field in metadata_by_id
    ]
    metadata_available = bool(details) and any(
        item["semantic_available"] for item in details
    )
    matched = [
        required for required in hypothesis.required_semantics
        if _required_semantic_match(required, details, expression)
    ]
    missing = [
        required for required in hypothesis.required_semantics if required not in matched
    ]
    if not metadata_available:
        status = "unverified"
        fidelity = 0.5
        material_mismatch = False
    else:
        status = "matched" if not missing else "mismatch"
        fidelity = (
            len(matched) / len(hypothesis.required_semantics)
            if hypothesis.required_semantics else 1.0
        )
        material_mismatch = bool(missing)

    target = hypothesis.target
    if (
        "cross-sectional stock returns" in target
        and not target.startswith("exploratory")
        and "not directly" not in target
    ):
        target_status = "aligned"
    elif target in {"future option-strategy returns, not directly stock returns", "aggregate market returns"}:
        target_status = "exploratory_mismatch"
        # An outcome mismatch is material for a stock-return simulation, but
        # remains explicitly exploratory rather than being relabeled as stock alpha.
        fidelity = min(fidelity, 0.35)
    else:
        target_status = "unknown"

    return {
        "status": status,
        "semantic_fidelity": round(float(fidelity), 4),
        "metadata_available": metadata_available,
        "required_semantics": list(hypothesis.required_semantics),
        "matched_required_semantics": matched,
        "missing_required_semantics": missing,
        "material_mismatch": material_mismatch,
        "high_confidence_mismatch": bool(
            hypothesis.confidence == "high" and material_mismatch
        ),
        "target_outcome_alignment": {
            "target": target,
            "status": target_status,
            "brain_default_target": "future cross-sectional stock returns",
        },
        "field_details": details,
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
    semantic_audit = audit_expression_semantics(
        mechanism, expression, field_metadata
    )
    return {
        "hypothesis": asdict(hypothesis),
        "field_mapping": map_expression_fields(expression, field_metadata),
        "semantic_audit": semantic_audit,
        "context_key": research_context_key(
            mechanism, expression, field_metadata, settings
        ),
    }
