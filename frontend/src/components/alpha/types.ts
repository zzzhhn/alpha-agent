import type {
  FactorBacktestResponse,
  HypothesisTranslateResponse,
} from "@/lib/types";

export type ChainState =
  | { kind: "idle" }
  | { kind: "translating" }
  | { kind: "backtesting"; translate: HypothesisTranslateResponse }
  | { kind: "done"; translate: HypothesisTranslateResponse; backtest: FactorBacktestResponse }
  | { kind: "translate_error"; message: string }
  | { kind: "backtest_error"; translate: HypothesisTranslateResponse; message: string };

export type PaneState = "waiting" | "loading" | "ok" | "error";

export interface ChainPaneStates {
  spec: PaneState;
  smoke: PaneState;
  backtest: PaneState;
}

export interface VerdictMetrics {
  ic: number | null;
  sharpe: number | null;
  maxDrawdown: number | null;
}

export type ThresholdStatus = "ok" | "warn" | "bad";

export interface ThresholdMark {
  status: ThresholdStatus;
  threshold: string;
}

export interface ThresholdEval {
  ic: ThresholdMark | null;
  sharpe: ThresholdMark | null;
  maxDrawdown: ThresholdMark | null;
}
