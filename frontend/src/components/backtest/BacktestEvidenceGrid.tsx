"use client";

/**
 * BacktestEvidenceGrid — default-evidence row for /backtest redesign (T5).
 *
 * Three side-by-side panes (Equity / Drawdown / Walkforward) that always
 * render under the verdict bar. Each pane owns its own 4-state lifecycle
 * (waiting / running / ok / error) and pulls its data slice off the
 * single shared `currentRun`.
 *
 * Layout: stacked on narrow viewports, 3-up on `lg:` and above.
 */

import { WalkforwardPane } from "./WalkforwardPane";
import { BacktestValidationGate } from "./BacktestValidationGate";
import { TmEquityDrawdownChart } from "./TmEquityDrawdownChart";
import type { BacktestGateThresholds } from "@/lib/backtest-gates";
import type { Run, RunState } from "./types";

interface Props {
  readonly runState: RunState;
  readonly currentRun: Run | null;
  readonly thresholds: BacktestGateThresholds;
}

export function BacktestEvidenceGrid({ runState, currentRun, thresholds }: Props) {
  return (
    <div className="grid grid-cols-[minmax(680px,2fr)_minmax(360px,1fr)] gap-4">
      <div className="min-w-0">
        {currentRun ? <TmEquityDrawdownChart result={currentRun.raw} height={460} /> : null}
      </div>
      <div className="flex min-w-0 flex-col gap-4">
        <BacktestValidationGate currentRun={currentRun} thresholds={thresholds} />
        <WalkforwardPane runState={runState} currentRun={currentRun} />
      </div>
    </div>
  );
}
