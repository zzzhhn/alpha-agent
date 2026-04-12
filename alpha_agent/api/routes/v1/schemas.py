"""Pydantic response models for API v1 endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Market
# ---------------------------------------------------------------------------

class MarketRegime(BaseModel):
    """HMM market regime detection result."""

    current_regime: str = Field(description="Detected market regime label")
    current_regime_zh: str = Field(default="", description="Chinese label")
    regime_probabilities: dict[str, float] = Field(
        default_factory=dict, description="Probability per regime"
    )
    transition_probability: float = Field(
        description="Probability of regime change"
    )
    model_scores: dict[str, float] = Field(default_factory=dict)
    source: str = "HMM GaussianHMM"


class IndicatorValue(BaseModel):
    """A single technical indicator data point."""

    name: str
    value: float
    timestamp: Optional[str] = None


class TickerIndicators(BaseModel):
    """Technical indicators for a single ticker."""

    ticker: str
    indicators: list[IndicatorValue] = Field(default_factory=list)
    ohlcv_recent: list[dict] = Field(
        default_factory=list, description="Last 20 OHLCV bars"
    )


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------

class ModelPrediction(BaseModel):
    """Single model prediction result."""

    ticker: str
    bull_prob: float
    bear_prob: float
    direction: str


class InferencePredictResponse(BaseModel):
    """Fused prediction across all models."""

    assets: list[dict] = Field(default_factory=list)
    fusion: dict = Field(default_factory=dict)
    source: str = "GradientBoosting + MLP"


class ModelInfo(BaseModel):
    """Status of a single ML model."""

    name: str
    trained: bool = False
    last_trained: Optional[float] = None
    file: Optional[str] = None
    description: str = ""


class ModelsListResponse(BaseModel):
    """All registered models and their training status."""

    models: list[ModelInfo] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Alpha
# ---------------------------------------------------------------------------

class FactorResult(BaseModel):
    """A discovered alpha factor."""

    name: str = ""
    expression: str = ""
    ic: Optional[float] = None
    sharpe: Optional[float] = None
    metadata: dict = Field(default_factory=dict)


class AlphaFactorsResponse(BaseModel):
    """Factor discovery results."""

    factors: list[FactorResult] = Field(default_factory=list)
    pipeline_status: dict = Field(default_factory=dict)


class BacktestResult(BaseModel):
    """Backtest run summary."""

    sharpe: Optional[float] = None
    max_drawdown: Optional[float] = None
    annual_return: Optional[float] = None
    total_trades: int = 0
    win_rate: Optional[float] = None
    period: dict = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

class Position(BaseModel):
    """A single portfolio position."""

    ticker: str
    direction: str
    weight: float
    score: float


class RiskMetrics(BaseModel):
    """Portfolio risk metrics."""

    total_exposure: float = 0.0
    max_single_position: float = 0.0
    diversification_score: float = 0.0
    var_95: Optional[float] = Field(
        default=None, description="Value at Risk (95%)"
    )
    realized_volatility: Optional[float] = None


class PortfolioPositionsResponse(BaseModel):
    """Current portfolio positions."""

    positions: list[Position] = Field(default_factory=list)
    total_positions: int = 0


class PortfolioRiskResponse(BaseModel):
    """Portfolio risk analysis."""

    risk_metrics: RiskMetrics = Field(default_factory=RiskMetrics)
    positions: list[Position] = Field(default_factory=list)
    backtest_summary: BacktestResult = Field(default_factory=BacktestResult)


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------

class PendingOrder(BaseModel):
    """A pending order."""

    order_id: str = ""
    ticker: str = ""
    direction: str = ""
    size_pct: float = 0.0
    status: str = "pending"
    created_at: Optional[str] = None


class OrderHistoryEntry(BaseModel):
    """A completed order."""

    order_id: str = ""
    ticker: str = ""
    direction: str = ""
    size_pct: float = 0.0
    status: str = ""
    executed_at: Optional[str] = None
    price: Optional[float] = None


class PendingOrdersResponse(BaseModel):
    """All pending orders."""

    pending_orders: list[PendingOrder] = Field(default_factory=list)
    execution_config: dict = Field(default_factory=dict)


class OrderHistoryResponse(BaseModel):
    """Order execution history."""

    orders: list[OrderHistoryEntry] = Field(default_factory=list)
    total: int = 0


# ---------------------------------------------------------------------------
# Gateway (gate checks)
# ---------------------------------------------------------------------------

class GateCheck(BaseModel):
    """Single gate evaluation result."""

    name: str = ""
    passed: bool = False
    confidence: float = 0.0
    reason: str = ""


class GatewayStatusResponse(BaseModel):
    """Overall gateway status."""

    ticker: str
    gates: list[GateCheck] = Field(default_factory=list)
    overall_confidence: float = 0.0
    passed: bool = False
    signal_description: str = ""


class GateRule(BaseModel):
    """Definition of a gate rule."""

    name: str
    description: str = ""
    enabled: bool = True
    threshold: Optional[float] = None


class GatewayRulesResponse(BaseModel):
    """All configured gate rules."""

    rules: list[GateRule] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------

class AuditEntry(BaseModel):
    """A single audit log entry."""

    timestamp: Optional[str] = None
    ticker: str = ""
    direction: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    source: str = ""


class AuditLogResponse(BaseModel):
    """Audit trail entries."""

    entries: list[AuditEntry] = Field(default_factory=list)
    total_entries: int = 0
    filters: dict = Field(default_factory=dict)


class DecisionEntry(BaseModel):
    """A recorded trading decision."""

    timestamp: Optional[str] = None
    ticker: str = ""
    direction: str = ""
    confidence: float = 0.0
    position_size_pct: float = 0.0
    leverage: float = 1.0
    reasoning: str = ""
    source: str = ""


class DecisionHistoryResponse(BaseModel):
    """Decision history."""

    decisions: list[DecisionEntry] = Field(default_factory=list)
    total: int = 0


# ---------------------------------------------------------------------------
# System
# ---------------------------------------------------------------------------

class ServiceStatus(BaseModel):
    """Status of a single service."""

    name: str
    status: str = "unknown"


class SystemHealthResponse(BaseModel):
    """System health overview."""

    services: dict[str, str] = Field(default_factory=dict)
    models: dict = Field(default_factory=dict)
    system: dict = Field(default_factory=dict)
    cache_stats: dict = Field(default_factory=dict)


class SystemConfigResponse(BaseModel):
    """Non-secret system configuration."""

    tickers: list[str] = Field(default_factory=list)
    cache_ttl_seconds: int = 300
    fastapi_port: int = 6008
    llm_provider: str = "ollama"
    ollama_model: str = ""
    max_iterations: int = 3
    data_cache_max_age_hours: int = 24


# ---------------------------------------------------------------------------
# Features
# ---------------------------------------------------------------------------

class FeatureValue(BaseModel):
    """Single feature with z-score and percentile."""

    name: str
    value: float
    z_score: float = 0.0
    percentile: float = 0.5


class FeatureStateResponse(BaseModel):
    """Feature state for a ticker (blueprint p9 data contract)."""

    ticker: str
    timestamp: str = ""
    features: list[FeatureValue] = Field(default_factory=list)


class FeatureStatRow(BaseModel):
    """Feature statistics summary row."""

    name: str
    value: float
    mean: float
    std: float
    min: float
    max: float


class FeatureStatsResponse(BaseModel):
    """Feature statistics for a ticker."""

    ticker: str
    stats: list[FeatureStatRow] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Data Quality
# ---------------------------------------------------------------------------

class ValidationRuleResult(BaseModel):
    """Single data quality validation result."""

    rule: str
    passed: bool
    severity: str = "pass"
    details: str = ""
    affected_rows: int = 0


class DataQualityResponse(BaseModel):
    """Data quality report for a ticker."""

    ticker: str
    total_rows: int = 0
    rules: list[ValidationRuleResult] = Field(default_factory=list)
    overall_pass: bool = False


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

class DashboardSummaryResponse(BaseModel):
    """Aggregated dashboard data."""

    market_state: dict = Field(default_factory=dict)
    inference: dict = Field(default_factory=dict)
    gate: dict = Field(default_factory=dict)
    decision: dict = Field(default_factory=dict)
    model_voting: list[dict] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)
