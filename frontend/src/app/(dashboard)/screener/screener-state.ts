const SECTOR_LABELS_ZH: Readonly<Record<string, string>> = {
  "Communication Services": "通信服务",
  "Consumer Discretionary": "可选消费",
  "Consumer Staples": "必需消费",
  Energy: "能源",
  Financials: "金融",
  "Health Care": "医疗保健",
  Industrials: "工业",
  "Information Technology": "信息技术",
  Materials: "原材料",
  "Real Estate": "房地产",
  Utilities: "公用事业",
  // Preserve provider aliases as values, while using the same display names.
  Technology: "信息技术",
  "Financial Services": "金融",
  Healthcare: "医疗保健",
  "Consumer Cyclical": "可选消费",
  "Consumer Defensive": "必需消费",
  "Basic Materials": "原材料",
};

export function isClassifiedScreenerSector(sector: string | null | undefined): boolean {
  const normalized = sector?.trim().toLowerCase() ?? "";
  return normalized.length > 0 && !["unknown", "unclassified", "n/a", "na", "未知", "未分类"].includes(normalized);
}

/** Display-only localization. Never substitute these labels in API payloads. */
export function screenerSectorLabel(sector: string | null | undefined, locale: "zh" | "en"): string {
  if (!isClassifiedScreenerSector(sector)) return locale === "zh" ? "未分类" : "Unclassified";
  return locale === "zh" ? SECTOR_LABELS_ZH[sector!.trim()] ?? sector! : sector!;
}

/** Compare editable inputs with the inputs captured by a successful request. */
export function screenerDraftKey(draft: {
  readonly selections: readonly { readonly id: string; readonly direction: string; readonly weight: number }[];
  readonly selectedSectors: ReadonlySet<string>;
  readonly excludeInput: string;
  readonly minCap: string;
  readonly maxCap: string;
  readonly lookback: number;
  readonly topN: number;
  readonly combineMethod: string;
  readonly asOfDate: string;
  readonly neutralize: string;
}): string {
  return JSON.stringify({
    ...draft,
    selectedSectors: [...draft.selectedSectors].sort(),
    excludeInput: [...new Set(draft.excludeInput.split(/[,，\s]+/).map((ticker) => ticker.trim().toUpperCase()).filter(Boolean))].sort(),
    minCap: draft.minCap.trim() ? Number(draft.minCap) : null,
    maxCap: draft.maxCap.trim() ? Number(draft.maxCap) : null,
    asOfDate: draft.asOfDate.trim(),
  });
}
