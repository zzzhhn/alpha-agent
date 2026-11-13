"""Explicit model capabilities and dated estimates; never select a model for users."""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from alpha_agent.llm.base import LLMResponse


@dataclass(frozen=True)
class ModelProfile:
    model: str
    reasoning_efforts: tuple[str, ...]
    input_usd_per_million: float
    cached_input_usd_per_million: float
    output_usd_per_million: float
    pricing_as_of: str
    source: str


# Add models only after checking their own API contract. Do not infer support
# from a gpt-* prefix or silently enable global LiteLLM drop_params.
SOL_PROFILE = ModelProfile(
    model="gpt-6.1-sol",
    reasoning_efforts=("low", "medium", "high", "xhigh", "max"),
    input_usd_per_million=2.0,
    cached_input_usd_per_million=0.1,
    output_usd_per_million=10.0,
    pricing_as_of="2026-11-13",
    source="https://developers.openai.com/api/docs/models/gpt-6.1-sol",
)


def model_profile(model: str) -> ModelProfile | None:
    """Known bare OpenAI ID or LiteLLM-prefixed ID; unknown aliases stay unknown."""
    return SOL_PROFILE if model in (SOL_PROFILE.model, f"openai/{SOL_PROFILE.model}") else None


def generation_parameters(
    model: str, temperature: float, max_tokens: int, *, reasoning_effort: str | None = None,
) -> dict[str, object]:
    profile = model_profile(model)
    if reasoning_effort is not None and (
        profile is None or reasoning_effort not in profile.reasoning_efforts
    ):
        raise ValueError("Unsupported reasoning effort for the selected model")
    if profile is None:
        return {"temperature": temperature, "max_tokens": max_tokens}
    parameters: dict[str, object] = {"max_completion_tokens": max_tokens}
    if reasoning_effort is not None:
        parameters["reasoning_effort"] = reasoning_effort
    return parameters


def estimate_standard_cost(response: LLMResponse, *, api_base: str) -> dict | None:
    """Standard short-context text estimate, not a bill or credit-balance check.

    Reasoning tokens are already included in completion_tokens, never added
    again. Unknown usage/model/custom endpoints cannot acquire an invented price.
    Cache-write fees, tools and non-standard service tiers are outside this
    estimate; the smoke command requests none of them.
    """
    endpoint = urlsplit(api_base)
    profile = model_profile(response.model)
    if (endpoint.scheme != "https" or endpoint.netloc != "api.openai.com"
            or endpoint.path.rstrip("/") != "/v1" or profile is None):
        return None
    prompt, completion = response.prompt_tokens, response.completion_tokens
    cached = response.cached_prompt_tokens
    if (prompt < 0 or completion < 0 or prompt + completion == 0
            or prompt > 272000 or (cached is not None and not 0 <= cached <= prompt)):
        return None
    cost = ((prompt - (cached or 0)) * profile.input_usd_per_million
            + (cached or 0) * profile.cached_input_usd_per_million
            + completion * profile.output_usd_per_million) / 1_000_000
    return {
        "amount_usd": round(cost, 8),
        "basis": "standard_uncached_estimate" if cached is None else "standard_cache_adjusted_estimate",
        "pricing_as_of": profile.pricing_as_of,
        "source": profile.source,
    }
