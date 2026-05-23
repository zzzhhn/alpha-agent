"use client";

import { useCallback, useMemo, useState } from "react";
import { runFactorBacktest, translateHypothesis } from "@/lib/api";
import type { FactorUniverse } from "@/lib/types";
import type {
  ChainPaneStates,
  ChainState,
  ThresholdEval,
  VerdictMetrics,
} from "./types";

// SmokeReport uses ic_spearman (not ic_mean). Threshold set at 0.02 as
// a reasonable minimum for cross-sectional information.
const IC_OK = 0.02;
const SHARPE_OK = 1.0;
const SHARPE_WARN = 0.5;
const MAXDD_OK = -0.15;
const MAXDD_BAD = -0.25;

function evalThresholds(m: VerdictMetrics): ThresholdEval {
  return {
    ic: m.ic === null ? null : {
      status: m.ic >= IC_OK ? "ok" : m.ic > 0 ? "warn" : "bad",
      threshold: "threshold >=0.02 considered useful",
    },
    sharpe: m.sharpe === null ? null : {
      status: m.sharpe >= SHARPE_OK ? "ok" : m.sharpe >= SHARPE_WARN ? "warn" : "bad",
      threshold: "threshold >=1.0 considered viable",
    },
    maxDrawdown: m.maxDrawdown === null ? null : {
      status: m.maxDrawdown >= MAXDD_OK ? "ok" : m.maxDrawdown >= MAXDD_BAD ? "warn" : "bad",
      threshold: "threshold >=-15% considered acceptable",
    },
  };
}

function paneStates(s: ChainState): ChainPaneStates {
  switch (s.kind) {
    case "idle":            return { spec: "waiting", smoke: "waiting", backtest: "waiting" };
    case "translating":     return { spec: "loading", smoke: "loading", backtest: "waiting" };
    case "backtesting":     return { spec: "ok",      smoke: "ok",      backtest: "loading" };
    case "done":            return { spec: "ok",      smoke: "ok",      backtest: "ok" };
    case "translate_error": return { spec: "error",   smoke: "waiting", backtest: "waiting" };
    case "backtest_error":  return { spec: "ok",      smoke: "ok",      backtest: "error" };
  }
}

function deriveMetrics(s: ChainState): VerdictMetrics {
  // IC comes from SmokeReport.ic_spearman (the only IC field on SmokeReport).
  // Backtest metrics come from test_metrics on FactorBacktestResponse
  // (the out-of-sample slice; FactorSplitMetrics has sharpe and max_drawdown).
  const hasTranslate =
    s.kind === "backtesting" || s.kind === "done" || s.kind === "backtest_error";
  const ic = hasTranslate ? (s.translate.smoke.ic_spearman ?? null) : null;

  const bt = s.kind === "done" ? s.backtest : null;
  return {
    ic,
    sharpe: bt?.test_metrics?.sharpe ?? null,
    maxDrawdown: bt?.test_metrics?.max_drawdown ?? null,
  };
}

export function useAlphaChain() {
  const [state, setState] = useState<ChainState>({ kind: "idle" });

  const start = useCallback(async (text: string, universe: FactorUniverse) => {
    setState({ kind: "translating" });

    let translate;
    try {
      const resp = await translateHypothesis({ text, universe });
      if (resp.error || !resp.data) {
        setState({ kind: "translate_error", message: resp.error ?? "Unknown error" });
        return;
      }
      translate = resp.data;
    } catch (e) {
      setState({
        kind: "translate_error",
        message: e instanceof Error ? e.message : String(e),
      });
      return;
    }

    // Block degenerate factors from reaching the backtest engine, consistent
    // with existing page.tsx behaviour.
    if (translate.smoke.degenerate) {
      setState({
        kind: "translate_error",
        message: "Factor has zero cross-sectional variance (degenerate). Backtest blocked.",
      });
      return;
    }

    setState({ kind: "backtesting", translate });

    try {
      // runFactorBacktest takes { spec: FactorSpec, direction?, ... }.
      // Passing spec directly (which already contains universe + expression)
      // matches the existing page.tsx onBacktest pattern.
      const resp = await runFactorBacktest({ spec: translate.spec, direction: "long_short" });
      if (resp.error || !resp.data) {
        setState({
          kind: "backtest_error",
          translate,
          message: resp.error ?? "Unknown error",
        });
        return;
      }
      setState({ kind: "done", translate, backtest: resp.data });
    } catch (e) {
      setState({
        kind: "backtest_error",
        translate,
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }, []);

  const retryBacktest = useCallback(async () => {
    if (state.kind !== "backtest_error" && state.kind !== "done") return;
    const translate = state.translate;

    setState({ kind: "backtesting", translate });

    try {
      const resp = await runFactorBacktest({ spec: translate.spec, direction: "long_short" });
      if (resp.error || !resp.data) {
        setState({
          kind: "backtest_error",
          translate,
          message: resp.error ?? "Unknown error",
        });
        return;
      }
      setState({ kind: "done", translate, backtest: resp.data });
    } catch (e) {
      setState({
        kind: "backtest_error",
        translate,
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }, [state]);

  const reset = useCallback(() => setState({ kind: "idle" }), []);

  // Derive all computed values inside useMemo so `state` is the only
  // dependency that drives re-computation (rerender-derived-state,
  // rerender-dependencies). Extracting `m` outside would produce a new
  // object reference on every render, defeating the memo.
  return useMemo(() => {
    const m = deriveMetrics(state);
    return {
      state,
      panes: paneStates(state),
      metrics: m,
      thresholds: evalThresholds(m),
      start,
      retryBacktest,
      reset,
      isLoading: state.kind === "translating" || state.kind === "backtesting",
    };
  }, [state, start, retryBacktest, reset]);
}
