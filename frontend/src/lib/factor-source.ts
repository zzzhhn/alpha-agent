/**
 * Disclosure for the composite's "factor" signal.
 *
 * The backend attaches `raw.factor_source` = { expression, is_custom, panel,
 * data_date }. A custom expression is evaluated on the frozen research
 * parquet, so its value can lag the live market by weeks; this note makes
 * that visible instead of letting the signal timestamp imply freshness.
 */
import type { Locale } from "@/lib/i18n";

export interface FactorSource {
  readonly expression: string | null;
  readonly isCustom: boolean;
  readonly panel: "live_daily_prices" | "frozen_research_parquet" | null;
  readonly dataDate: string | null;
}

export function readFactorSource(raw: unknown): FactorSource | null {
  if (!raw || typeof raw !== "object") return null;
  const source = (raw as Record<string, unknown>).factor_source;
  if (!source || typeof source !== "object") return null;
  const s = source as Record<string, unknown>;
  const panel = s.panel === "live_daily_prices" || s.panel === "frozen_research_parquet" ? s.panel : null;
  return {
    expression: typeof s.expression === "string" ? s.expression : null,
    isCustom: s.is_custom === true,
    panel,
    dataDate: typeof s.data_date === "string" ? s.data_date.slice(0, 10) : null,
  };
}

/** One short line; `stale` means the evaluated panel row predates the card's market date. */
export function factorSourceNote(
  source: FactorSource | null,
  marketDate: string | null,
  locale: Locale,
): { text: string; stale: boolean } | null {
  if (!source) return null;
  const zh = locale === "zh";
  const date = source.dataDate ?? (zh ? "未知" : "unknown");
  const frozen = source.panel === "frozen_research_parquet";
  const stale = !!(source.dataDate && marketDate && source.dataDate < marketDate.slice(0, 10));
  const kind = source.isCustom
    ? (zh ? "自定义表达式" : "Custom expression")
    : (zh ? "预设表达式" : "Preset expression");
  const panel = frozen
    ? (zh ? "冻结研究面板" : "frozen research panel")
    : (zh ? "每日行情" : "daily prices");
  return {
    text: zh ? `${kind} · ${panel} · 数据截至 ${date}` : `${kind} · ${panel} · data through ${date}`,
    stale,
  };
}
