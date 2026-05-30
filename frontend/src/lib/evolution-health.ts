// Pure assessment logic for the self-evolution health strip. Runs on the
// server (page.tsx) against the already-fetched evolution data and emits
// plain serializable verdicts the client strip formats with i18n.
//
// The page's real intent (per the user) is: "is the agent's self-evolution
// effective AND trustworthy — approve or reject?" The discrete approve/
// reject surface (methodology proposals) is often dormant, but the answer
// to "effective & trustworthy right now" is computable from the evidence
// that is always present: calibration (trustworthy?), IC trend (effective?),
// adaptive-weight activity (what self-regulation is doing), and the pending
// count (anything awaiting you?).
import type {
  EvolutionCalibration,
  EvolutionWeightsResponse,
  IcTrendResponse,
  ProposalsResponse,
} from "./api/evolution";

// 'action' = needs the user (pending decisions). 'warn' = a real concern.
// 'good' = healthy. 'neutral' = nothing notable. 'na' = data unavailable.
export type HealthTone = "good" | "warn" | "action" | "neutral" | "na";

export interface SubVerdict {
  tone: HealthTone;
  // Numeric/string facts the client formats into a localized readout.
  facts: Record<string, number | string | boolean | null>;
}

export interface EvolutionHealth {
  calibration: SubVerdict;
  ic: SubVerdict;
  weights: SubVerdict;
  proposals: SubVerdict;
}

// Brier baselines: 0 perfect, 0.25 = no-skill (always predict 0.5 at a 50%
// base rate), > 0.25 = worse than guessing. Thresholds anchor to that line.
const BRIER_GOOD = 0.18;
const BRIER_NOSKILL = 0.25;
// High-confidence buckets overconfident if predicted exceeds actual by this.
const OVERCONF_MARGIN = 0.08;

function meanBrier(cal: EvolutionCalibration): number | null {
  const valid = cal.buckets.filter((b) => b.brier !== null && b.n > 0);
  if (valid.length === 0) return null;
  const totalN = valid.reduce((s, b) => s + b.n, 0);
  const weighted = valid.reduce((s, b) => s + (b.brier as number) * b.n, 0);
  return totalN > 0 ? weighted / totalN : null;
}

function overconfidence(cal: EvolutionCalibration): number | null {
  // Mean (predicted - actual) over high-confidence buckets. Positive => the
  // system claims more confidence than its hit rate earns.
  const high = cal.buckets.filter(
    (b) => b.n > 0 && b.hit_rate !== null && (b.lo + b.hi) / 2 >= 0.6,
  );
  if (high.length === 0) return null;
  const gaps = high.map((b) => (b.lo + b.hi) / 2 - (b.hit_rate as number));
  return gaps.reduce((s, g) => s + g, 0) / gaps.length;
}

export function assessCalibration(
  cal: EvolutionCalibration | null,
): SubVerdict {
  if (!cal) return { tone: "na", facts: {} };
  if (!cal.applied) {
    return { tone: "neutral", facts: { applied: false, nPairs: cal.n_pairs } };
  }
  const brier = meanBrier(cal);
  const overconf = overconfidence(cal);
  const isOverconf = overconf !== null && overconf > OVERCONF_MARGIN;
  const worseThanGuess = brier !== null && brier >= BRIER_NOSKILL;
  const wellCalibrated = brier !== null && brier < BRIER_GOOD && !isOverconf;

  const tone: HealthTone =
    worseThanGuess || isOverconf ? "warn" : wellCalibrated ? "good" : "neutral";

  return {
    tone,
    facts: {
      applied: true,
      brier: brier !== null ? Number(brier.toFixed(4)) : null,
      overconfident: isOverconf,
      worseThanGuess,
      nPairs: cal.n_pairs,
    },
  };
}

function latestIc(points: { computed_at: string; ic: number }[]): number | null {
  if (points.length === 0) return null;
  // Defensive: don't assume input order — take the chronologically last.
  const sorted = [...points].sort((a, b) =>
    a.computed_at < b.computed_at ? -1 : 1,
  );
  return sorted[sorted.length - 1].ic;
}

export function assessIc(icTrend: IcTrendResponse | null): SubVerdict {
  if (!icTrend || icTrend.series.length === 0) return { tone: "na", facts: {} };
  let pos = 0;
  let total = 0;
  let strongestName = "";
  let strongestIc = -Infinity;
  for (const s of icTrend.series) {
    const ic = latestIc(s.points);
    if (ic === null) continue;
    total += 1;
    if (ic > 0) pos += 1;
    if (ic > strongestIc) {
      strongestIc = ic;
      strongestName = s.signal_name;
    }
  }
  if (total === 0) return { tone: "na", facts: {} };
  const ratio = pos / total;
  const tone: HealthTone =
    ratio >= 0.6 ? "good" : ratio < 0.4 ? "warn" : "neutral";
  return {
    tone,
    facts: {
      pos,
      total,
      strongestName,
      strongestIc: strongestIc !== -Infinity ? Number(strongestIc.toFixed(4)) : null,
    },
  };
}

export function assessWeights(
  weights: EvolutionWeightsResponse | null,
): SubVerdict {
  if (!weights || weights.weights.length === 0) return { tone: "na", facts: {} };
  const names = new Set<string>();
  let shadow = 0;
  let degrading = 0;
  let nearPromotion = 0;
  for (const w of weights.weights) {
    names.add(w.signal_name);
    if (w.status === "shadow") shadow += 1;
    if (w.consecutive_bad_windows > 0) degrading += 1;
    if (w.shadow_streak >= 4) nearPromotion += 1;
  }
  // Degrading live signals are the only real concern here; otherwise the
  // shadow accumulation is the system quietly doing its job.
  const tone: HealthTone = degrading > 0 ? "warn" : "neutral";
  return {
    tone,
    facts: {
      signals: names.size,
      shadow,
      degrading,
      nearPromotion,
    },
  };
}

export function assessProposals(
  proposals: ProposalsResponse | null,
): SubVerdict {
  if (!proposals) return { tone: "na", facts: {} };
  const pending = proposals.proposals.filter(
    (p) => p.status === "pending",
  ).length;
  // Pending proposals are the one thing that actively needs the user.
  const tone: HealthTone = pending > 0 ? "action" : "neutral";
  return { tone, facts: { pending, total: proposals.proposals.length } };
}

export function assessEvolutionHealth(data: {
  icTrend: IcTrendResponse | null;
  calibration: EvolutionCalibration | null;
  weights: EvolutionWeightsResponse | null;
  proposals: ProposalsResponse | null;
}): EvolutionHealth {
  return {
    calibration: assessCalibration(data.calibration),
    ic: assessIc(data.icTrend),
    weights: assessWeights(data.weights),
    proposals: assessProposals(data.proposals),
  };
}
