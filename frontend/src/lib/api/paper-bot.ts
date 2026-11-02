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
  readonly config_version: number;
  readonly credential_configured: boolean;
  readonly next_wake_at: string | null;
  readonly market: {
    readonly session_date: string;
    readonly is_open: boolean;
    readonly open_at: string | null;
    readonly close_at: string | null;
    readonly next_open_at: string | null;
  };
}

export type PaperBotConfigPatch = Partial<Pick<PaperBotConfig,
  "provider" | "model" | "instructions" | "schedule_enabled" | "open_enabled" | "close_enabled" |
  "open_offset_minutes" | "close_offset_minutes" | "max_daily_runs" | "max_positions" |
  "max_position_weight" | "fee_bps" | "slippage_bps"
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

const root = (id: number) => `/api/paper/accounts/${id}`;
export const isActivePaperRun = (run: PaperBotRun | null | undefined) => run?.status === "queued" || run?.status === "running";
export const fetchPaperAccounts = () => paperFetch<{ accounts: readonly PaperAccountSummary[] }>("/api/paper/accounts");
export const createPaperBotAccount = (body: { name: string; initial_cash: number }) => paperFetch<PaperAccountSummary>("/api/paper/accounts", { method: "POST", body: JSON.stringify(body) });
export const fetchBotAccount = (id: number) => paperFetch<AccountResponse>(root(id));
export const fetchBotCurve = (id: number) => paperFetch<EquityCurveResponse>(`${root(id)}/equity-curve`);
export const fetchBotOrders = (id: number, limit = 5, offset = 0) => paperFetch<OrderListResponse>(`${root(id)}/orders?limit=${limit}&offset=${offset}`);
export const fetchPaperBotConfig = (id: number) => paperFetch<PaperBotConfig>(`${root(id)}/bot`);
export const patchPaperBotConfig = (id: number, body: PaperBotConfigPatch) => paperFetch<PaperBotConfig>(`${root(id)}/bot`, { method: "PATCH", body: JSON.stringify(body) });
export const fetchPaperBotRuns = (id: number, limit = 5, offset = 0) => paperFetch<PaperBotRunList>(`${root(id)}/runs?limit=${limit}&offset=${offset}`);
export const fetchPaperBotRun = (id: number, runId: string) => paperFetch<PaperBotRun>(`${root(id)}/runs/${encodeURIComponent(runId)}`);
export const startPaperBotRun = (id: number) => paperFetch<PaperBotRun>(`${root(id)}/runs`, { method: "POST", body: "{}" });
export const stopPaperBotRun = (id: number, runId: string) => paperFetch<PaperBotRun>(`${root(id)}/runs/${encodeURIComponent(runId)}/stop`, { method: "POST", body: "{}" });
