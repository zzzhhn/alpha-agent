"use client";

import { useCallback, useMemo, useState } from "react";
import { runFactorBacktest } from "@/lib/api";
import type {
  FactorBacktestRequest,
  FactorBacktestResponse,
  FactorSpec,
} from "@/lib/types";
import type {
  BacktestParams,
  MetricDelta,
  MetricDirection,
  Run,
  RunDeltas,
  RunMetrics,
  RunState,
} from "./types";

const MAX_RECENT_RUNS = 10;

// Thresholds (locked per spec §8.2)
const TH_SHARPE_OK = 1.0;
const TH_SHARPE_WARN = 0.5;
const TH_MAXDD_OK = -0.15;
const TH_MAXDD_BAD = -0.25;
const TH_IC_OK = 0.02;
const TH_TURNOVER_OK = 0.4;
const TH_TURNOVER_BAD = 0.6;
const TH_ANNRET_OK = 0.10;

/**
 * Optional spec metadata that the page can supply when prefilling from a
 * /alpha translate handoff. Defaults are used otherwise.
 */
export interface SpecMetadata {
  name: string;
  hypothesis: string;
  justification: string;
}

const DEFAULT_SPEC_METADATA: SpecMetadata = {
  name: "user_factor",
  hypothesis: "user-supplied factor",
  justification: "interactive backtest",
};

export const DEFAULT_PARAMS: BacktestParams = {
  expression: "",
  operatorsUsed: [],
  direction: "long_short",
  topPct: 30,
  bottomPct: 30,
  universe: "SP500",
  lookback: 252,
  benchmark: "SPY",
  neutralize: false,
  transactionCostBps: 10,
  mode: "static",
};

// Hoisted (rerender-memo-with-default-value): stable identity across renders
// so downstream consumers' effects on `thresholds` don't re-run spuriously.
const THRESHOLDS = {
  sharpe: TH_SHARPE_OK,
  sharpeWarn: TH_SHARPE_WARN,
  maxDD: TH_MAXDD_OK,
  maxDDBad: TH_MAXDD_BAD,
  ic: TH_IC_OK,
  turnover: TH_TURNOVER_OK,
  turnoverBad: TH_TURNOVER_BAD,
  annReturn: TH_ANNRET_OK,
} as const;

function extractMetrics(raw: FactorBacktestResponse): RunMetrics {
  const m = raw.test_metrics;
  return {
    sharpe: m?.sharpe ?? null,
    maxDD: m?.max_drawdown ?? null,
    ic: m?.ic_spearman ?? null,
    turnover: m?.turnover ?? null,
    annReturn:
      m?.total_return != null && m?.n_days != null && m.n_days > 0
        ? Math.pow(1 + m.total_return, 252 / m.n_days) - 1
        : null,
  };
}

function makeId(): string {
  return `run_${Date.now()}_${Math.floor(Math.random() * 1000)}`;
}

/**
 * Build a real `FactorBacktestRequest` from form params + optional spec
 * metadata. UI carries `topPct`/`bottomPct` as 0–100 percentages; API
 * expects 0–1 fractions, so we divide by 100 here. `neutralize` is a UI
 * boolean; API enum is `"none" | "sector"`.
 *
 * `lookback` has a 5-day floor (matches existing page.tsx behaviour).
 */
function buildRequest(
  params: BacktestParams,
  meta: SpecMetadata,
): FactorBacktestRequest {
  const spec: FactorSpec = {
    name: meta.name,
    hypothesis: meta.hypothesis,
    expression: params.expression,
    operators_used: params.operatorsUsed,
    lookback: Math.max(params.lookback, 5),
    universe: params.universe,
    justification: meta.justification,
  };
  return {
    spec,
    direction: params.direction,
    top_pct: params.topPct / 100,
    bottom_pct: params.bottomPct / 100,
    transaction_cost_bps: params.transactionCostBps,
    mode: params.mode,
    neutralize: params.neutralize ? "sector" : "none",
    benchmark_ticker: params.benchmark,
  };
}

/**
 * `initParams` — an OPTIONAL lazy initializer the page passes to seed the form
 * from persisted localStorage on first render (so the initial params are the
 * stored ones, never DEFAULT_PARAMS-then-restore). Restoring synchronously in
 * useState avoids the race where a persist-on-change effect would clobber the
 * stored values with defaults before an effect-based restore could land. The
 * fn must be SSR-safe (return null on the server) so server + client agree.
 */
