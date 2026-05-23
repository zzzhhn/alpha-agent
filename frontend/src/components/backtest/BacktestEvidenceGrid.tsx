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

import { EquityCurvePane } from "./EquityCurvePane";
import { DrawdownPane } from "./DrawdownPane";
import { WalkforwardPane } from "./WalkforwardPane";
import type { Run, RunState } from "./types";

interface Props {
  readonly runState: RunState;
  readonly currentRun: Run | null;
}

export function BacktestEvidenceGrid({ runState, currentRun }: Props) {
  return (
    <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
      <EquityCurvePane runState={runState} currentRun={currentRun} />
      <DrawdownPane runState={runState} currentRun={currentRun} />
      <WalkforwardPane runState={runState} currentRun={currentRun} />
    </div>
  );
}
