import { paperFetch, type AccountResponse, type EquityCurveResponse, type OrderListResponse } from "./paper";

export interface PaperAccountSummary {
  readonly account_id: number;
  readonly kind: "human" | "bot";
  readonly name: string;
  readonly status: string;
  readonly initial_cash: number;
}

export interface PaperBotConfig {
  readonly account_id: number;
  readonly provider: string;
  readonly model: string;
  readonly instructions: string;
  readonly schedule_enabled: boolean;
  readonly open_enabled: boolean;
  readonly close_enabled: boolean;
  readonly open_offset_minutes: number;
  readonly close_offset_minutes: number;
  readonly max_daily_runs: number;
  readonly max_positions: number;
  readonly max_position_weight: number;
  readonly fee_bps: number;
  readonly slippage_bps: number;
  readonly horizon_sessions?: number;
  readonly max_research_age_sessions?: number;
  readonly min_trade_weight_delta?: number;
  readonly max_turnover_weight?: number;
  readonly cash_policy?: "discretionary";
  readonly config_version: number;
  readonly credential_configured: boolean;
  readonly next_wake_at: string | null;
  readonly readiness?: PaperBotReadiness;
  readonly schedule_observations?: readonly PaperBotScheduleObservation[];
  readonly market: {
    readonly session_date: string;
    readonly is_open: boolean;
    readonly open_at: string | null;
    readonly close_at: string | null;
    readonly next_open_at: string | null;
  };
}

export interface PaperBotReadiness {
  readonly evaluated_at: string;
  readonly can_wake: boolean;
  readonly blocked_reasons: readonly string[];
  readonly warnings?: readonly string[];
  readonly schedule_reason: string;
  readonly today_runs: number;
  readonly research_as_of: string | null;
  readonly research_age_sessions: number | null;
}

export interface PaperBotScheduleObservation {
  readonly inferred?: boolean;
  readonly session_date: string;
  readonly slot: string;
  readonly planned_at: string | null;
  readonly observed_at: string | null;
  readonly status: string;
  readonly reason: string | null;
  readonly run_id: string | null;
}

export type PaperBotConfigPatch = Partial<Pick<PaperBotConfig,
  "provider" | "model" | "instructions" | "schedule_enabled" | "open_enabled" | "close_enabled" |
  "open_offset_minutes" | "close_offset_minutes" | "max_daily_runs" | "max_positions" |
  "max_position_weight" | "fee_bps" | "slippage_bps" | "horizon_sessions" |
  "max_research_age_sessions" | "min_trade_weight_delta" | "max_turnover_weight" | "cash_policy"
>>;

export type PaperBotRunStatus = "queued" | "running" | "completed" | "no_trade" | "partial" | "failed" | "skipped" | "stopped";

export interface PaperBotRun {
  readonly id: string;
  readonly account_id: number;
  readonly status: PaperBotRunStatus;
  readonly stage: string | null;
  readonly trigger: string;
  readonly created_at: string;
  readonly started_at: string | null;
  readonly finished_at: string | null;
  readonly summary: string | null;
  readonly error: string | null;
  readonly result: Readonly<Record<string, unknown>> | null;
  readonly prompt_tokens: number | null;
  readonly completion_tokens: number | null;
  readonly provider: string | null;
  readonly model: string | null;
}

export interface PaperBotRunList { readonly runs: readonly PaperBotRun[]; readonly total: number }

export interface PaperBotPerformance {
  readonly account_id: number;
  readonly cohort_id: number;
  readonly as_of: string;
  readonly history: { readonly scope: string; readonly sample_count: number; readonly valid_nav_count: number; readonly null_nav_count: number; readonly first_date: string | null; readonly last_date: string | null; readonly truncated: boolean };
  readonly valuation: { readonly cash: number | null; readonly portfolio_value: number | null; readonly invested_value: number | null; readonly exposure_pct: number | null; readonly quality: string; readonly valued_at: string | null };
  readonly matched_window: { readonly start_date: string | null; readonly end_date: string | null; readonly sample_count: number; readonly expected_sessions: number | null; readonly missing_sessions: number | null; readonly complete: boolean; readonly bot_return_pct: number | null; readonly spy_return_pct: number | null; readonly cash_return_pct: number | null; readonly bot_max_drawdown_pct: number | null; readonly reason: string | null };
  readonly orders: { readonly scope: string; readonly filled: number; readonly pending: number; readonly failed: number; readonly expired: number; readonly cancelled: number; readonly paid_fees: number | null };
  readonly turnover: { readonly window_start: string | null; readonly window_end: string | null; readonly gross_filled_notional: number | null; readonly average_nav: number | null; readonly ratio_pct: number | null; readonly reason: string | null };
  readonly llm: { readonly scope: string; readonly run_count: number; readonly first_run_at?: string | null; readonly last_run_at?: string | null; readonly prompt_tokens: number | null; readonly completion_tokens: number | null; readonly cost_usd: number | null; readonly cost_reason: string | null };
  readonly comparators: { readonly spy: { readonly basis: string }; readonly cash: { readonly basis: string }; readonly deterministic: { readonly available: boolean; readonly reason: string } };
}

const root = (id: number) => `/api/paper/accounts/${id}`;
export const isActivePaperRun = (run: PaperBotRun | null | undefined) => run?.status === "queued" || run?.status === "running";
/** Scheduling and non-blocking research warnings do not determine manual readiness. */
export const canWakePaperBot = (config: PaperBotConfig | null | undefined) => config?.credential_configured === true && config.readiness?.can_wake !== false;
export const fetchPaperAccounts = () => paperFetch<{ accounts: readonly PaperAccountSummary[] }>("/api/paper/accounts");
export const createPaperBotAccount = (body: { name: string; initial_cash: number }) => paperFetch<PaperAccountSummary>("/api/paper/accounts", { method: "POST", body: JSON.stringify(body) });
export const fetchBotAccount = (id: number) => paperFetch<AccountResponse>(root(id));
export const fetchBotCurve = (id: number) => paperFetch<EquityCurveResponse>(`${root(id)}/equity-curve`);
export const fetchBotOrders = (id: number, limit = 5, offset = 0) => paperFetch<OrderListResponse>(`${root(id)}/orders?limit=${limit}&offset=${offset}`);
export const fetchPaperBotConfig = (id: number) => paperFetch<PaperBotConfig>(`${root(id)}/bot`);
export const fetchPaperBotPerformance = (id: number) => paperFetch<PaperBotPerformance>(`${root(id)}/bot/performance`);
export const patchPaperBotConfig = (id: number, body: PaperBotConfigPatch) => paperFetch<PaperBotConfig>(`${root(id)}/bot`, { method: "PATCH", body: JSON.stringify(body) });
export const fetchPaperBotRuns = (id: number, limit = 5, offset = 0) => paperFetch<PaperBotRunList>(`${root(id)}/runs?limit=${limit}&offset=${offset}`);
export const fetchPaperBotRun = (id: number, runId: string) => paperFetch<PaperBotRun>(`${root(id)}/runs/${encodeURIComponent(runId)}`);
export const startPaperBotRun = (id: number) => paperFetch<PaperBotRun>(`${root(id)}/runs`, { method: "POST", body: "{}" });
export const stopPaperBotRun = (id: number, runId: string) => paperFetch<PaperBotRun>(`${root(id)}/runs/${encodeURIComponent(runId)}/stop`, { method: "POST", body: "{}" });
