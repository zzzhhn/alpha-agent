// frontend/src/lib/picks-mode.ts
// Helpers for the SHORT/LONG factor toggle that flows through every UI
// component consuming a RatingCard.breakdown.
//
// Backend persists three numbers on factor.raw: z (active mode value),
// z_short (12d/60d), z_long (252d/126d). Picks endpoint already does
// server-side re-rank when ?mode=long is requested — composite + rating
// already reflect the long-mode swap. The frontend hook here only matters
// for the *display* of factor.z + factor.contribution in single-card
// components (AttributionTable, AttributionRadar) since they don't refetch
// on toggle (they receive the card from the parent fetch).
import type { BreakdownEntry, FactorMode, RatingCard, FactorRaw } from "@/lib/api/picks";

interface MaybeFactorRaw {
  z?: number;
  z_short?: number;
  z_long?: number;
  fundamentals?: FactorRaw["fundamentals"];
}

/**
 * Return a new BreakdownEntry[] with the factor row's `z` + `contribution`
 * swapped to the requested mode's value. Non-factor rows pass through
 * unchanged. If the factor row lacks `z_long` (legacy / partial data),
 * fall back to z_short or the existing z so the UI never goes blank.
 */
export function applyFactorMode(
  breakdown: BreakdownEntry[],
  mode: FactorMode,
): BreakdownEntry[] {
  return breakdown.map((entry) => {
    if (entry.signal !== "factor") return entry;
    const raw = entry.raw as MaybeFactorRaw | null | undefined;
    if (!raw || typeof raw !== "object") return entry;
    const zShort = typeof raw.z_short === "number" ? raw.z_short : entry.z ?? 0;
    const zLong = typeof raw.z_long === "number" ? raw.z_long : null;
    const newZ = mode === "long" && zLong !== null ? zLong : zShort;
    const wEff = entry.weight_effective ?? 0;
    return {
      ...entry,
      z: newZ,
      contribution: wEff * newZ,
      raw: { ...raw, z: newZ },
    };
  });
}

/**
 * Return a card with composite_score adjusted for the active mode using the
 * stored z_short / z_long deltas. Used by single-card views that don't
 * refetch on toggle. Picks endpoint already does this server-side.
 */
export function applyFactorModeToCard(
  card: RatingCard,
  mode: FactorMode,
): RatingCard {
  const factor = card.breakdown.find((b) => b.signal === "factor");
  if (!factor) return card;
  const raw = factor.raw as MaybeFactorRaw | null | undefined;
  if (!raw || typeof raw !== "object") return card;
  const zShort = typeof raw.z_short === "number" ? raw.z_short : factor.z ?? 0;
  const zLong = typeof raw.z_long === "number" ? raw.z_long : null;
  const oldZ = factor.z ?? 0;
  const newZ = mode === "long" && zLong !== null ? zLong : zShort;
  const wEff = factor.weight_effective ?? 0;
  const deltaComposite = wEff * (newZ - oldZ);
  return {
    ...card,
    breakdown: applyFactorMode(card.breakdown, mode),
    composite_score: (card.composite_score ?? 0) + deltaComposite,
  };
}
