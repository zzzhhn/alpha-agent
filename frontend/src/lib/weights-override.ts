// frontend/src/lib/weights-override.ts
// Client-side PERSONAL weight override (serenity seam #2 follow-on).
//
// The WeightsEditor (settings) saves a {signal: weight} map to localStorage.
// This module recomputes a RatingCard's composite + rating + per-signal
// contributions from its breakdown using that map, mirroring the backend
// fusion combine() + map_to_tier() EXACTLY so that an override equal to the
// backend default reproduces the backend composite (parity).
//
// Backend parity (alpha_agent/fusion/combine.py + rating.py):
//   drop a signal when confidence == 0 OR weight == 0 OR z is non-finite;
//   renormalize weights across the surviving signals;
//   composite = sum(z * weight_effective);
//   tier: >1.5 BUY, >0.5 OW, >=-0.5 HOLD, >=-1.5 UW, else SELL.
//
// Scope: this is a per-browser what-if view. It never writes back to the
// backend and never changes which tickers the picks endpoint selects.
import type { BreakdownEntry, RatingCard } from "@/lib/api/picks";

export const WEIGHTS_KEY = "alpha-agent:weights";

// Canonical default weights — MUST mirror alpha_agent/fusion/weights.py
// DEFAULT_WEIGHTS. Display-only signals stay at 0; supply_chain is the
// exploratory serenity bottleneck tilt (0.05). The WeightsEditor imports
// this so the editor and the reweight engine never drift.
export const DEFAULT_WEIGHTS: Record<string, number> = {
  factor: 0.3,
  // mirror backend: technicals trimmed 0.20 -> 0.15 to fund rsrs (price-action
  // bucket total unchanged at 0.20); see alpha_agent/fusion/weights.py.
  technicals: 0.15,
  rsrs: 0.05,
  analyst: 0.1,
  earnings: 0.1,
  news: 0.1,
  insider: 0.05,
  options: 0.05,
  premarket: 0.05,
  macro: 0.05,
  calendar: 0.0,
  political_impact: 0.0,
  geopolitical_impact: 0.0,
  supply_chain: 0.05,
};

// Active-policy guardrail caps (council #5). MUST mirror the active WeightPolicy
// caps in alpha_agent/fusion/policy.py (currently static_v2: technicals 0.10).
// A capped signal's effective weight is scaled down to the cap and the freed
// weight is NOT reallocated (goes to neutral), so the personal reweight matches
// the production composite. Empty entry = uncapped.
export const ACTIVE_CAPS: Record<string, number> = {
  technicals: 0.1,
};

type Tier = RatingCard["rating"];

function isFiniteNumber(x: unknown): x is number {
  return typeof x === "number" && Number.isFinite(x);
}

// Per-row "data-backed" confidence. The backend sends `confidence` on each
// breakdown row (used by combine's drop logic) even though older type
// definitions omitted it; when it is absent (legacy rows) fall back to
// z-finiteness so a real signal is never silently dropped.
function rowConfidence(e: BreakdownEntry): number {
  const c = (e as { confidence?: number | null }).confidence;
  if (typeof c === "number") return c;
  return isFiniteNumber(e.z) ? 1 : 0;
}

// Mirror of map_to_tier (alpha_agent/fusion/rating.py) DEFAULT thresholds.
// The backend allows an ALPHA_TIER_THRESHOLDS env override; this mirrors the
// shipped defaults (buy 1.5 / ow 0.5 / hold -0.5 / uw -1.5).
export function mapToTier(composite: number | null): Tier {
  if (composite === null || !Number.isFinite(composite)) return "HOLD";
  if (composite > 1.5) return "BUY";
  if (composite > 0.5) return "OW";
  if (composite >= -0.5) return "HOLD";
  if (composite >= -1.5) return "UW";
  return "SELL";
}

// Read + validate the saved override. Returns null when absent or invalid
// (caller then uses the backend card unchanged — never a silent wrong
// reweight). Rejects non-numeric / negative / NaN values wholesale.
export function readWeightsOverride(): Record<string, number> | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(WEIGHTS_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const out: Record<string, number> = {};
    for (const [k, v] of Object.entries(parsed)) {
      if (typeof v !== "number" || !Number.isFinite(v) || v < 0) return null;
      out[k] = v;
    }
    return Object.keys(out).length > 0 ? out : null;
  } catch {
    return null;
  }
}

// The always-expected core signals used for coverage-aware fusion. MUST mirror
// alpha_agent/fusion/policy.py _CORE_SIGNALS. Sparse signals (insider, options,
// premarket, supply_chain) and weight-0 display-only signals are excluded so
// their structural absence does not penalize conviction.
const CORE_SIGNALS = new Set([
  "factor",
  "technicals",
  "analyst",
  "earnings",
  "news",
  "macro",
]);

// Recompute breakdown weight / weight_effective / contribution under custom
// weights, mirroring combine()'s drop + renormalize logic exactly, then apply
// the coverage-aware damping (council #2): composite is scaled by
// sqrt(core coverage) so cards missing core signals carry less conviction.
// Returns the rewritten rows, the resulting composite, and the coverage.
export function applyWeightsToBreakdown(
  breakdown: BreakdownEntry[],
  weights: Record<string, number>,
): { breakdown: BreakdownEntry[]; composite: number; coverage: number } {
  const dropped = new Set<string>();
  for (const e of breakdown) {
    const w = weights[e.signal] ?? 0;
    if (rowConfidence(e) === 0) dropped.add(e.signal);
    if (w === 0) dropped.add(e.signal);
    if (!isFiniteNumber(e.z)) dropped.add(e.signal);
  }
  let total = 0;
  for (const [k, v] of Object.entries(weights)) {
    if (!dropped.has(k) && v > 0) total += v;
  }
  let composite = 0;
  const out = breakdown.map((e) => {
    const wOrig = weights[e.signal] ?? 0;
    let wEff =
      total > 0 && !dropped.has(e.signal) && wOrig > 0 ? wOrig / total : 0;
    // Apply guardrail cap (council #5): scale the effective weight down to the
    // cap without reallocating the freed weight (mirrors backend _apply_caps).
    const cap = ACTIVE_CAPS[e.signal];
    if (cap !== undefined && wOrig > 0 && cap < wOrig) wEff *= cap / wOrig;
    const contribution = wEff === 0 ? 0 : (e.z ?? 0) * wEff;
    composite += contribution;
    return { ...e, weight: wOrig, weight_effective: wEff, contribution };
  });
  // Coverage-aware damping over the core signal set (mirrors backend
  // _core_coverage). present core weight / total core weight, weight>0.
  let coreTotal = 0;
  let corePresent = 0;
  for (const e of breakdown) {
    if (!CORE_SIGNALS.has(e.signal)) continue;
    const w = weights[e.signal] ?? 0;
    if (w <= 0) continue;
    coreTotal += w;
    if (!dropped.has(e.signal)) corePresent += w;
  }
  const coverage = coreTotal > 0 ? corePresent / coreTotal : 1.0;
  composite *= Math.sqrt(coverage);
  return { breakdown: out, composite, coverage };
}

// Recompute a card's composite_score + rating + breakdown under custom
// weights. Pure: returns a new card, never mutates the input.
export function applyWeightsToCard(
  card: RatingCard,
  weights: Record<string, number>,
): RatingCard {
  const { breakdown, composite } = applyWeightsToBreakdown(
    card.breakdown,
    weights,
  );
  return {
    ...card,
    breakdown,
    composite_score: composite,
    rating: mapToTier(composite),
  };
}
