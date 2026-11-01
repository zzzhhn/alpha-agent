import type { RatingCard } from "./api/picks";
import type { Locale } from "./i18n";

// Descriptive next-day evidence, not a forecast probability or holding horizon.
export const CONSISTENCY_MIN = { d5: 3, m1: 10, y1: 120, hist: 5 } as const;

export function consistencyEvidence(
  card: Pick<RatingCard, "consistency" | "consistency_n">,
  window: keyof typeof CONSISTENCY_MIN,
  locale: Locale,
) {
  const rawN = card.consistency_n?.[window];
  const n = typeof rawN === "number" && Number.isInteger(rawN) && rawN >= 0 ? rawN : null;
  const min = CONSISTENCY_MIN[window];
  const rate = card.consistency?.[window];
  const validRate = typeof rate === "number" && Number.isFinite(rate) && rate >= 0 && rate <= 1;
  const pct = validRate && (n === null || n >= min) ? Math.round(rate * 100) : null;
  const sampleLabel = n === null
    ? "n=?"
    : pct === null ? `n=${n}/${min}` : `n=${n}`;
  const reason = n === null
    ? (locale === "zh" ? "旧快照未记录样本数，不能据此判断统计可靠性。" : "This snapshot has no sample count; statistical reliability is unknown.")
    : n < min
      ? (locale === "zh" ? `有效方向样本 ${n} 条，至少需要 ${min} 条；HOLD 和尚未实现的结果不计入。` : `${n} evaluated directional calls; ${min} required. HOLD and unrealized outcomes are excluded.`)
      : pct === null
        ? (locale === "zh" ? "已有样本，但该快照未提供有效统计值，需要检查证据计算。" : "Samples exist but this snapshot has no valid rate; check evidence computation.")
        : (locale === "zh" ? `基于 ${n} 条已实现的次日方向判断；不是未来胜率。` : `Based on ${n} realized next-day direction calls, not a future win probability.`);
  return { pct, n, min, sampleLabel, reason };
}
