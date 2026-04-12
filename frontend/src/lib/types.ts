/* ═══════════════════ Service Health ═══════════════════ */

export type ServiceStatus = "green" | "yellow" | "red";

export interface ServiceHealth {
  readonly service_id: string;
  readonly status: ServiceStatus;
  readonly latency_p95_ms: number;
  readonly uptime_pct_24h: number;
  readonly last_check_at: string;
  readonly last_error_at: string | null;
}

export interface ServiceHealthResponse {
  readonly services: readonly ServiceHealth[];
  readonly timestamp: string;
}

/* ═══════════════════ Pipeline Latency ═══════════════════ */

export interface LatencySegment {
  readonly stage: string;
  readonly latency_ms: number;
  readonly percentage: number;
}

export interface PipelineLatency {
  readonly segments: readonly LatencySegment[];
  readonly total_ms: number;
  readonly timestamp: string;
}

/* ═══════════════════ Gateway / Risk Gate ═══════════════════ */

export interface GateRule {
  readonly name: string;
  readonly enabled: boolean;
  readonly passed: boolean;
  readonly confidence: number;
  readonly reason: string;
}

export interface GatewayStatus {
  readonly gates_passed: number;
  readonly gates_failed: number;
  readonly overall_confidence: number;
  readonly signal_description: string;
  readonly rules: readonly GateRule[];
  readonly timestamp: string;
}

/* ═══════════════════ Audit Decision ═══════════════════ */

export interface AuditDecision {
  readonly id: string;
  readonly timestamp: string;
  readonly ticker: string;
  readonly direction: "LONG" | "SHORT" | "NEUTRAL";
  readonly confidence: number;
  readonly reasoning: string;
  readonly reasoning_chain: readonly string[];
  readonly accepted: boolean;
}

export interface AuditSummary {
  readonly total_decisions: number;
  readonly acceptance_rate: number;
  readonly avg_confidence: number;
  readonly last_decision_time: string;
  readonly decisions: readonly AuditDecision[];
}

/* ═══════════════════ System Health ═══════════════════ */

export interface SystemConfig {
  readonly api_calls_24h: number;
  readonly cache_hit_rate: number;
  readonly avg_latency_ms: number;
  readonly error_count_24h: number;
  readonly alerts: readonly Alert[];
}

/* ═══════════════════ Alerts ═══════════════════ */

export type AlertSeverity = "INFO" | "WARN" | "ERROR" | "CRITICAL";

export interface Alert {
  readonly timestamp: string;
  readonly severity: AlertSeverity;
  readonly service: string;
  readonly message: string;
  readonly action_url?: string;
}

/* ═══════════════════ Throughput ═══════════════════ */

export interface ThroughputMetrics {
  readonly tickers_per_sec: number;
  readonly trades_per_sec: number;
  readonly features_per_sec: number;
  readonly timestamp: string;
}

/* ═══════════════════ Audit Event ═══════════════════ */

export interface AuditEvent {
  readonly event_id: string;
  readonly timestamp: string;
  readonly event_type: string;
  readonly user_id: string;
  readonly ticker: string;
  readonly side: "BUY" | "SELL";
  readonly quantity: number;
  readonly order_price: number;
  readonly fill_price: number;
  readonly fill_quantity: number;
  readonly decision_chain_id: string;
  readonly regime_state: {
    readonly current_regime: string;
    readonly probability: number;
  };
  readonly risk_assessment: {
    readonly var_impact_bps: number;
    readonly concentration_impact: number;
  };
  readonly execution_latency_ms: number;
  readonly slippage_bps: number;
  readonly tags: readonly string[];
}

/* ═══════════════════ Market / Alpha ═══════════════════ */

export interface MarketRegime {
  readonly regime: string;
  readonly probability: number;
  readonly timestamp: string;
}

export interface AlphaSignal {
  readonly ticker: string;
  readonly score: number;
  readonly direction: "LONG" | "SHORT" | "NEUTRAL";
  readonly confidence: number;
  readonly sources: readonly string[];
}

/* ═══════════════════ Portfolio ═══════════════════ */

export interface Position {
  readonly ticker: string;
  readonly quantity: number;
  readonly avg_price: number;
  readonly current_price: number;
  readonly pnl: number;
  readonly pnl_pct: number;
  readonly weight: number;
}

/* ═══════════════════ Orders ═══════════════════ */

export type OrderStatus =
  | "PENDING"
  | "FILLED"
  | "PARTIAL"
  | "CANCELLED"
  | "REJECTED";

export interface Order {
  readonly order_id: string;
  readonly ticker: string;
  readonly side: "BUY" | "SELL";
  readonly quantity: number;
  readonly price: number;
  readonly status: OrderStatus;
  readonly filled_quantity: number;
  readonly timestamp: string;
}

/* ═══════════════════ Navigation ═══════════════════ */

export interface NavItem {
  readonly id: string;
  readonly label: string;
  readonly labelZh: string;
  readonly icon: string;
  readonly href: string;
  readonly badge?: string;
}

export interface PipelineStage {
  readonly id: string;
  readonly label: string;
  readonly labelZh: string;
}

/* ═══════════════════ Market Indicators ═══════════════════ */

export interface MarketIndicators {
  readonly ticker: string;
  readonly rsi: number;
  readonly macd: number;
  readonly bollinger_pct_b: number;
  readonly volatility: number;
  readonly log_return: number;
  readonly timestamp: string;
}

export interface FeatureState {
  readonly features: readonly string[];
  readonly tickers: readonly string[];
  readonly heatmap: readonly (readonly number[])[];
  readonly timestamp: string;
}

/* ═══════════════════ Alpha Factors ═══════════════════ */

export type FactorStatus = "active" | "testing" | "disabled";

export interface AlphaFactor {
  readonly id: string;
  readonly expression: string;
  readonly ic: number;
  readonly icir: number;
  readonly sharpe: number;
  readonly status: FactorStatus;
  readonly created_at: string;
}

export interface AlphaFactorSummary {
  readonly best_ic: number;
  readonly best_sharpe: number;
  readonly total_factors: number;
  readonly pipeline_status: string;
}

/* ═══════════════════ Portfolio Risk ═══════════════════ */

export interface PortfolioRisk {
  readonly total_exposure: number;
  readonly diversification_score: number;
  readonly max_position_pct: number;
  readonly var_95: number;
  readonly sharpe_ratio: number;
  readonly max_drawdown: number;
  readonly beta: number;
  readonly timestamp: string;
}

/* ═══════════════════ API Response Envelope ═══════════════════ */

export interface ApiResponse<T> {
  readonly data: T | null;
  readonly error: string | null;
  readonly timestamp: string;
}
