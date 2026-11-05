import type { AlphaValidationParams } from "./useAlphaChain";

/** Shared Save/Compare contract, always called with the submitted snapshot. */
export function alphaRunConfig(validation: AlphaValidationParams) {
  return {
    direction: validation.direction,
    neutralize: validation.neutralize,
    benchmarkTicker: validation.benchmarkTicker,
    mode: "static" as const,
    topPct: validation.topPct / 100,
    bottomPct: validation.topPct / 100,
    transactionCostBps: validation.transactionCostBps,
  };
}

export function sameAlphaValidation(a: AlphaValidationParams, b: AlphaValidationParams) {
  return a.direction === b.direction && a.topPct === b.topPct
    && a.transactionCostBps === b.transactionCostBps && a.neutralize === b.neutralize
    && a.benchmarkTicker === b.benchmarkTicker;
}
