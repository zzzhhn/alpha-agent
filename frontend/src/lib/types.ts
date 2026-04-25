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

/* ═══════════════════ Backtest (Interactive) ═══════════════════ */

export interface BacktestParams {
  readonly rsi_period: number;
  readonly rsi_oversold: number;
  readonly rsi_overbought: number;
  readonly macd_fast: number;
  readonly macd_slow: number;
  readonly bollinger_period: number;
}

export interface BacktestRequest {
  readonly ticker: string;
  readonly start_date: string;
  readonly end_date: string;
  readonly rsi_period?: number;
  readonly rsi_oversold?: number;
  readonly rsi_overbought?: number;
  readonly macd_fast?: number;
  readonly macd_slow?: number;
  readonly bollinger_period?: number;
  readonly bollinger_std?: number;
  readonly stop_loss_pct?: number;
  readonly take_profit_pct?: number;
  readonly position_size_pct?: number;
  readonly initial_capital?: number;
}

export interface BacktestTrade {
  readonly date: string;
  readonly side: string;
  readonly price: number;
  readonly shares: number;
  readonly pnl: number;
}

export interface BacktestMetrics {
  readonly total_return: number;
  readonly sharpe_ratio: number;
  readonly sortino_ratio: number;
  readonly max_drawdown: number;
  readonly win_rate: number;
  readonly total_trades: number;
  readonly final_value: number;
}

export interface EquityCurvePoint {
  readonly date: string;
  readonly value: number;
}

export interface BacktestResult {
  readonly ticker: string;
  readonly start_date: string;
  readonly end_date: string;
  readonly params: BacktestParams;
  readonly metrics: BacktestMetrics;
  readonly equity_curve: readonly EquityCurvePoint[];
  readonly trades: readonly BacktestTrade[];
  readonly timestamp: string;
}

export interface BacktestHistoryEntry {
  readonly id: string;
  readonly timestamp: string;
  readonly request: BacktestRequest;
  readonly result: BacktestResult;
  readonly isFavorite: boolean;
}

export interface TickerAnalyzeRequest {
  readonly ticker: string;
  readonly rsi_period?: number;
  readonly macd_fast?: number;
  readonly macd_slow?: number;
  readonly bollinger_period?: number;
}

export interface OHLCVPoint {
  readonly date: string;
  readonly open: number;
  readonly high: number;
  readonly low: number;
  readonly close: number;
  readonly volume: number;
}

export interface TickerAnalysis {
  readonly ticker: string;
  readonly ohlcv: readonly OHLCVPoint[];
  readonly indicators: {
    readonly rsi: readonly (number | null)[];
    readonly macd_line: readonly (number | null)[];
    readonly macd_signal: readonly (number | null)[];
    readonly bb_upper: readonly (number | null)[];
    readonly bb_lower: readonly (number | null)[];
    readonly bb_mid: readonly (number | null)[];
    readonly bb_pctb: readonly (number | null)[];
  };
  readonly regime: string;
  readonly regime_probabilities: Record<string, number>;
  readonly timestamp: string;
}

export interface TickerSearchResult {
  readonly ticker: string;
  readonly name: string;
  readonly sector: string;
}

export interface TickerSearchResponse {
  readonly query: string;
  readonly results: readonly TickerSearchResult[];
  readonly timestamp: string;
}

/* ═══════════════════ Phase 2: Factor Analytics + Gate Editor ═══════════════════ */

export interface FactorRecord {
  readonly id: number;
  readonly name: string;
  readonly expression: string;
  readonly rationale: string;
  readonly ic: number;
  readonly icir: number;
  readonly sharpe: number;
  readonly turnover: number;
  readonly max_drawdown: number;
  readonly alpha_decay: readonly number[];
  readonly created_at: string;
}

export interface FeatureStat {
  readonly name: string;
  readonly value: number;
  readonly mean: number;
  readonly std: number;
  readonly min: number;
  readonly max: number;
}

export interface FactorAnalysisResult {
  readonly ticker: string;
  readonly registry_factors: readonly FactorRecord[];
  readonly feature_stats: readonly FeatureStat[];
  readonly feature_names: readonly string[];
  readonly correlation_matrix: readonly (readonly number[])[];
  readonly total_factors: number;
  readonly timestamp: string;
}

export interface GateScore {
  readonly name: string;
  readonly timeframe: string;
  readonly score: number;
  readonly weight: number;
  readonly passed: boolean;
  readonly description: string;
}

export interface GateSimulationResult {
  readonly ticker: string;
  readonly gates: readonly GateScore[];
  readonly composite_score: number;
  readonly threshold: number;
  readonly passed: boolean;
  readonly signal_description: string;
  readonly weights_used: {
    readonly trend: number;
    readonly momentum: number;
    readonly entry: number;
  };
  readonly timestamp: string;
}

/* ═══════════════════ Phase 3: Portfolio Stress Test ═══════════════════ */

export interface StressPosition {
  readonly ticker: string;
  readonly value: number;
  readonly weight: number;
  readonly shock: number;
  readonly pnl: number;
  readonly contribution: number;
}

export interface StressScenario {
  readonly id: string;
  readonly name: string;
  readonly name_zh: string;
  readonly description?: string;
  readonly period?: string;
}

export interface StressTestResult {
  readonly scenario: StressScenario;
  readonly portfolio: {
    readonly initial_value: number;
    readonly pnl: number;
    readonly return_pct: number;
    readonly final_value: number;
  };
  readonly positions: readonly StressPosition[];
  readonly available_scenarios: readonly StressScenario[];
  readonly timestamp: string;
}

/* ═══════════════════ W2: Hypothesis Translator (T1) ═══════════════════ */

export type FactorUniverse = "CSI300" | "CSI500" | "SP500" | "custom";

