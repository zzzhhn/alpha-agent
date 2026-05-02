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

export interface EquityCurvePoint {
  readonly date: string;
  readonly value: number;
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

/* ═══════════════════ B3: AST visualization ═══════════════════ */

export type AstNode =
  | { readonly type: "operator"; readonly name: string; readonly args: readonly AstNode[] }
  | { readonly type: "operand"; readonly name: string }
  | { readonly type: "literal"; readonly value: number };

export interface ExplainAstResponse {
  readonly tree: AstNode;
}

export type BacktestDirection = "long_short" | "long_only" | "short_only";
export type BacktestMode = "static" | "walk_forward";

export interface FactorBacktestRequest {
  readonly spec: FactorSpec;
  readonly train_ratio?: number;
  readonly direction?: BacktestDirection;
  readonly top_pct?: number;              // P4.1: 0.01–0.50, fraction to long
  readonly bottom_pct?: number;           // P4.1: 0.01–0.50, fraction to short
  readonly transaction_cost_bps?: number; // P4.1: 0–200 bps round-trip cost
  readonly mode?: BacktestMode;           // A7 v3: static (default) | walk_forward
  readonly wf_window_days?: number;       // A7 v3: 20–252, only used when walk_forward
  readonly wf_step_days?: number;         // A7 v3: 5–wf_window_days
  readonly include_breakdown?: boolean;   // B4 v3: opt-in heavy daily_breakdown payload
  readonly purge_days?: number;           // T1.3 v4: 0–30, drop last N rows of train slice
  readonly embargo_days?: number;         // T1.3 v4: 0–30, drop first N rows of test slice
}

export interface WalkForwardWindow {
  readonly window_start: string;
  readonly window_end: string;
  readonly sharpe: number;
  readonly total_return: number;
  readonly ic_spearman: number;
  readonly n_days: number;
  readonly max_drawdown: number;
  readonly turnover: number;
  readonly hit_rate: number;
  // T1.4 v4 — same per-window
  readonly ic_std?: number;
  readonly icir?: number;
  readonly ic_t_stat?: number;
  readonly ic_pvalue?: number;
}

export interface BasketEntry {
  readonly ticker: string;
  readonly weight: number;
}

export interface DailyBreakdown {
  readonly date: string;
  readonly long_basket: readonly BasketEntry[];
  readonly short_basket: readonly BasketEntry[];
  readonly daily_return: number;
  readonly daily_ic: number;
}

export interface FactorSplitMetrics {
  readonly sharpe: number;
  readonly total_return: number;
  readonly ic_spearman: number;
  readonly n_days: number;
  readonly max_drawdown?: number;   // P4.1
  readonly turnover?: number;       // P4.1
  readonly hit_rate?: number;       // P4.1
  // T1.4 v4 — IC distribution + statistical significance
  readonly ic_std?: number;
  readonly icir?: number;            // mean(IC)/std(IC) × √252
  readonly ic_t_stat?: number;       // t-statistic against IC=0
  readonly ic_pvalue?: number;       // two-sided p-value, 1.0 = totally insignificant
}

export interface MonthlyReturn {
  readonly year: number;
  readonly month: number;     // 1–12
  readonly return: number;    // decimal, e.g. 0.073 for +7.3%
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
  readonly monthly_returns?: readonly MonthlyReturn[];   // P4.2
  readonly walk_forward?: readonly WalkForwardWindow[] | null;   // A7 v3
  readonly daily_breakdown?: readonly DailyBreakdown[] | null;   // B4 v3
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

export interface FieldCoverage {
  readonly name: string;
  readonly category: "ohlcv" | "metadata" | "fundamental";
  readonly tier: "T1" | "T2";
  readonly fill_rate: number;     // 0–1
  readonly n_present: number;
  readonly n_total: number;
}

export interface TickerCoverage {
  readonly ticker: string;
  readonly fill_rate: number;
  readonly n_missing: number;
}

export interface CoverageResponse {
  readonly universe_id: string;
  readonly n_tickers: number;
  readonly n_days: number;
  readonly start_date: string;
  readonly end_date: string;
  readonly ohlcv_total_cells: number;
  readonly ohlcv_missing_cells: number;
  readonly ohlcv_coverage_pct: number;
  readonly field_coverage: readonly FieldCoverage[];
  readonly ticker_coverage: readonly TickerCoverage[];
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

/* ═══════════════════ Screener (D1) ═══════════════════ */

export type CombineMethod = "equal_z" | "ic_weighted" | "user_weighted";

export interface ScreenerFactorInput {
  readonly spec: SignalSpec;            // reuse SignalSpec — same FactorSpec shape
  readonly direction: BacktestDirection;
  readonly weight?: number;
}

export interface ScreenerUniverseFilter {
  readonly sectors?: readonly string[];
  readonly min_cap?: number;
  readonly max_cap?: number;
  readonly exclude_tickers?: readonly string[];
}

export interface ScreenerRequest {
  readonly factors: readonly ScreenerFactorInput[];
  readonly universe_filter?: ScreenerUniverseFilter;
  readonly lookback_days?: number;
  readonly top_n?: number;
  readonly combine_method?: CombineMethod;
  readonly as_of_date?: string | null;
}

export interface PerFactorScore {
  readonly factor_idx: number;
  readonly raw: number;
  readonly z: number;
  readonly contribution: number;
}

export interface ScreenerRecommendation {
  readonly ticker: string;
  readonly composite_score: number;
  readonly rank: number;
  readonly sector?: string | null;
  readonly cap?: number | null;
  readonly per_factor_scores: readonly PerFactorScore[];
}

export interface ScreenerFactorDiagnostic {
  readonly factor_idx: number;
  readonly expression: string;
  readonly in_window_ic: number;
  readonly used_weight: number;
  readonly n_eligible: number;
}

export interface ScreenerResponse {
  readonly recommendations: readonly ScreenerRecommendation[];
  readonly factor_diagnostics: readonly ScreenerFactorDiagnostic[];
  readonly metadata: {
    readonly as_of_date: string;
    readonly n_eligible_tickers: number;
    readonly method: CombineMethod;
    readonly lookback_days: number;
  };
}

/* ═══════════════════ API Response Envelope ═══════════════════ */

export interface ApiResponse<T> {
  readonly data: T | null;
  readonly error: string | null;
  readonly timestamp: string;
}
