// frontend/src/lib/thesis.ts
import type { RatingCard, BreakdownEntry } from "./api/picks";

export interface Thesis { bull: string[]; bear: string[]; }

const _signalLabel = (name: string) => name.toUpperCase();

export function renderLeanThesis(card: RatingCard): Thesis {
  const lookup: Record<string, BreakdownEntry> = {};
  for (const b of card.breakdown) lookup[b.signal] = b;

  const bull = card.top_drivers.map((d) => {
    const z = lookup[d]?.z ?? 0;
    return `${_signalLabel(d)} signal contributing positively (z=${z >= 0 ? "+" : ""}${z.toFixed(2)})`;
  });
  const bear = card.top_drags.map((d) => {
    const z = lookup[d]?.z ?? 0;
    return `${_signalLabel(d)} signal pulling negatively (z=${z >= 0 ? "+" : ""}${z.toFixed(2)})`;
  });
  return {
    bull: bull.length ? bull : ["No strongly positive signals detected"],
    bear: bear.length ? bear : ["No strongly negative signals detected"],
  };
}
