// Shared display-label helper for all 11 signal names.
//
// Backend signal names (factor / technicals / analyst / earnings / news /
// insider / options / premarket / macro / calendar / political_impact) stay
// stable for SQL + breakdown contracts. The display label is overridden
// here so the UI (Radar + Table) shows i18n-translated text consistently.
//
// Lookup chain:
//   1. i18n key `attribution.signal_label_<name>` (translation if present)
//   2. SIGNAL_DISPLAY_LABEL_FALLBACK below (English/Chinese-mixed alias)
//   3. Raw signal name (last resort)

import { t, type Locale } from "./i18n";

const SIGNAL_DISPLAY_LABEL_FALLBACK: Record<string, Record<Locale, string>> = {
  factor: { zh: "因子", en: "Factor" },
  technicals: { zh: "技术面", en: "Technicals" },
  analyst: { zh: "分析师", en: "Analyst" },
  earnings: { zh: "财报", en: "Earnings" },
  news: { zh: "新闻", en: "News" },
  insider: { zh: "内部交易", en: "Insider" },
  options: { zh: "期权", en: "Options" },
  premarket: { zh: "盘前", en: "Pre-market" },
  macro: { zh: "宏观 (波动率)", en: "Macro (Vol)" },
  calendar: { zh: "日历", en: "Calendar" },
  political_impact: { zh: "政治", en: "Political" },
};

export function getSignalDisplayLabel(
  signalName: string,
  locale: Locale,
): string {
  const key = `attribution.signal_label_${signalName}`;
  const translated = t(locale, key as Parameters<typeof t>[1]);
  // t() returns the key string itself when not found; treat that as miss.
  if (translated !== key) return translated;
  const fallback = SIGNAL_DISPLAY_LABEL_FALLBACK[signalName]?.[locale];
  return fallback ?? signalName;
}
