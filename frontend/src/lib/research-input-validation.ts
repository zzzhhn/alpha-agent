// Matches FactorSpec and FactorBacktestRequest. Keep UI hints and execution
// gates on the same bounds, including when loading persisted drafts.
export const RESEARCH_NUMBER_LIMITS = {
  topPct: { min: 1, max: 50 },
  bottomPct: { min: 1, max: 50 },
  lookback: { min: 5, max: 252 },
  transactionCostBps: { min: 0, max: 200 },
} as const;

type Field = keyof typeof RESEARCH_NUMBER_LIMITS;

export function researchNumberError(field: Field, value: number, locale: "zh" | "en"): string | undefined {
  const { min, max } = RESEARCH_NUMBER_LIMITS[field];
  const integer = field === "lookback";
  if (Number.isFinite(value) && value >= min && value <= max && (!integer || Number.isInteger(value))) return undefined;
  return locale === "zh"
    ? `请输入 ${min} 至 ${max} 的${integer ? "整数" : "数值"}`
    : `Enter ${integer ? "an integer" : "a number"} from ${min} to ${max}`;
}

export function researchParameterErrors(values: Record<Field, number>, locale: "zh" | "en") {
  return {
    topPct: researchNumberError("topPct", values.topPct, locale),
    bottomPct: researchNumberError("bottomPct", values.bottomPct, locale),
    lookback: researchNumberError("lookback", values.lookback, locale),
    transactionCostBps: researchNumberError("transactionCostBps", values.transactionCostBps, locale),
  };
}
