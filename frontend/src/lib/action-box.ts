// frontend/src/lib/action-box.ts
/**
 * Action box derivation from a RatingCard breakdown + price snapshot.
 * Spec §3.3: entry = current ± ATR×0.5, stop = current − ATR×1.5,
 * target = min(analyst.targetMeanPrice, max(180d) × 1.05).
 *
 * The frontend gets ATR from the technicals signal's raw dict; current price
 * from yfinance via a lightweight side-fetch (M3 backlog: bake into
 * /api/stock response). If ATR missing, returns nulls and UI shows "—".
 */
export interface ActionBox {
  entryLow: number | null;
  entryHigh: number | null;
  entryMid: number | null;
  stop: number | null;
  target: number | null;
  rrRatio: number | null;
  positionPct: number | null;
}

interface DeriveInput {
  currentPrice: number | null;
  atr14: number | null;
  analystTarget: number | null;
  high180d: number | null;
  confidence: number;
  maxPositionPct?: number; // user setting; default 7
}

export function deriveActionBox(input: DeriveInput): ActionBox {
  const { currentPrice: px, atr14, analystTarget, high180d, confidence } = input;
  const maxPos = input.maxPositionPct ?? 7;
  if (px == null || atr14 == null) {
    return {
      entryLow: null, entryHigh: null, entryMid: null,
      stop: null, target: null, rrRatio: null,
      positionPct: maxPos * confidence,
    };
  }
  const entryLow = +(px - atr14 * 0.5).toFixed(2);
  const entryHigh = +(px + atr14 * 0.5).toFixed(2);
  const entryMid = px;
  const stop = +(px - atr14 * 1.5).toFixed(2);
  const target = ((): number | null => {
    if (analystTarget == null && high180d == null) return null;
    const candidates = [
      analystTarget,
      high180d != null ? high180d * 1.05 : null,
    ].filter((v): v is number => v != null);
    return candidates.length === 0 ? null : Math.min(...candidates);
  })();
  const rrRatio =
    target == null ? null : +((target - entryMid) / (entryMid - stop)).toFixed(2);
  return {
    entryLow, entryHigh, entryMid, stop, target, rrRatio,
    positionPct: +(maxPos * confidence).toFixed(2),
  };
}
