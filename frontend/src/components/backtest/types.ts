import type { FactorBacktestResponse, FactorUniverse } from "@/lib/types";

/**
 * State machine for a single backtest run. `result` is unwrapped from the
 * fetchJson envelope (ApiResponse<T>) — the hook resolves `data | error`
 * before transitioning to `ok` / `error`, so consumers don't deal with the
 * envelope here.
 */
export type RunState =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "ok"; result: FactorBacktestResponse }
  | { kind: "error"; message: string };

export type DirectionMode = "long_short" | "long_only" | "short_only";
export type BacktestMode = "static" | "walk_forward";

/**
 * Form-driven backtest parameters. The hook turns this into a real
 * `FactorBacktestRequest` (which needs a constructed `FactorSpec`) at
 * runOnce time.
 *
 * `topPct` / `bottomPct` are stored as percentages 0–100 in this UI layer
 * for display ergonomics; the hook converts to fractions (0.01–0.50) before
 * calling the API.
 *
 * `operatorsUsed` is required by `FactorSpec` — the form must surface this
 * (the existing TmBacktestForm already tracks it). We carry it here so the
 * hook can build the spec without page-level orchestration.
 *
 * `neutralize` is a boolean here (UI toggle); converted to `"none" | "sector"`
 * inside the hook to match the request shape.
 */
export interface BacktestParams {
  expression: string;
  operatorsUsed: readonly string[];
  direction: DirectionMode;
  topPct: number;       // 0 to 100 (UI %); hook converts to 0–1 fraction
  bottomPct: number;    // 0 to 100 (UI %)
  universe: FactorUniverse;
  lookback: number;     // days
  benchmark: "SPY" | "RSP";
  neutralize: boolean;
  transactionCostBps: number;
  mode: BacktestMode;
}

export interface RunMetrics {
  sharpe: number | null;
  maxDD: number | null;        // -0.15 means -15%
  ic: number | null;
  turnover: number | null;     // 0.28 means 28%
  annReturn: number | null;
}

export interface Run {
  id: string;
  ts: number;
  params: BacktestParams;
  metrics: RunMetrics;
  raw: FactorBacktestResponse;
}

export type MetricDirection = "up_good" | "down_good";
export type DeltaArrow = "up" | "down" | "flat";

export interface MetricDelta {
  arrow: DeltaArrow;
  diff: number;
  betterThanBaseline: boolean;
}

/**
 * Per-metric deltas keyed by metric name. `null` means the comparison is
 * not computable (no baseline, no current, or current === baseline).
 */
export interface RunDeltas {
  sharpe: MetricDelta | null;
  maxDD: MetricDelta | null;
  ic: MetricDelta | null;
  turnover: MetricDelta | null;
  annReturn: MetricDelta | null;
}
