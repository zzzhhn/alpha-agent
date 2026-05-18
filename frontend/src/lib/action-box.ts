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

/**
 * Resolve ATR to a dollar value.
 * Backend technicals.py historically stored `atr` as a ratio
 * (raw_atr / close), since the z-score uses tanh(ratio*50). Treating that
 * ratio as a dollar amount made entry/stop differ by cents instead of $-units
 * — surfaced in production on 2026-05-18. Backend now emits `atr_dollar`
 * directly; this helper handles both shapes for backward compat:
 *   - if atr_dollar provided, use it
 *   - if atr14 looks like a ratio (< 1), upscale by current price
 *   - otherwise treat atr14 as already-dollar
 */
function resolveAtrDollar(
  atr14: number | null,
  atrDollar: number | null | undefined,
  currentPrice: number,
): number | null {
  if (atrDollar != null && atrDollar > 0) return atrDollar;
  if (atr14 == null) return null;
  if (atr14 < 1) return atr14 * currentPrice;
  return atr14;
}

export function deriveActionBox(
  input: DeriveInput & { atrDollar?: number | null },
): ActionBox {
  const { currentPrice: px, atr14, analystTarget, high180d, confidence } = input;
  const maxPos = input.maxPositionPct ?? 7;
  if (px == null) {
    return {
      entryLow: null, entryHigh: null, entryMid: null,
      stop: null, target: null, rrRatio: null,
      positionPct: maxPos * confidence,
    };
  }
  const atr = resolveAtrDollar(atr14, input.atrDollar ?? null, px);
  if (atr == null) {
    return {
      entryLow: null, entryHigh: null, entryMid: null,
      stop: null, target: null, rrRatio: null,
      positionPct: maxPos * confidence,
    };
  }
  const entryLow = +(px - atr * 0.5).toFixed(2);
  const entryHigh = +(px + atr * 0.5).toFixed(2);
  const entryMid = px;
  const stop = +(px - atr * 1.5).toFixed(2);
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
