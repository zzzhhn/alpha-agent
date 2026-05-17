"""LLM-powered trading decision engine using Gemma 4 via Ollama."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from alpha_agent.llm.base import LLMClient, LLMResponse, Message
from alpha_agent.models.fusion import FusionResult
from alpha_agent.models.hmm import MarketState
from alpha_agent.trading.gate import GateResult

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TradingDecision:
    """Immutable LLM trading decision."""

    direction: str  # "Bullish" / "Bearish" / "Neutral"
    confidence: float  # 0-100
    position_size_pct: float  # 0-100
    leverage: float  # 1x-5x
    ticker: str
    reasoning: str
    source: str  # "LLM" or "Rule-based fallback"


_SYSTEM_PROMPT = """You are AlphaCore, a quantitative trading decision engine.
You receive market state analysis, model predictions, and multi-timeframe gate signals.
You MUST respond with ONLY a JSON object. No markdown, no explanation, no text before or after.

Rules:
1. If gate has NOT passed, set confidence < 30 and position_size_pct < 5.
2. If model consensus and gate direction conflict, prefer the gate (trend-following).
3. Leverage range: 1x (low confidence) to 3x (high confidence). Never exceed 3x.
4. Position size: 3-15% of portfolio, scaled by confidence.

Respond with EXACTLY this JSON structure (no other text):
{"direction":"Bullish","confidence":50,"position_size_pct":5,"leverage":1,"ticker":"NVDA","reasoning":"explanation here"}"""


class LLMDecisionEngine:
    """Synthesizes all model outputs into a final trading decision via LLM."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._client = llm_client

    async def decide(
        self,
        ticker: str,
        market_state: MarketState,
        fusion: FusionResult,
        gate: GateResult,
    ) -> TradingDecision:
        """Generate trading decision. Falls back to rules if LLM unavailable."""
        if self._client is None:
            return self._rule_based_fallback(ticker, fusion, gate)

        try:
            available = await self._client.is_available()
            if not available:
                logger.warning("Ollama not available; using rule-based fallback.")
                return self._rule_based_fallback(ticker, fusion, gate)
        except Exception:
            return self._rule_based_fallback(ticker, fusion, gate)

        user_msg = self._build_prompt(ticker, market_state, fusion, gate)

        try:
            response = await self._client.chat(
                messages=[
                    Message(role="system", content=_SYSTEM_PROMPT),
                    Message(role="user", content=user_msg),
                ],
                temperature=0.3,
                max_tokens=512,
            )
            return self._parse_response(response, ticker)

        except Exception:
            logger.warning("LLM decision failed; using rule-based fallback.", exc_info=True)
            return self._rule_based_fallback(ticker, fusion, gate)

    def _build_prompt(
        self,
        ticker: str,
        market_state: MarketState,
        fusion: FusionResult,
        gate: GateResult,
    ) -> str:
        """Construct structured prompt with all model outputs."""
        gate_details = "\n".join(
            f"  - {g.name} ({g.timeframe}): score={g.score:.2f}, passed={g.passed}"
            for g in gate.gates
        )

        return f"""Ticker: {ticker}

Market Regime (HMM):
  Current: {market_state.current_regime}
  Transition probability: {market_state.transition_probability:.2%}
  Probabilities: {market_state.regime_probabilities}

Model Fusion:
  Direction: {fusion.direction}
  Confidence: {fusion.confidence:.2%}
  Bull/Bear: {fusion.bull_prob:.2%} / {fusion.bear_prob:.2%}
  Per-model: XGBoost={fusion.per_model.get('XGBoost', 'N/A')}, LSTM={fusion.per_model.get('LSTM', 'N/A')}

Multi-Timeframe Gate:
  Overall: {gate.overall_confidence:.2%}, Passed: {gate.passed}
{gate_details}

Respond with ONLY the JSON object, nothing else."""

    def _parse_response(self, response: LLMResponse, ticker: str) -> TradingDecision:
        """Parse LLM JSON output into TradingDecision."""
        import re

        content = response.content.strip()

        # Try direct parse first
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            # Try extracting JSON from markdown code blocks or mixed text
            match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", content)
            if match:
                try:
                    data = json.loads(match.group(0))
                except json.JSONDecodeError:
                    logger.error("Failed to parse extracted JSON: %s", match.group(0)[:200])
                    return self._rule_based_fallback(ticker, None, None)
            else:
                logger.error("No JSON found in LLM response: %s", content[:200])
                return self._rule_based_fallback(ticker, None, None)

        return TradingDecision(
            direction=str(data.get("direction", "Neutral")),
            confidence=float(data.get("confidence", 50)),
            position_size_pct=float(data.get("position_size_pct", 5)),
            leverage=float(data.get("leverage", 1)),
            ticker=ticker,
            reasoning=str(data.get("reasoning", "")),
            source="LLM (Gemma 4 26B)",
        )

    @staticmethod
    def _rule_based_fallback(
        ticker: str,
        fusion: FusionResult | None,
        gate: GateResult | None,
    ) -> TradingDecision:
        """Simple rule-based decision when LLM is unavailable."""
        if fusion is None:
            return TradingDecision(
                direction="Neutral",
                confidence=25.0,
                position_size_pct=0.0,
                leverage=1.0,
                ticker=ticker,
                reasoning="Insufficient data for decision.",
                source="Rule-based fallback",
            )

        confidence = fusion.confidence * 100
        gate_passed = gate.passed if gate else False

        if not gate_passed:
            confidence = min(confidence, 30.0)

        position = min(confidence * 0.15, 15.0) if gate_passed else 3.0
        leverage = 1.0 + (confidence / 100) if gate_passed else 1.0

        return TradingDecision(
            direction=fusion.direction,
            confidence=confidence,
            position_size_pct=position,
            leverage=min(leverage, 3.0),
            ticker=ticker,
            reasoning=(
                f"Rule-based: fusion={fusion.direction} ({fusion.confidence:.0%}), "
                f"gate={'passed' if gate_passed else 'failed'}."
            ),
            source="Rule-based fallback",
        )
