import type { RunMetrics } from "@/components/backtest/types";

export interface BacktestGateThresholds {
  readonly sharpe: number;
  readonly maxDD: number;
  readonly ic: number;
  readonly turnover: number;
  readonly annReturn: number;
}

export type GateStatus = "pass" | "fail" | "missing";

export interface BacktestGate {
  readonly key: keyof RunMetrics;
  readonly status: GateStatus;
  readonly value: number | null;
  readonly threshold: number;
  readonly lowerIsBetter: boolean;
}

export function evaluateBacktestGates(
  metrics: RunMetrics,
  thresholds: BacktestGateThresholds,
): BacktestGate[] {
  const definitions: Array<{
    key: keyof RunMetrics;
    threshold: number;
    lowerIsBetter: boolean;
  }> = [
    { key: "sharpe", threshold: thresholds.sharpe, lowerIsBetter: false },
    { key: "maxDD", threshold: thresholds.maxDD, lowerIsBetter: false },
    { key: "ic", threshold: thresholds.ic, lowerIsBetter: false },
    { key: "turnover", threshold: thresholds.turnover, lowerIsBetter: true },
    { key: "annReturn", threshold: thresholds.annReturn, lowerIsBetter: false },
  ];
  return definitions.map((definition) => {
    const value = metrics[definition.key];
    const status: GateStatus = value === null
      ? "missing"
      : definition.lowerIsBetter
        ? value <= definition.threshold ? "pass" : "fail"
        : value >= definition.threshold ? "pass" : "fail";
    return { ...definition, value, status };
  });
}