export function useBacktestSession(
  initParams?: () => Partial<BacktestParams> | null,
) {
  const [params, setParams] = useState<BacktestParams>(() => {
    const override = initParams?.() ?? null;
    return override ? { ...DEFAULT_PARAMS, ...override } : DEFAULT_PARAMS;
  });
  const [specMeta, setSpecMeta] = useState<SpecMetadata>(DEFAULT_SPEC_METADATA);
  const [runState, setRunState] = useState<RunState>({ kind: "idle" });
  const [recentRuns, setRecentRuns] = useState<Run[]>([]);
  const [baselineRunId, setBaselineRunId] = useState<string | null>(null);

  const runOnce = useCallback(async () => {
    setRunState({ kind: "running" });
    try {
      const request = buildRequest(params, specMeta);
      const resp = await runFactorBacktest(request);
      if (resp.error || !resp.data) {
        setRunState({
          kind: "error",
          message: resp.error ?? "Unknown error",
        });
        return;
      }
      const result = resp.data;
      const metrics = extractMetrics(result);
      const newRun: Run = {
        id: makeId(),
        ts: Date.now(),
        params,
        metrics,
        raw: result,
      };
      setRecentRuns((rs) => {
        const updated = [newRun, ...rs];
        return updated.slice(0, MAX_RECENT_RUNS);
      });
      // After eviction, if the pinned baseline was evicted, clear it so
      // the baselineRun memo doesn't silently fall through to recentRuns[1]
      // (a different run) and produce misleading delta arrows.
      setBaselineRunId((prev) => {
        if (prev === null) return null;
        const updated = [newRun, ...recentRuns].slice(0, MAX_RECENT_RUNS);
        return updated.some((r) => r.id === prev) ? prev : null;
      });
      setRunState({ kind: "ok", result });
    } catch (e) {
      setRunState({
        kind: "error",
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }, [params, specMeta, recentRuns]);

  const refillFromRun = useCallback(
    (runId: string) => {
      const r = recentRuns.find((r) => r.id === runId);
      if (r) setParams(r.params);
    },
    [recentRuns],
  );

  const togglePin = useCallback((runId: string) => {
    setBaselineRunId((prev) => (prev === runId ? null : runId));
  }, []);

  // currentRun reflects the most recent completed run regardless of in-flight
  // run state. During a re-run, runState transitions to "running" but
  // recentRuns[0] still holds the last completed run — keeping the VerdictBar
  // and Evidence panes populated until the new result lands. The `isRunning`
  // flag handles loading-overlay UX. On error, the last successful run stays
  // visible; the error is surfaced via runState.
  const currentRun = useMemo(
    () => recentRuns[0] ?? null,
    [recentRuns],
  );

  const baselineRun = useMemo(() => {
    if (baselineRunId) {
      return recentRuns.find((r) => r.id === baselineRunId) ?? null;
    }
    // Default baseline = the immediately prior run, if any.
    return recentRuns[1] ?? null;
  }, [baselineRunId, recentRuns]);

  const computeDelta = useCallback(
    (
      current: number | null,
      baseline: number | null,
      dir: MetricDirection,
    ): MetricDelta | null => {
      if (current === null || baseline === null) return null;
      const diff = current - baseline;
      const EPS = 1e-4;
      const arrow =
        Math.abs(diff) < EPS ? "flat" : diff > 0 ? "up" : "down";
      const betterThanBaseline = dir === "up_good" ? diff > 0 : diff < 0;
      return { arrow, diff, betterThanBaseline };
    },
    [],
  );

  const deltas: RunDeltas = useMemo(() => {
    if (!currentRun || !baselineRun || currentRun.id === baselineRun.id) {
      return {
        sharpe: null,
        maxDD: null,
        ic: null,
        turnover: null,
        annReturn: null,
      };
    }
    return {
      sharpe: computeDelta(
        currentRun.metrics.sharpe,
        baselineRun.metrics.sharpe,
        "up_good",
      ),
      // maxDD is a negative number; closer to 0 = larger = "up_good".
      maxDD: computeDelta(
        currentRun.metrics.maxDD,
        baselineRun.metrics.maxDD,
        "up_good",
      ),
      ic: computeDelta(
        currentRun.metrics.ic,
        baselineRun.metrics.ic,
        "up_good",
      ),
      turnover: computeDelta(
        currentRun.metrics.turnover,
        baselineRun.metrics.turnover,
        "down_good",
      ),
      annReturn: computeDelta(
        currentRun.metrics.annReturn,
        baselineRun.metrics.annReturn,
        "up_good",
      ),
    };
  }, [currentRun, baselineRun, computeDelta]);

  return {
    params,
    setParams,
    specMeta,
    setSpecMeta,
    runState,
    runOnce,
    recentRuns,
    refillFromRun,
    togglePin,
    baselineRunId,
    currentRun,
    baselineRun,
    deltas,
    thresholds: THRESHOLDS,
    isRunning: runState.kind === "running",
  };
}
