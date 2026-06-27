// Pre-backtest factor QC scorecard.
//
// Aggregates the smoke gate's structural gauges into one honest verdict. This is
// a STRUCTURAL pre-check, not a predictive verdict: the smoke IC is computed
// against a synthetic random-return panel, so it is near-zero noise rather than a
// quality signal — real predictive power comes from the backtest. The scorecard
// therefore grades only the three structural dimensions the smoke gate can
// actually measure on synthetic data:
//
//   - Integrity  (degenerate): the only BLOCKING check — a (near-)constant factor
//                carries zero cross-sectional signal and disables backtest/save.
//   - Stability  (high_turnover): advisory — a change/reversal expression churns
//                its book and is eaten by transaction costs.
//   - Robustness (low_robustness): advisory — ranking collapses under input noise,
//                a sign of overfitting that won't hold out-of-sample.
//
// Verdict precedence: block > caution > pass.

import type { SmokeReport } from "./types";

export type QcStatus = "pass" | "caution" | "block";

export interface SmokeScorecard {
  readonly verdict: QcStatus;
  readonly integrity: QcStatus;
  readonly stability: QcStatus;
  readonly robustness: QcStatus;
}

export function buildSmokeScorecard(data: SmokeReport): SmokeScorecard {
  // Optional flags are treated as "not tripped" so an in-flight response from
  // before a gauge shipped degrades to pass rather than throwing.
  const integrity: QcStatus = data.degenerate ? "block" : "pass";
  const stability: QcStatus = data.high_turnover ? "caution" : "pass";
  const robustness: QcStatus = data.low_robustness ? "caution" : "pass";

  const verdict: QcStatus =
    integrity === "block"
      ? "block"
      : stability === "caution" || robustness === "caution"
        ? "caution"
        : "pass";

  return { verdict, integrity, stability, robustness };
}
