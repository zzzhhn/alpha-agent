// Factor quality tier, derived from the backtest's risk-attribution stats.
//
// Canonical thresholds — identical to the ones the alpha examples are
// classified by (see components/alpha/FactorExamples.tsx):
//
//   PURE ALPHA    α-p < 0.05 AND |β| < 0.30   (significant alpha, market-neutral)
//   LEVERED ALPHA α-p < 0.05                   (significant alpha, but market-exposed)
//   MARGINAL      α-p < 0.10                   (suggestive, not confirmed)
//   NOISE         otherwise                    (directional but not statistically real)
//   —             α-p unknown                  (can't classify)
//
// Deriving the tier from the live result (not a hand-label) keeps the report's
// VERDICT banner honest: it says exactly what the strict RISK.ATTRIBUTION test
// found, with no fabricated conclusion.

export type FactorTierTone = "pos" | "info" | "warn" | "muted";

export interface FactorTier {
  readonly label: "PURE ALPHA" | "LEVERED ALPHA" | "MARGINAL" | "NOISE" | "—";
  readonly tone: FactorTierTone;
}

const PURE_BETA_MAX = 0.3;
const SIGNIFICANT_P = 0.05;
const MARGINAL_P = 0.1;

export function classifyFactorTier(
  alphaPvalue: number | null | undefined,
  betaMarket: number | null | undefined,
): FactorTier {
  if (alphaPvalue == null || !Number.isFinite(alphaPvalue)) {
    return { label: "—", tone: "muted" };
  }
  if (alphaPvalue < SIGNIFICANT_P) {
    const betaKnown = betaMarket != null && Number.isFinite(betaMarket);
    if (betaKnown && Math.abs(betaMarket as number) < PURE_BETA_MAX) {
      return { label: "PURE ALPHA", tone: "pos" };
    }
    return { label: "LEVERED ALPHA", tone: "info" };
  }
  if (alphaPvalue < MARGINAL_P) {
    return { label: "MARGINAL", tone: "warn" };
  }
  return { label: "NOISE", tone: "muted" };
}