export interface FactorSpec {
  readonly name: string;
  readonly hypothesis: string;
  readonly expression: string;
  readonly operators_used: readonly string[];
  readonly lookback: number;
  readonly universe: FactorUniverse;
  readonly justification: string;
}

export interface HypothesisTranslateRequest {
  readonly text: string;
  readonly universe?: FactorUniverse;
  readonly budget_tokens?: number;
}

export interface SmokeReport {
  readonly rows_valid: number;
  readonly ic_spearman: number;
  readonly runtime_ms: number;
}

export interface HypothesisTranslateResponse {
  readonly spec: FactorSpec;
  readonly smoke: SmokeReport;
  readonly llm_tokens: {
    readonly prompt: number;
    readonly completion: number;
  };
  readonly llm_raw: string;
}

export type BacktestDirection = "long_short" | "long_only" | "short_only";

export interface FactorBacktestRequest {
  readonly spec: FactorSpec;
  readonly train_ratio?: number;
  readonly direction?: BacktestDirection;
}

export interface FactorSplitMetrics {
  readonly sharpe: number;
  readonly total_return: number;
  readonly ic_spearman: number;
  readonly n_days: number;
}

export interface FactorBacktestResponse {
  readonly equity_curve: readonly EquityCurvePoint[];
  readonly benchmark_curve: readonly EquityCurvePoint[];
  readonly train_end_index: number;
  readonly train_metrics: FactorSplitMetrics;
  readonly test_metrics: FactorSplitMetrics;
  readonly currency: string;
  readonly factor_name: string;
  readonly benchmark_ticker: string;
  readonly direction?: BacktestDirection;
}

export interface HypothesisHistoryEntry {
  readonly id: string;
  readonly timestamp: string;
  readonly request: HypothesisTranslateRequest;
  readonly result: HypothesisTranslateResponse;
  readonly isFavorite: boolean;
}

/* ═══════════════════ P1: Data Layer ═══════════════════ */

export interface UniverseInfo {
  readonly id: string;
  readonly name: string;
  readonly ticker_count: number;
  readonly benchmark: string;
  readonly tickers: readonly string[];
  readonly start_date: string;
  readonly end_date: string;
  readonly n_days: number;
  readonly currency: string;
}

export interface UniverseListResponse {
  readonly universes: readonly UniverseInfo[];
}

export type CatalogTier = "T1" | "T2" | "T3";

export interface OperatorInfo {
  readonly name: string;
  readonly signature?: string;
  readonly arity?: number | null;
  readonly category: string;
  readonly function_zh?: string;
  readonly description_en?: string;
  readonly description_zh?: string;
  readonly example?: string;
  readonly notes?: string;
  readonly tier: CatalogTier;
  readonly implemented: boolean;
}

export interface OperandInfo {
  readonly name: string;
  readonly category?: string;
  readonly derived?: boolean;
  readonly description_zh?: string;
  readonly description_en?: string;
  readonly usage_zh?: string;
  readonly unit?: string;
  readonly tier: CatalogTier;
  readonly implemented: boolean;
}

export interface CatalogTierSummary {
  readonly T1: number;
  readonly T2: number;
  readonly T3: number;
  readonly total: number;
}

export interface OperandCatalogResponse {
  readonly operators: readonly OperatorInfo[];
  readonly operands: readonly OperandInfo[];
  readonly tier_summary: {
    readonly operators: CatalogTierSummary;
    readonly operands: CatalogTierSummary;
  };
}

export interface CoverageResponse {
  readonly universe_id: string;
  readonly dates: readonly string[];
  readonly tickers: readonly string[];
  readonly matrix: readonly (readonly number[])[];
  readonly total_cells: number;
  readonly missing_cells: number;
  readonly coverage_pct: number;
  readonly missing_per_ticker: Readonly<Record<string, number>>;
}

/* ═══════════════════ P3: Signal Layer ═══════════════════ */

export interface SignalSpec {
  readonly name: string;
  readonly hypothesis: string;
  readonly expression: string;
  readonly operators_used: readonly string[];
  readonly lookback: number;
  readonly universe: "CSI300" | "CSI500" | "SP500" | "custom";
  readonly justification: string;
}

export interface SignalTickerRow {
  readonly ticker: string;
  readonly factor: number;
  readonly sector: string | null;
  readonly cap: number | null;
}

export interface SignalTodayResponse {
  readonly as_of: string;
  readonly factor_name: string;
  readonly universe_size: number;
  readonly n_valid: number;
  readonly top: readonly SignalTickerRow[];
  readonly bottom: readonly SignalTickerRow[];
}

export interface ICPoint {
  readonly date: string;
  readonly ic: number;
  readonly rolling_mean: number | null;
}

export interface ICTimeseriesResponse {
  readonly factor_name: string;
  readonly lookback: number;
  readonly points: readonly ICPoint[];
  readonly summary: {
    readonly ic_mean: number;
    readonly ic_std: number;
    readonly ic_ir: number;
    readonly hit_rate: number;
  };
}

export interface SectorExposure {
  readonly sector: string;
  readonly long_pct: number;
  readonly short_pct: number;
  readonly net_pct: number;
  readonly n_long: number;
  readonly n_short: number;
}

export interface CapBucket {
  readonly bucket: string;
  readonly long_pct: number;
  readonly short_pct: number;
  readonly net_pct: number;
}

export interface ExposureResponse {
  readonly factor_name: string;
  readonly as_of: string;
  readonly sector_exposure: readonly SectorExposure[];
  readonly cap_quintile: readonly CapBucket[];
}

/* ═══════════════════ API Response Envelope ═══════════════════ */

export interface ApiResponse<T> {
  readonly data: T | null;
  readonly error: string | null;
  readonly timestamp: string;
}
